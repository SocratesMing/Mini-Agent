"""聊天路由.

提供流式和非流式聊天 API 接口.
"""

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from mini_agent.web.database import Database, SessionModel, get_database
from mini_agent.web.models import (
    ChatRequest,
    ChatResponse,
)
from mini_agent.web.service import get_or_create_agent, remove_session_agent, chat_stream_generator

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/chat",
    tags=["Chat"],
)


@router.post(
    "/stream",
    summary="流式聊天",
    description="发送聊天消息并接收实时流式响应，包括思考过程和最终内容。"
)
async def chat_stream(
    request: ChatRequest,
    db: Annotated[Database, Depends(get_database)],
    http_request: Request,
):
    """发送聊天消息并返回流式响应."""
    start_time = time.time()
    
    if not request.message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    
    session_id = request.session_id
    message_id = request.message_id or str(uuid.uuid4())
    
    sid = session_id[-5:] if session_id else "new"
    
    logger.info(f"[{sid}] 聊天请求 | message: {request.message[:50]}{'...' if len(request.message) > 50 else ''} | deep_think: {request.enable_deep_think}")
    
    def generate_session_title(message, files):
        if message and message.strip():
            title = message.strip()
            return title[:12] + "..." if len(title) > 12 else title
        elif files and len(files) > 0:
            filename = files[0].get('filename', '文件')
            return filename[:12] + "..." if len(filename) > 12 else filename
        else:
            return "未命名会话"
    
    if session_id is None:
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        session_title = generate_session_title(request.message, request.files)
        session_data = SessionModel(
            session_id=session_id,
            title=session_title,
            messages=[],
            created_at=now,
            updated_at=now,
        )
        db.create_session(session_data)
    else:
        session = db.get_session(session_id)
        if not session:
            session_id = str(uuid.uuid4())
            now = datetime.now().isoformat()
            session_title = generate_session_title(request.message, request.files)
            session_data = SessionModel(
                session_id=session_id,
                title=session_title,
                messages=[],
                created_at=now,
                updated_at=now,
            )
            db.create_session(session_data)
        elif len(session.messages) == 0:
            session_title = generate_session_title(request.message, request.files)
            session.title = session_title
            session.updated_at = datetime.now().isoformat()
            db.update_session(session)
    
    user_message = {
        "role": "user",
        "content": request.message,
        "timestamp": datetime.now().isoformat(),
        "files": request.files or [],
    }
    db.add_message(session_id, user_message)
    
    parsed_content = request.message
    if request.files and len(request.files) > 0:
        try:
            from mini_agent.tools import DocumentParseTool
            parse_tool = DocumentParseTool()
            
            file_contents = []
            for file_info in request.files:
                file_path = file_info.get('file_path')
                if file_path:
                    result = parse_tool.run(file_path)
                    if result.get('success'):
                        content = result.get('content', '')
                        filename = file_info.get('filename', 'unknown')
                        file_contents.append(f"【文件: {filename}】\n{content}")
                    else:
                        logger.warning(f"[{sid}] 文件解析失败: {file_path}")
            
            if file_contents:
                parsed_content = f"{request.message}\n\n--- 文件内容 ---\n\n" + "\n\n---\n\n".join(file_contents)
        except Exception as e:
            logger.error(f"[{sid}] 文件解析出错: {str(e)}")
    
    from mini_agent.web.server import get_app_config
    app_config = get_app_config()
    
    try:
        from mini_agent.llm import LLMClient
        from mini_agent.schema import LLMProvider
        
        provider = LLMProvider.ANTHROPIC if app_config.llm.provider == "anthropic" else LLMProvider.OPENAI
        llm_client = LLMClient(
            api_key=app_config.llm.api_key,
            provider=provider,
            api_base=app_config.llm.api_base,
            model=app_config.llm.model,
            retry_config=app_config.llm.retry,
        )
    except Exception as e:
        logger.error(f"[{sid}] LLM客户端创建失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取LLM客户端失败: {str(e)}")
    
    try:
        from mini_agent.tools import BashTool, ReadTool, WriteTool, EditTool, SessionNoteTool, DocumentParseTool, DocumentInfoTool
        from pathlib import Path
        import os
        
        tools = []
        project_root = Path(__file__).parent.parent.parent
        
        if app_config.tools.enable_bash:
            tools.append(BashTool())
        
        if app_config.tools.enable_file_tools:
            tools.extend([
                ReadTool(workspace_dir=str(project_root / "workspace")),
                WriteTool(workspace_dir=str(project_root / "workspace")),
                EditTool(workspace_dir=str(project_root / "workspace")),
                DocumentParseTool(),
                DocumentInfoTool()
            ])
        
        if app_config.tools.enable_note:
            tools.append(SessionNoteTool(memory_file=str(project_root / "workspace" / ".agent_memory.json")))
    except Exception as e:
        logger.error(f"[{sid}] 工具加载失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取工具列表失败: {str(e)}")
    
    try:
        system_prompt = ""
        if app_config.agent.system_prompt_path:
            import os
            prompt_path = app_config.agent.system_prompt_path
            if os.path.exists(prompt_path):
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    system_prompt = f.read()
        
        components = {
            "llm_client": llm_client,
            "tools": tools,
            "system_prompt": system_prompt,
            "max_steps": app_config.agent.max_steps,
            "workspace_dir": app_config.agent.workspace_dir,
        }
    except Exception as e:
        logger.error(f"[{sid}] Agent组件加载失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取Agent组件失败: {str(e)}")
    
    agent = get_or_create_agent(
        session_id,
        components["llm_client"],
        components["tools"],
        components["system_prompt"],
        components["max_steps"],
        components["workspace_dir"],
    )
    
    return StreamingResponse(
        chat_stream_generator(
            request=request,
            db=db,
            agent=agent,
            session_id=session_id,
            message_id=message_id,
            http_request=http_request,
            parsed_content=parsed_content,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete(
    "/session/{session_id}/agent",
    summary="清除会话Agent缓存",
    description="清除指定会话的Agent实例缓存，下次请求会创建新的Agent。"
)
async def clear_session_agent(session_id: str):
    """清除会话的Agent缓存."""
    sid = session_id[-5:] if session_id else "new"
    remove_session_agent(session_id)
    logger.info(f"[{sid}] Agent缓存已清除")
    return {
        "status": "success",
        "message": f"会话 {session_id} 的Agent缓存已清除"
    }
