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
    "/files/all",
    summary="获取所有文件",
    description="获取当前用户上传的所有文件列表。"
)
async def get_all_files(
    db: Annotated[Database, Depends(get_database)],
):
    """获取当前用户上传的所有文件列表（从文件系统扫描）."""
    user = db.get_or_create_default_user()
    username = user.username
    
    safe_username = "".join(c for c in username if c.isalnum() or c in ('_', '-')) or "user"
    user_dir = Path("workspace") / "users" / safe_username / "files"
    
    files = []
    if user_dir.exists():
        for file_path in user_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                file_ext = file_path.suffix[1:] if file_path.suffix else "unknown"
                files.append({
                    "id": file_path.name,
                    "filename": file_path.name,
                    "file_path": str(file_path),
                    "file_type": file_ext,
                    "size": stat.st_size,
                    "uploaded_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "username": username,
                    "session_title": "",
                })
    
    logger.info(f"获取用户文件 | 用户: {username} | 用户目录: {user_dir} | 文件总数: {len(files)}")
    if files:
        for f in files:
            logger.debug(f"  - 文件: {f.get('filename')} | 大小: {f.get('size')} | 路径: {f.get('file_path')}")
    
    return {"files": files}


@router.get(
    "/files/{filename}/download",
    summary="下载文件",
    description="下载指定文件。"
)
async def download_file(
    filename: str,
    db: Annotated[Database, Depends(get_database)],
):
    """下载文件."""
    from fastapi.responses import FileResponse
    
    user = db.get_or_create_default_user()
    username = user.username
    
    safe_username = "".join(c for c in username if c.isalnum() or c in ('_', '-')) or "user"
    user_dir = Path("workspace") / "users" / safe_username / "files"
    file_path = user_dir / filename
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    logger.info(f"下载文件 | 文件名: {filename} | 用户: {username} | 路径: {file_path}")
    
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream"
    )


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
    description="删除指定的会话及其所有消息和文件。"
)
async def delete_session(
    session_id: str,
    db: Annotated[Database, Depends(get_database)],
):
    """从 SQLite 数据库删除会话及其关联文件."""
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    files = db.get_session_files(session_id)
    deleted_files = []
    for file_info in files:
        file_path = file_info.get('file_path')
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                deleted_files.append(file_info.get('filename'))
                logger.info(f"删除会话文件 | 会话: {session_id} | 文件: {file_path}")
            except Exception as e:
                logger.error(f"删除会话文件失败 | 会话: {session_id} | 文件: {file_path} | 错误: {e}")
    
    db.delete_session(session_id)
    
    logger.info(f"删除会话 | 会话ID: {session_id} | 标题: {session.title} | 删除文件数: {len(deleted_files)}")
    
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
    
    user = db.get_or_create_default_user()
    username = user.username
    
    safe_username = "".join(c for c in username if c.isalnum() or c in ('_', '-')) or "user"
    
    upload_dir = Path("workspace") / "users" / safe_username / "files"
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    filename = file.filename or "unknown"
    file_path = upload_dir / filename
    
    counter = 1
    while file_path.exists():
        name, ext = os.path.splitext(filename)
        file_path = upload_dir / f"{name}_{counter}{ext}"
        counter += 1
    
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    file_size = file_path.stat().st_size
    
    file_type = os.path.splitext(filename)[1][1:] if '.' in filename else 'unknown'
    
    file_id = db.add_session_file(
        session_id=session_id,
        filename=file_path.name,
        file_path=str(file_path),
        file_type=file_type,
        size=file_size,
        username=username
    )
    
    logger.info(f"文件上传成功 | 会话: {session_id} | 文件: {file_path.name} | 用户: {username} | ID: {file_id}")
    
    return {
        "id": file_id,
        "filename": file_path.name,
        "file_path": str(file_path),
        "file_type": file_type,
        "size": file_size,
        "username": username,
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
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    files = db.get_session_files(session_id)
    
    return {"files": files}


@router.delete(
    "/{session_id}/files/{file_id}",
    summary="删除会话文件",
    description="删除指定会话的指定文件。"
)
async def delete_session_file(
    session_id: str,
    file_id: int,
    db: Annotated[Database, Depends(get_database)],
):
    """删除会话文件并移除文件系统中的文件."""
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    files = db.get_session_files(session_id)
    file_to_delete = next((f for f in files if f['id'] == file_id), None)
    
    if not file_to_delete:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    file_path = file_to_delete['file_path']
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info(f"文件系统删除成功 | 文件: {file_path}")
        except Exception as e:
            logger.error(f"文件系统删除失败 | 文件: {file_path} | 错误: {e}")
    
    if not db.delete_session_file(file_id):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    logger.info(f"文件删除成功 | 会话: {session_id} | 文件ID: {file_id}")
    
    return {"status": "deleted", "file_id": file_id}
