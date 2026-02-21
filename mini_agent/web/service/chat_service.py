"""聊天服务模块."""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, AsyncGenerator, Optional

from mini_agent.agent import Agent
from mini_agent.web.database import Database, SessionModel
from mini_agent.web.models import ChatRequest, ChatResponse

if TYPE_CHECKING:
    from fastapi import HTTPException
    from starlette.requests import Request

logger = logging.getLogger("mini_agent.chat_service")


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
        session_id=session_id,
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
    http_request: Optional["Request"] = None,
    parsed_content: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """生成聊天流式响应."""
    start_time = time.time()
    sid = session_id[-5:] if session_id else "-----"
    
    message_content = parsed_content if parsed_content else request.message
    
    logger.info(f"[{sid}] 开始流式响应生成")
    logger.info(f"[{sid}] session_id: {session_id} | message_id: {message_id}")
    logger.info(f"[{sid}] message: {message_content[:50]}{'...' if len(message_content) > 50 else ''} | enable_deep_think: {request.enable_deep_think}")
    logger.info(f"[{sid}] 请求日志已记录")
    
    session = db.get_session(session_id)
    
    if session is None:
        logger.error(f"[{sid}] 会话不存在")
        yield f"data: {json.dumps({'type': 'error', 'content': '会话不存在'}, ensure_ascii=False)}\n\n"
        return
    
    if len(session.messages) == 0 and message_content:
        session.title = message_content[:12] + "..." if len(message_content) > 12 else message_content
        session.updated_at = datetime.now().isoformat()
        db.update_session(session)
        logger.info(f"[{sid}] 更新会话标题: {session.title}")
    
    full_response = ""
    thinking_content = None
    thinking_started = False
    assistant_started = False
    tool_calls_count = 0
    
    content_blocks = []
    block_order = 0
    current_content = ""
    
    def add_content_block():
        nonlocal current_content, block_order
        if current_content:
            content_blocks.append({
                "type": "content",
                "content": current_content,
                "order": block_order,
            })
            block_order += 1
            current_content = ""
    
    cancel_event = asyncio.Event()
    agent.cancel_event = cancel_event
    
    async def check_client_disconnect():
        if http_request and hasattr(http_request, 'is_disconnected'):
            while not cancel_event.is_set():
                if await http_request.is_disconnected():
                    logger.info(f"[{sid}] 检测到客户端断开连接")
                    cancel_event.set()
                    break
                await asyncio.sleep(0.5)
    
    disconnect_task = None
    if http_request:
        disconnect_task = asyncio.create_task(check_client_disconnect())
    
    try:
        start_event = {'type': 'start', 'session_id': session_id, 'message_id': message_id, 'title': session.title}
        logger.info(f"[{sid}] 发送事件: start | 标题: {session.title}")
        yield f"data: {json.dumps(start_event, ensure_ascii=False)}\n\n"
        
        event_count = 0
        step_start_time = time.time()
        
        async for event in agent.run_stream(message_content, enable_deep_think=request.enable_deep_think):
            event_count += 1
            event_type = event.get("type", "unknown")
            event_time = time.time() - step_start_time
            
            step_start_time = time.time()
            
            if event_type == "thinking_start":
                thinking_started = True
            elif event_type == "thinking":
                content = event.get("content", "")
                thinking_content = (thinking_content or "") + content
                yield f"data: {json.dumps({'type': 'thinking', 'content': content}, ensure_ascii=False)}\n\n"
            elif event_type == "assistant_start":
                assistant_started = True
                yield f"data: {json.dumps({'type': 'assistant_start', 'content': ''}, ensure_ascii=False)}\n\n"
            elif event_type == "content":
                content = event.get("content", "")
                full_response += content
                current_content += content
                yield f"data: {json.dumps({'type': 'content', 'content': content}, ensure_ascii=False)}\n\n"
            elif event_type == "tool_call":
                add_content_block()
                tool_name = event.get("tool_name", "")
                arguments = event.get("arguments", {})
                tool_call_id = event.get("tool_call_id", "")
                tool_calls_count += 1
                logger.info(f"[{sid}] 工具调用: tool_name={tool_name} | tool_call_id={tool_call_id}")
                logger.info(f"[{sid}] 工具参数: {json.dumps(arguments, ensure_ascii=False)[:200]}")
                
                db_start = time.time()
                db.add_tool_call_record(
                    session_id=session_id,
                    message_id=message_id,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    arguments=arguments,
                    result=None,
                    success=True
                )
                logger.info(f"[{sid}] 保存工具调用记录到数据库 | 耗时: {time.time() - db_start:.2f}s")
                
                content_blocks.append({
                    "type": "tool_call",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "tool_call_id": tool_call_id,
                    "order": block_order,
                })
                block_order += 1
                yield f"data: {json.dumps({'type': 'tool_call', 'tool_name': tool_name, 'arguments': arguments, 'tool_call_id': tool_call_id}, ensure_ascii=False)}\n\n"
            elif event_type == "tool_result":
                tool_name = event.get("tool_name", "")
                success = event.get("success", False)
                result = event.get("result", "")
                tool_call_id = event.get("tool_call_id", "")
                logger.info(f"[{sid}] 工具结果: tool_name={tool_name} | success={success}")
                logger.info(f"[{sid}] 工具结果内容: {str(result)[:100]}{'...' if len(str(result)) > 100 else ''}")
                
                if tool_call_id:
                    db_start = time.time()
                    db.update_tool_call_result(
                        session_id=session_id,
                        message_id=message_id,
                        tool_call_id=tool_call_id,
                        result=result,
                        success=success
                    )
                    logger.info(f"[{sid}] 更新工具调用结果到数据库 | 耗时: {time.time() - db_start:.2f}s")
                
                content_blocks.append({
                    "type": "tool_result",
                    "tool_name": tool_name,
                    "result": result,
                    "success": success,
                    "tool_call_id": tool_call_id,
                    "order": block_order,
                })
                block_order += 1
                yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': tool_name, 'success': success, 'result': result, 'tool_call_id': tool_call_id}, ensure_ascii=False)}\n\n"
            elif event_type == "done":
                add_content_block()
                event_thinking = event.get("thinking", None)
                if event_thinking:
                    thinking_content = event_thinking
                steps = event.get("steps", 1)
                tool_calls = event.get("tool_calls", 0)
                
                logger.info(f"[{sid}] 思考完成 | 长度: {len(thinking_content) if thinking_content else 0}")
                if thinking_content:
                    logger.info(f"[{sid}] 思考内容全文:\n{thinking_content}")
                logger.info(f"[{sid}] 正式内容完成 | 长度: {len(full_response)}")
                logger.info(f"[{sid}] 正式响应全文:\n{full_response}")
                logger.info(f"[{sid}] 响应完成: steps={steps} | tool_calls={tool_calls}")
                
                if thinking_content:
                    thinking_block = {
                        "type": "thinking",
                        "content": thinking_content,
                        "order": 0,
                    }
                    content_blocks.insert(0, thinking_block)
                    for i, block in enumerate(content_blocks):
                        block["order"] = i
                
                assistant_message = {
                    "role": "assistant",
                    "content": full_response,
                    "timestamp": datetime.now().isoformat(),
                    "thinking": thinking_content,
                    "blocks": content_blocks
                }
                
                db_start = time.time()
                db.add_message(session_id, assistant_message)
                logger.info(f"[{sid}] 保存助手消息到数据库 | blocks_count={len(content_blocks)} | 耗时: {time.time() - db_start:.2f}s")
                
                done_event = {
                    'type': 'done', 
                    'session_id': session_id, 
                    'message_id': message_id, 
                    'content': full_response, 
                    'steps': steps, 
                    'tool_calls': tool_calls
                }
                logger.info(f"[{sid}] 发送事件: done")
                yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"
            elif event_type == "error":
                error_msg = event.get("content", "")
                logger.error(f"[{sid}] 错误: {error_msg}")
                yield f"data: {json.dumps({'type': 'error', 'content': error_msg}, ensure_ascii=False)}\n\n"
        
        cancel_event.set()
        if disconnect_task:
            disconnect_task.cancel()
            try:
                await disconnect_task
            except asyncio.CancelledError:
                pass
        
        total_time = time.time() - start_time
        logger.info(f"[{sid}] 流式响应完成: 总事件数={event_count} | 总内容长度={len(full_response)} | 工具调用次数={tool_calls_count} | 总耗时: {total_time:.2f}s")
                    
    except Exception as e:
        cancel_event.set()
        if disconnect_task:
            disconnect_task.cancel()
            try:
                await disconnect_task
            except asyncio.CancelledError:
                pass
        
        error_msg = str(e)
        logger.error(f"[{sid}] 流式响应异常: {error_msg}")
        import traceback
        logger.error(f"[{sid}] 异常堆栈:\n{traceback.format_exc()}")
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg}, ensure_ascii=False)}\n\n"


