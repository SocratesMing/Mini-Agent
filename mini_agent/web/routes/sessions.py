"""会话管理路由.

提供会话的创建、查询、更新、删除等 REST API 接口.
"""

import asyncio
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response

from mini_agent.config import Config
from mini_agent.web.database import Database, SessionModel, get_database
from mini_agent.web.dependencies import get_current_username
from mini_agent.web.models import (
    CreateSessionRequest,
    CreateSessionResponse,
    DeleteSessionResponse,
    SessionDetail,
    SessionInfo,
    UpdateTitleRequest,
)
from mini_agent.web.utils.vector_store import get_vector_store

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/sessions",
    tags=["Session Management"],
)


@router.get(
    "/files/{filename}/preview",
    summary="预览文件",
    description="预览支持的文件类型（图片、PDF、文本等）"
)
async def preview_file(filename: str):
    """预览文件内容"""
    from urllib.parse import unquote
    filename = unquote(filename)
    logger.info(f"[预览] 请求文件: {filename}")

    user_dir = Path("workspace/users")
    file_path = None
    try:
        for user_folder in user_dir.iterdir():
            if user_folder.is_dir() and (user_folder / "files").is_dir():
                candidate = user_folder / "files" / filename
                logger.info(f"[预览] 检查路径: {candidate} (exists={candidate.exists()})")
                if candidate.exists():
                    file_path = candidate
                    logger.info(f"[预览] 找到文件: {file_path}")
                    break
        else:
            logger.warning(f"[预览] 遍历完成，未找到文件: {filename}")
    except Exception as e:
        logger.error(f"[预览] 遍历用户目录出错: {e}")

    if not file_path or not file_path.exists():
        logger.warning(f"[预览] 文件不存在: {filename}")
        raise HTTPException(status_code=404, detail="文件不存在")

    ext = file_path.suffix.lower()
    logger.info(f"[预览] 文件扩展名: {ext}")

    direct_preview_types = {
        '.pdf': 'application/pdf',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.webp': 'image/webp',
        '.svg': 'image/svg+xml',
        '.ico': 'image/x-icon',
    }

    if ext in direct_preview_types:
        file_content = file_path.read_bytes()
        return Response(
            content=file_content,
            media_type=direct_preview_types[ext]
        )

    text_preview_types = {'.txt', '.json', '.xml', '.csv', '.md'}
    if ext in text_preview_types:
        return FileResponse(
            path=str(file_path),
            media_type='text/plain',
            filename=filename
        )

    binary_types = {'.docx', '.xlsx', '.pptx'}
    if ext in binary_types:
        return FileResponse(
            path=str(file_path),
            filename=filename
        )

    parseable_types = {'md', 'html', 'htm', 'doc', 'xls', 'ppt', 'pptx'}
    if ext.lstrip('.') in parseable_types:
        from mini_agent.web.utils.file_parser import FileParser
        logger.info(f"[预览] 开始解析文件: {file_path}, 类型: {ext}")
        content = FileParser.extract_content(str(file_path), ext)
        logger.info(f"[预览] 解析结果长度: {len(content) if content else 0}")
        if content:
            media_type = 'text/markdown; charset=utf-8' if ext.lstrip('.') == 'md' else 'text/plain; charset=utf-8'
            return Response(content=content.encode('utf-8'), media_type=media_type)
        else:
            logger.warning(f"[预览] 文件解析返回空内容: {file_path}")
            return Response(content="文件内容为空或解析失败".encode('utf-8'), media_type='text/plain; charset=utf-8')

    raise HTTPException(
        status_code=415,
        detail=f"不支持预览此文件类型: {ext}"
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
    session_id = str(uuid.uuid4())
    title = request.title if request.title else "未命名会话"
    username = request.username or ""
    now = datetime.now().isoformat()
    
    logger.info(f"创建会话 | ID: {session_id} | 标题: {title} | 用户: {username}")
    
    session_data = SessionModel(
        session_id=session_id,
        title=title,
        messages=[],
        created_at=now,
        updated_at=now,
        username=username,
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
    username: Annotated[Optional[str], Query(description="用户名过滤")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="返回数量限制")] = 50,
    offset: Annotated[int, Query(ge=0, description="偏移量")] = 0,
):
    """从 SQLite 数据库获取会话列表."""
    logger.info(f"查询会话列表 | username: {username} | limit: {limit} | offset: {offset}")
    
    sessions = db.list_sessions(limit=limit, offset=offset, username=username)
    
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
    username: Annotated[str, Depends(get_current_username)],
):
    """获取当前用户上传的所有文件列表（从文件系统扫描）."""
    safe_username = "".join(c for c in username if c.isalnum() or c in ('_', '-')) or "user"
    
    env_workspace = Config.get_workspace_dir()
    if env_workspace:
        workspace = Path(env_workspace)
    else:
        workspace = Path("workspace")
    
    user_dir = workspace / "users" / safe_username / "files"
    
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
    username: Annotated[str, Depends(get_current_username)],
):
    """下载文件."""
    from fastapi.responses import FileResponse
    
    safe_username = "".join(c for c in username if c.isalnum() or c in ('_', '-')) or "user"
    
    env_workspace = Config.get_workspace_dir()
    if env_workspace:
        workspace = Path(env_workspace)
    else:
        workspace = Path("workspace")
    
    user_dir = workspace / "users" / safe_username / "files"
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
    username: Annotated[str, Depends(get_current_username)],
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
    
    env_workspace = Config.get_workspace_dir()
    if env_workspace:
        workspace = Path(env_workspace)
    else:
        project_root = Path(__file__).parent.parent.parent
        workspace = project_root / "workspace"
    
    safe_username = "".join(c for c in username if c.isalnum() or c in ('_', '-')) or "user"
    session_workspace = workspace / "users" / safe_username / session_id
    
    if session_workspace.exists() and session_workspace.is_dir():
        try:
            shutil.rmtree(session_workspace)
            logger.info(f"删除会话工作目录 | 会话: {session_id} | 路径: {session_workspace}")
        except Exception as e:
            logger.error(f"删除会话工作目录失败 | 会话: {session_id} | 路径: {session_workspace} | 错误: {e}")
    
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
    username: Annotated[str, Depends(get_current_username)],
    file: UploadFile = File(...),
):
    """上传文件到会话目录，返回文件路径供 AI 读取."""
    safe_username = "".join(c for c in username if c.isalnum() or c in ('_', '-')) or "user"

    env_workspace = Config.get_workspace_dir()
    if env_workspace:
        workspace = Path(env_workspace)
    else:
        workspace = Path("workspace")

    upload_dir = workspace / "users" / safe_username / "files"
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

    session = db.get_session(session_id) if session_id != 'default' else None
    actual_session_id = session.session_id if session else None

    if actual_session_id:
        file_id = db.add_session_file(
            session_id=actual_session_id,
            filename=file_path.name,
            file_path=str(file_path),
            file_type=file_type,
            size=file_size,
            username=username
        )
    else:
        logger.info(f"跳过数据库记录 | session_id={session_id} 用于文件: {file_path.name}")
        file_id = None

    async def background_index_file(file_path_str: str, file_name: str, file_type: str, user: str):
        """后台异步索引文件到向量数据库"""
        try:
            await asyncio.sleep(0.5)
            vector_store = get_vector_store(user)
            if vector_store and vector_store.config.enabled:
                logger.info(f"[后台索引] 开始索引文件: {file_name} | 用户: {user} | 类型: {file_type}")
                chunks_count = vector_store.add_file(
                    file_path=file_path_str,
                    username=user,
                    file_type=file_type
                )
                if chunks_count > 0:
                    logger.info(f"[后台索引] ✅ 文件索引完成: {file_name} | chunks: {chunks_count}")
                else:
                    logger.warning(f"[后台索引] ⚠️ 文件索引完成但未添加chunks: {file_name}")
            else:
                logger.info(f"[后台索引] 向量数据库未启用，跳过文件索引: {file_name}")
        except Exception as e:
            logger.error(f"[后台索引] ❌ 文件索引失败: {file_name} | 错误: {e}")

    asyncio.create_task(background_index_file(str(file_path), file_path.name, file_type, username))

    logger.info(f"文件上传成功 | 会话: {session_id} | 文件: {file_path.name} | 用户: {username} | ID: {file_id}")
    logger.info(f"[异步索引] 向量数据库索引任务已创建，将在后台执行")

    return {
        "id": file_id or file_path.name,
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
    file_id: str,
    db: Annotated[Database, Depends(get_database)],
    username: Annotated[str, Depends(get_current_username)],
):
    """删除会话文件并移除文件系统中的文件."""
    from urllib.parse import unquote
    file_id = unquote(file_id)

    safe_username = "".join(c for c in username if c.isalnum() or c in ('_', '-')) or "user"
    
    env_workspace = Config.get_workspace_dir()
    if env_workspace:
        workspace = Path(env_workspace)
    else:
        workspace = Path("workspace")

    if session_id == "files":
        files = []
        user_dir = workspace / "users" / safe_username / "files"
        logger.info(f"[删除文件] 搜索文件 | session_id: {session_id} | user_dir: {user_dir} | file_id: {file_id} | safe_username: {safe_username} | username: {username}")
        logger.info(f"[删除文件] 完整路径: {user_dir / file_id} | exists: {(user_dir / file_id).exists()}")
        if user_dir.exists():
            logger.info(f"[删除文件] 用户目录存在，遍历文件...")
            actual_files = list(user_dir.iterdir())
            logger.info(f"[删除文件] 目录中的文件列表: {[fp.name for fp in actual_files]}")
            for fp in user_dir.iterdir():
                logger.info(f"[删除文件] 比较: fp.name={fp.name} == file_id={file_id} ? {fp.name == file_id}")
                if fp.is_file() and fp.name == file_id:
                    logger.info(f"[删除文件] 找到匹配文件: {fp}")
                    file_to_delete = {
                        "id": fp.name,
                        "filename": fp.name,
                        "file_path": str(fp),
                        "file_type": fp.suffix[1:] if fp.suffix else "unknown",
                        "size": fp.stat().st_size,
                        "username": safe_username,
                    }
                    files.append(file_to_delete)
        else:
            logger.warning(f"[删除文件] 用户目录不存在: {user_dir}")

        if not files:
            logger.warning(f"[删除文件] 文件不存在 | file_id: {file_id} | 搜索目录: {user_dir}")
            raise HTTPException(status_code=404, detail="文件不存在")
        file_to_delete = files[0]
    else:
        session = db.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")

        files = db.get_session_files(session_id)
        file_to_delete = None
        if file_id.isdigit():
            file_to_delete = next((f for f in files if f['id'] == int(file_id)), None)
        else:
            file_to_delete = next((f for f in files if f['filename'] == file_id), None)

        if not file_to_delete:
            raise HTTPException(status_code=404, detail="文件不存在")

    file_path = file_to_delete['file_path']
    file_username = file_to_delete.get('username', safe_username)
    db_id = file_to_delete.get('id')

    async def background_delete(file_path: str, file_username: str, db_id, session_id: str, filename: str):
        """后台异步删除文件"""
        try:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"[后台删除] 文件系统删除成功 | 文件: {file_path}")
                except Exception as e:
                    logger.error(f"[后台删除] 文件系统删除失败 | 文件: {file_path} | 错误: {e}")
            else:
                logger.warning(f"[后台删除] 文件不存在 | 文件: {file_path}")

            try:
                vector_store = get_vector_store(file_username)
                if vector_store and vector_store.config.enabled:
                    logger.info(f"[后台删除] 开始从向量数据库删除文件: {file_path} | 用户: {file_username}")
                    deleted = vector_store.delete_by_file(
                        file_path=file_path,
                        username=file_username
                    )
                    if deleted:
                        logger.info(f"[后台删除] ✅ 文件从向量数据库删除完成: {file_path}")
            except Exception as e:
                logger.error(f"[后台删除] ❌ 从向量数据库删除文件失败: {file_path} | 错误: {e}")

            if db_id and isinstance(db_id, int):
                try:
                    if not db.delete_session_file(db_id):
                        logger.warning(f"[后台删除] 数据库记录删除失败 | 文件ID: {db_id}")
                    else:
                        logger.info(f"[后台删除] 数据库记录删除成功 | 会话: {session_id} | 文件ID: {db_id}")
                except Exception as e:
                    logger.error(f"[后台删除] 数据库记录删除失败 | 文件ID: {db_id} | 错误: {e}")

            logger.info(f"[后台删除] ✅ 文件删除完成 | 文件: {filename}")
        except Exception as e:
            logger.error(f"[后台删除] ❌ 文件删除失败 | 文件: {filename} | 错误: {e}")

    asyncio.create_task(background_delete(
        file_path=file_path,
        file_username=file_username,
        db_id=db_id,
        session_id=session_id,
        filename=file_to_delete.get('filename', file_id)
    ))

    return {"status": "deleted", "file_id": file_to_delete.get('filename', file_id)}
