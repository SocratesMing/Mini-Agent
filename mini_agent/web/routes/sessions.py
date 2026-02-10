"""会话管理路由.

提供会话的创建、查询、更新、删除等 REST API 接口.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from mini_agent.web.database import Database, SessionModel, get_database
from mini_agent.web.models import (
    CreateSessionRequest,
    CreateSessionResponse,
    DeleteSessionResponse,
    SessionDetail,
    SessionInfo,
    UpdateTitleRequest,
)


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
    title = request.title or f"新会话 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    now = datetime.now().isoformat()
    
    session_data = SessionModel(
        session_id=session_id,
        title=title,
        messages=[],
        created_at=now,
        updated_at=now,
    )
    
    db.create_session(session_data)
    
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
    sessions = db.list_sessions(limit=limit, offset=offset)
    
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
