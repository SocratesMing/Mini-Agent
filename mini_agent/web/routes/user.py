"""用户管理路由.

提供用户资料的查询和更新 REST API 接口.
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from mini_agent.web.database import Database, get_database
from mini_agent.web.models import UserProfile, UpdateUserProfileRequest

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/user",
    tags=["User Management"],
)


@router.get(
    "/profile",
    response_model=UserProfile,
    summary="获取用户资料",
    description="获取当前用户的资料信息。"
)
async def get_user_profile(
    db: Annotated[Database, Depends(get_database)],
):
    """获取当前用户资料."""
    user = db.get_or_create_default_user()
    logger.info(f"获取用户资料 | 用户ID: {user.user_id} | 用户名: {user.username}")
    return UserProfile(
        user_id=user.user_id,
        username=user.username,
        organization_id=user.organization_id,
        email=user.email,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.put(
    "/profile",
    response_model=UserProfile,
    summary="更新用户资料",
    description="更新当前用户的资料信息。"
)
async def update_user_profile(
    request: UpdateUserProfileRequest,
    db: Annotated[Database, Depends(get_database)],
):
    """更新用户资料."""
    user = db.get_or_create_default_user()
    
    if request.username is not None:
        existing_user = db.get_user_by_username(request.username)
        if existing_user and existing_user.user_id != user.user_id:
            raise HTTPException(status_code=400, detail="用户名已存在")
        user.username = request.username
    
    if request.organization_id is not None:
        user.organization_id = request.organization_id
    
    if request.email is not None:
        user.email = request.email
    
    user.updated_at = datetime.now().isoformat()
    db.update_user(user)
    
    logger.info(f"更新用户资料 | 用户ID: {user.user_id} | 用户名: {user.username}")
    
    return UserProfile(
        user_id=user.user_id,
        username=user.username,
        organization_id=user.organization_id,
        email=user.email,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
