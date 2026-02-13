"""会话管理路由.

提供会话的创建、查询、更新、删除等 REST API 接口.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from mini_agent.web.database import Database, SessionModel, get_database
from mini_agent.web.models import (
    CreateSessionRequest,
    CreateSessionResponse,
    DeleteSessionResponse,
    SessionDetail,
    SessionInfo,
    UpdateTitleRequest,
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/sessions",
    tags=["Session Management"],
)


@router.post(
    "",
    response_model=CreateSessionResponse,
    summary="创建新会话",
    description="创建一个新的聊天会话，返回会话ID和初始信息。"
)
async def create_session(
    request: CreateSessionRequest,
    db: Annotated[Database, Depends(get_database)],
):
    """创建新会话并存储到 SQLite 数据库."""
    import uuid
    
    session_id = str(uuid.uuid4())
    title = request.title if request.title else "未命名会话"
    now = datetime.now().isoformat()
    
    logger.info(f"创建会话 | ID: {session_id} | 标题: {title}")
    
    session_data = SessionModel(
        session_id=session_id,
        title=title,
        messages=[],
        created_at=now,
        updated_at=now,
    )
    
    db.create_session(session_data)
    
    logger.info(f"会话创建成功 | ID: {session_id}")
    
    return CreateSessionResponse(
        session_id=session_id,
        title=title,
        created_at=now,
        updated_at=now,
        message_count=0,
    )


@router.get(
    "",
    response_model=list[SessionInfo],
    summary="获取会话列表",
    description="获取所有会话列表，按更新时间降序排列。"
)
async def list_sessions(
    db: Annotated[Database, Depends(get_database)],
    limit: Annotated[int, Query(ge=1, le=100, description="返回数量限制")] = 50,
    offset: Annotated[int, Query(ge=0, description="偏移量")] = 0,
):
    """从 SQLite 数据库获取会话列表."""
    logger.info(f"查询会话列表 | limit: {limit} | offset: {offset}")
    
    sessions = db.list_sessions(limit=limit, offset=offset)
    
    logger.info(f"会话列表查询成功 | 总数: {len(sessions)}")
    
    return [
        SessionInfo(
            session_id=s.session_id,
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
            message_count=len(s.messages),
        )
        for s in sessions
    ]


@router.get(
    "/{session_id}",
    response_model=SessionDetail,
    summary="获取会话详情",
    description="获取指定会话的详细信息，包括所有消息。"
)
async def get_session(
    session_id: str,
    db: Annotated[Database, Depends(get_database)],
):
    """从 SQLite 数据库获取会话详情."""
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return SessionDetail(
        session_id=session.session_id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=session.messages,
    )


@router.delete(
    "/{session_id}",
    response_model=DeleteSessionResponse,
    summary="删除会话",
    description="删除指定的会话及其所有消息。"
)
async def delete_session(
    session_id: str,
    db: Annotated[Database, Depends(get_database)],
):
    """从 SQLite 数据库删除会话."""
    if not db.delete_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return DeleteSessionResponse(
        status="deleted",
        session_id=session_id,
    )


@router.put(
    "/{session_id}/title",
    response_model=SessionInfo,
    summary="更新会话标题",
    description="更新指定会话的标题。"
)
async def update_session_title(
    session_id: str,
    request: UpdateTitleRequest,
    db: Annotated[Database, Depends(get_database)],
):
    """更新 SQLite 数据库中的会话标题."""
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session.title = request.title or session.title
    session.updated_at = datetime.now().isoformat()
    db.update_session(session)
    
    return SessionInfo(
        session_id=session.session_id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=len(session.messages),
    )


@router.post(
    "/{session_id}/upload",
    summary="上传文件到会话",
    description="上传文件到指定会话，返回文件路径。"
)
async def upload_file(
    session_id: str,
    db: Annotated[Database, Depends(get_database)],
    file: UploadFile = File(...),
):
    """上传文件到会话目录，返回文件路径供 AI 读取."""
    import shutil
    
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    upload_dir = Path("workspace") / "sessions" / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    filename = file.filename or "unknown"
    file_path = upload_dir / filename
    
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    logger.info(f"文件上传成功 | 会话: {session_id} | 文件: {filename}")
    
    return {
        "filename": filename,
        "file_path": str(file_path),
        "size": file_path.stat().st_size,
    }


@router.get(
    "/{session_id}/files",
    summary="获取会话文件列表",
    description="获取指定会话上传的所有文件列表。"
)
async def list_session_files(
    session_id: str,
    db: Annotated[Database, Depends(get_database)],
):
    """获取会话已上传的文件列表."""
    import os
    
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    upload_dir = Path("workspace") / "sessions" / session_id
    
    if not upload_dir.exists():
        return {"files": []}
    
    files = []
    for f in upload_dir.iterdir():
        if f.is_file():
            files.append({
                "filename": f.name,
                "file_path": str(f),
                "size": f.stat().st_size,
            })
    
    return {"files": files}


@router.get(
    "/files/all",
    summary="获取所有文件",
    description="获取所有会话上传的文件列表。"
)
async def get_all_files():
    """获取所有会话已上传的文件列表."""
    upload_base = Path("workspace") / "sessions"
    
    if not upload_base.exists():
        return {"files": []}
    
    all_files = []
    for session_dir in upload_base.iterdir():
        if session_dir.is_dir():
            for f in session_dir.iterdir():
                try:
                    if f.is_file():
                        all_files.append({
                            "filename": f.name,
                            "file_path": str(f),
                            "size": f.stat().st_size,
                            "session_id": session_dir.name,
                        })
                except (OSError, PermissionError) as e:
                    logger.warning(f"无法访问文件 {f}: {e}")
    
    logger.info(f"获取所有文件 | 总数: {len(all_files)}")
    return {"files": all_files}


@router.get(
    "/sessions/{session_id}/tool-calls",
    summary="获取工具调用记录",
    description="获取指定会话的工具调用历史记录。"
)
async def get_session_tool_calls(
    session_id: str,
    message_id: Optional[str] = None
):
    """获取指定会话的工具调用记录."""
    db = get_database()
    records = db.get_tool_call_records(session_id, message_id)
    logger.info(f"获取工具调用记录 | 会话ID: {session_id} | 消息ID: {message_id} | 记录数: {len(records)}")
    return {"tool_calls": records}