async def chat_non_stream(
    request: ChatRequest,
    db: Database,
    llm_client,
    tools,
    system_prompt: str,
    max_steps: int,
    workspace_dir: str,
):
    """非流式聊天处理."""
    from datetime import datetime
    from mini_agent.web.models import ChatResponse
    
    session_id = request.session_id
    message_id = request.message_id or str(uuid.uuid4())
    sid = session_id[-5:] if session_id else "-----"
    
    logger.info(f"[{sid}] 收到聊天请求(非流式)")
    logger.info(f"[{sid}] session_id: {session_id} | message_id: {message_id}")
    logger.info(f"[{sid}] message: {request.message[:50]}{'...' if len(request.message) > 50 else ''} | enable_deep_think: {request.enable_deep_think}")
    
    if session_id is None:
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        session_data = SessionModel(
            session_id=session_id,
            title=request.message[:12] + "..." if len(request.message) > 12 else request.message,
            messages=[],
            created_at=now,
            updated_at=now,
        )
        db.create_session(session_data)
        logger.info(f"[{sid}] 新建会话 | 标题: {session_data.title}")
    else:
        session = db.get_session(session_id)
        if session and len(session.messages) == 0:
            new_title = request.message[:12] + "..." if len(request.message) > 12 else request.message
            session.title = new_title
            session.updated_at = datetime.now().isoformat()
            db.update_session(session)
            logger.info(f"[{sid}] 更新会话标题 | 新标题: {new_title}")
    
    user_message = {
        "role": "user",
        "content": request.message,
        "timestamp": datetime.now().isoformat(),
    }
    db.add_message(session_id, user_message)
    
    from mini_agent.web.service.chat_service import get_or_create_agent
    agent = get_or_create_agent(
        session_id,
        llm_client,
        tools,
        system_prompt,
        max_steps,
        workspace_dir,
    )
    
    tool_list = list(agent.tools.values())
    logger.info(f"[{sid}] 请求日志已记录")
    
    full_response = ""
    thinking_content = None
    
    try:
        async for chunk in agent.run_stream(request.message, enable_deep_think=request.enable_deep_think):
            if "[THINKING]" in chunk and "[/THINKING]" in chunk:
                thinking_text = chunk.replace("[THINKING]", "").replace("[/THINKING]", "")
                thinking_content = (thinking_content or "") + thinking_text
            else:
                full_response += chunk
    except Exception as e:
        logger.error(f"[{sid}] 非流式响应异常: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
    assistant_message = {
        "role": "assistant",
        "content": full_response,
        "timestamp": datetime.now().isoformat(),
        "thinking": thinking_content,
    }
    db.add_message(session_id, assistant_message)
    
    logger.info(f"[{sid}] 非流式响应完成: content_length={len(full_response)}")
    
    return ChatResponse(
        session_id=session_id,
        response=full_response,
        thinking=thinking_content,
        tool_calls=None,
        usage={"total_tokens": agent.api_total_tokens} if agent.api_total_tokens else None,
    )
