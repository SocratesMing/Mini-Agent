"""用户管理路由.

提供用户资料的查询、更新和认证 REST API 接口.
"""

import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Header

from mini_agent.web.database import Database, get_database
from mini_agent.web.models import (
    UserProfile,
    UpdateUserProfileRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    AuthResponse,
)
from mini_agent.web.utils.auth import create_access_token, get_username_from_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=AuthResponse,
    summary="注册新用户",
    description="注册一个新用户账号。"
)
async def register(
    request: RegisterRequest,
    db: Annotated[Database, Depends(get_database)],
):
    """注册新用户."""
    user = db.register_user(
        username=request.username,
        password=request.password,
        email=request.email,
    )

    if not user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    access_token = create_access_token(data={"sub": user.username})

    logger.info(f"用户注册成功 | 用户名: {user.username}")

    return AuthResponse(
        access_token=access_token,
        username=user.username,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="用户登录",
    description="使用用户名和密码登录。"
)
async def login(
    request: LoginRequest,
    db: Annotated[Database, Depends(get_database)],
):
    """用户登录."""
    user = db.verify_user_password(request.username, request.password)

    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    access_token = create_access_token(data={"sub": user.username})

    logger.info(f"用户登录成功 | 用户名: {user.username}")

    return AuthResponse(
        access_token=access_token,
        username=user.username,
    )


@router.post(
    "/reset-password",
    summary="重置密码",
    description="重置用户密码。"
)
async def reset_password(
    request: ResetPasswordRequest,
    db: Annotated[Database, Depends(get_database)],
):
    """重置用户密码."""
    user = db.get_user_by_username(request.username)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    from mini_agent.web.utils.auth import hash_password
    
    new_password_hash = hash_password(request.new_password)
    success = db.update_user_password(request.username, new_password_hash)
    
    if not success:
        raise HTTPException(status_code=500, detail="密码重置失败")
    
    logger.info(f"密码重置成功 | 用户名: {request.username}")
    
    return {"success": True, "message": "密码重置成功"}


@router.get(
    "/me",
    response_model=UserProfile,
    summary="获取当前用户资料",
    description="获取当前登录用户的资料信息。"
)
async def get_current_user_profile(
    db: Annotated[Database, Depends(get_database)],
    username: str = None,
):
    """获取当前用户资料（通过 username 参数）."""
    if not username:
        user = db.get_or_create_default_user()
    else:
        user = db.get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

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
    username: str = None,
):
    """更新用户资料."""
    if not username:
        user = db.get_or_create_default_user()
    else:
        user = db.get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

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


profile_router = APIRouter(
    prefix="/api/user",
    tags=["User Profile"],
)


@profile_router.get(
    "/profile",
    response_model=UserProfile,
    summary="获取用户资料",
    description="获取当前登录用户的资料信息。"
)
async def get_user_profile(
    db: Annotated[Database, Depends(get_database)],
    authorization: Annotated[Optional[str], Header()] = None,
):
    """获取用户资料."""
    username = None
    if authorization:
        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        username = get_username_from_token(token)
    
    if not username:
        user = db.get_or_create_default_user()
    else:
        user = db.get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

    logger.info(f"获取用户资料 | 用户ID: {user.user_id} | 用户名: {user.username}")
    return UserProfile(
        user_id=user.user_id,
        username=user.username,
        organization_id=user.organization_id,
        email=user.email,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
