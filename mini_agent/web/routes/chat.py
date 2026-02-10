"""聊天路由.

提供流式和非流式聊天 API 接口.
支持多用户并发访问，会话级别 Agent 复用.
"""

import json
import uuid
from datetime import datetime
from typing import Annotated, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from mini_agent.agent import Agent
from mini_agent.schema import Message
from mini_agent.web.database import Database, SessionModel, get_database
from mini_agent.web.models import (
    AddMessageRequest,
    AddMessageResponse,
    ChatRequest,
    ChatResponse,
    GetChatHistoryResponse,
)


router = APIRouter(
    prefix="/api/chat",
    tags=["Chat"],
)


agent_cache: dict[str, Agent] = {}
agent_cache_lock = None


def get_agent_cache_lock():
    """获取Agent缓存锁（懒加载）."""
    global agent_cache_lock
    if agent_cache_lock is None:
        try:
            import threading
            agent_cache_lock = threading.Lock()
        except Exception:
            agent_cache_lock = None
    return agent_cache_lock


def get_session_agent(session_id: str) -> Optional[Agent]:
    """获取会话的Agent实例（从缓存）."""
    lock = get_agent_cache_lock()
    if lock:
        with lock:
            return agent_cache.get(session_id)
    return agent_cache.get(session_id)


def set_session_agent(session_id: str, agent: Agent):
    """缓存会话的Agent实例."""
    lock = get_agent_cache_lock()
    if lock:
        with lock:
            agent_cache[session_id] = agent
    else:
        agent_cache[session_id] = agent


def remove_session_agent(session_id: str):
    """移除会话的Agent缓存."""
    lock = get_agent_cache_lock()
    if lock:
        with lock:
            if session_id in agent_cache:
                del agent_cache[session_id]
    else:
        if session_id in agent_cache:
            del agent_cache[session_id]


def create_session_agent(session_id: str, llm_client, tools, system_prompt: str, max_steps: int, workspace_dir: str) -> Agent:
    """为会话创建Agent实例并缓存."""
    agent = Agent(
        llm_client=llm_client,
        system_prompt=system_prompt,
        tools=tools,
        max_steps=max_steps,
        workspace_dir=workspace_dir,
    )
    set_session_agent(session_id, agent)
    return agent


def get_or_create_agent(
    session_id: str,
    llm_client,
    tools,
    system_prompt: str,
    max_steps: int,
    workspace_dir: str,
) -> Agent:
    """获取或创建会话的Agent实例."""
    agent = get_session_agent(session_id)
    
    if agent is None:
        agent = create_session_agent(
            session_id,
            llm_client,
            tools,
            system_prompt,
            max_steps,
            workspace_dir,
        )
    
    return agent


async def chat_stream_generator(
    request: ChatRequest,
    db: Database,
    agent: Agent,
    session_id: str,
    message_id: str,
) -> AsyncGenerator[str, None]:
    """生成聊天流式响应."""
    session = db.get_session(session_id)
    
    if session is None:
        yield f"data: {json.dumps({'type': 'error', 'content': '会话不存在'}, ensure_ascii=False)}\n\n"
        return
    
    full_response = ""
    thinking_content = None
    thinking_started = False
    assistant_started = False
    
    try:
        yield f"data: {json.dumps({'type': 'start', 'session_id': session_id, 'message_id': message_id}, ensure_ascii=False)}\n\n"
        
        tool_list = list(agent.tools.values())
        
        async for chunk in agent.llm.stream_generate(messages=agent.messages, tools=tool_list):
            if "[THINKING]" in chunk and "[/THINKING]" in chunk:
                thinking_text = chunk.replace("[THINKING]", "").replace("[/THINKING]", "")
                if not thinking_started:
                    thinking_started = True
                    yield f"data: {json.dumps({'type': 'thinking_start', 'content': ''}, ensure_ascii=False)}\n\n"
                thinking_content = (thinking_content or "") + thinking_text
                yield f"data: {json.dumps({'type': 'thinking', 'content': thinking_text}, ensure_ascii=False)}\n\n"
            else:
                if chunk and not assistant_started:
                    assistant_started = True
                    yield f"data: {json.dumps({'type': 'assistant_start', 'content': ''}, ensure_ascii=False)}\n\n"
                if chunk:
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"
                    
    except Exception as e:
        error_msg = str(e)
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg}, ensure_ascii=False)}\n\n"
        return
    
    assistant_message = {
        "role": "assistant",
        "content": full_response,
        "timestamp": datetime.now().isoformat(),
        "thinking": thinking_content,
    }
    db.add_message(session_id, assistant_message)
    
    yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'message_id': message_id, 'content': full_response}, ensure_ascii=False)}\n\n"


def get_agent_components():
    """获取创建Agent所需的组件."""
    import asyncio
    from pathlib import Path
    from mini_agent.config import Config
    from mini_agent.llm import LLMClient
    from mini_agent.schema import LLMProvider
    from mini_agent.tools.bash_tool import BashTool
    from mini_agent.tools.file_tools import ReadTool, WriteTool, EditTool
    from mini_agent.tools.note_tool import SessionNoteTool
    from mini_agent.tools.skill_tool import create_skill_tools
    from mini_agent.tools.mcp_loader import load_mcp_tools_async
    
    try:
        app_config = Config.load()
        
        provider = LLMProvider.ANTHROPIC if app_config.llm.provider == "anthropic" else LLMProvider.OPENAI
        llm_client = LLMClient(
            api_key=app_config.llm.api_key,
            provider=provider,
            api_base=app_config.llm.api_base,
            model=app_config.llm.model,
            retry_config=app_config.llm.retry,
        )
        
        workspace_dir = Path(app_config.agent.workspace_dir)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        
        tools = []
        
        if app_config.tools.enable_bash:
            tools.append(BashTool())
        
        if app_config.tools.enable_file_tools:
            tools.extend([
                ReadTool(workspace_dir=str(workspace_dir)),
                WriteTool(workspace_dir=str(workspace_dir)),
                EditTool(workspace_dir=str(workspace_dir)),
            ])
        
        if app_config.tools.enable_note:
            tools.append(SessionNoteTool(memory_file=str(workspace_dir / ".agent_memory.json")))
        
        if app_config.tools.enable_skills:
            skills_path = Path(app_config.tools.skills_dir).expanduser()
            if skills_path.is_absolute():
                skills_dir = str(skills_path)
            else:
                search_paths = [
                    skills_path,
                    Path("mini_agent") / skills_path,
                    Config.get_package_dir() / skills_path,
                ]
                skills_dir = str(skills_path)
                for path in search_paths:
                    if path.exists():
                        skills_dir = str(path.resolve())
                        break
            skill_tools, _ = create_skill_tools(skills_dir)
            tools.extend(skill_tools)
        
        if app_config.tools.enable_mcp:
            try:
                mcp_tools = asyncio.run(load_mcp_tools_async(app_config.tools.mcp_config_path))
                tools.extend(mcp_tools)
            except Exception:
                pass
        
        system_prompt_path = Config.find_config_file(app_config.agent.system_prompt_path)
        if system_prompt_path and system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            system_prompt = "You are Mini-Agent, an intelligent assistant powered by MiniMax M2.1 that can help users complete various tasks."
        
        return {
            "llm_client": llm_client,
            "tools": tools,
            "system_prompt": system_prompt,
            "max_steps": app_config.agent.max_steps,
            "workspace_dir": app_config.agent.workspace_dir,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取Agent组件失败: {str(e)}")


@router.post(
    "/stream",
    summary="流式聊天",
    description="发送聊天消息并接收实时流式响应，包括思考过程和最终内容。"
)
async def chat_stream(
    request: ChatRequest,
    db: Annotated[Database, Depends(get_database)],
):
    """发送聊天消息并返回流式响应."""
    if not request.message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    
    session_id = request.session_id
    message_id = request.message_id or str(uuid.uuid4())
    
    if session_id is None:
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        session_data = SessionModel(
            session_id=session_id,
            title=request.message[:50] + "..." if len(request.message) > 50 else request.message,
            messages=[],
            created_at=now,
            updated_at=now,
        )
        db.create_session(session_data)
    
    user_message = {
        "role": "user",
        "content": request.message,
        "timestamp": datetime.now().isoformat(),
        "message_id": message_id,
    }
    db.add_message(session_id, user_message)
    
    try:
        components = get_agent_components()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent初始化失败: {str(e)}")
    
    agent = get_or_create_agent(
        session_id,
        components["llm_client"],
        components["tools"],
        components["system_prompt"],
        components["max_steps"],
        components["workspace_dir"],
    )
    
    return StreamingResponse(
        chat_stream_generator(request, db, agent, session_id, message_id),
        media_type="text/event-stream",
    )


@router.post(
    "",
    response_model=ChatResponse,
    summary="非流式聊天",
    description="发送聊天消息，等待完整响应后返回结果。"
)
async def chat(
    request: ChatRequest,
    db: Annotated[Database, Depends(get_database)],
):
    """发送聊天消息并返回完整响应."""
    if not request.message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    
    session_id = request.session_id
    
    if session_id is None:
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        session_data = SessionModel(
            session_id=session_id,
            title=request.message[:50] + "..." if len(request.message) > 50 else request.message,
            messages=[],
            created_at=now,
            updated_at=now,
        )
        db.create_session(session_data)
    
    user_message = {
        "role": "user",
        "content": request.message,
        "timestamp": datetime.now().isoformat(),
    }
    db.add_message(session_id, user_message)
    
    try:
        components = get_agent_components()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent初始化失败: {str(e)}")
    
    agent = get_or_create_agent(
        session_id,
        components["llm_client"],
        components["tools"],
        components["system_prompt"],
        components["max_steps"],
        components["workspace_dir"],
    )
    
    full_response = ""
    thinking_content = None
    
    try:
        async for chunk in agent.run_stream(request.message):
            if "[THINKING]" in chunk and "[/THINKING]" in chunk:
                thinking_text = chunk.replace("[THINKING]", "").replace("[/THINKING]", "")
                thinking_content = (thinking_content or "") + thinking_text
            else:
                full_response += chunk
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    assistant_message = {
        "role": "assistant",
        "content": full_response,
        "timestamp": datetime.now().isoformat(),
        "thinking": thinking_content,
    }
    db.add_message(session_id, assistant_message)
    
    return ChatResponse(
        session_id=session_id,
        response=full_response,
        thinking=thinking_content,
        tool_calls=None,
        usage={"total_tokens": agent.api_total_tokens} if agent.api_total_tokens else None,
    )


@router.delete(
    "/session/{session_id}/agent",
    summary="清除会话Agent缓存",
    description="清除指定会话的Agent实例缓存，下次请求会创建新的Agent。"
)
async def clear_session_agent(session_id: str):
    """清除会话的Agent缓存."""
    remove_session_agent(session_id)
    return {
        "status": "success",
        "session_id": session_id,
        "message": "Agent缓存已清除",
    }


@router.get(
    "/history/{session_id}",
    response_model=GetChatHistoryResponse,
    summary="获取聊天历史",
    description="获取指定会话的所有消息历史。"
)
async def get_chat_history(
    session_id: str,
    db: Annotated[Database, Depends(get_database)],
):
    """获取会话的聊天历史."""
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return GetChatHistoryResponse(
        session_id=session.session_id,
        title=session.title,
        messages=session.messages,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post(
    "/history/{session_id}/messages",
    response_model=AddMessageResponse,
    summary="添加消息",
    description="手动向会话添加用户或助手消息。"
)
async def add_message(
    session_id: str,
    request: AddMessageRequest,
    db: Annotated[Database, Depends(get_database)],
):
    """向会话添加消息."""
    message = {
        "role": request.role,
        "content": request.content,
        "timestamp": datetime.now().isoformat(),
    }
    
    session = db.add_message(session_id, message)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return AddMessageResponse(
        status="success",
        session_id=session_id,
        message_count=len(session.messages),
    )
