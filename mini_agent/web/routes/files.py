"""文件相关API路由."""

import logging
import os
import shutil
import asyncio
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query, Depends, UploadFile, File

from mini_agent.config import Config
from mini_agent.web.database import get_database
from mini_agent.web.dependencies import get_current_username
from mini_agent.web.utils.vector_store import get_vector_store
from mini_agent.web.service.chat_service import get_user_upload_dir, get_user_chat_dir


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/content")
async def get_file_content(file_path: str = Query(..., description="文件路径")):
    """获取文件内容."""
    try:
        p = Path(file_path)
        if not p.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        
        content = p.read_text(encoding="utf-8")
        return content
    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取文件失败: {str(e)}")


@router.get("/download")
async def download_file(file_path: str = Query(..., description="文件路径")):
    """下载文件."""
    try:
        from fastapi.responses import FileResponse
        
        logger.info(f"下载文件请求: {file_path}")
        p = Path(file_path)
        logger.info(f"文件路径解析: {p}, exists: {p.exists()}")
        if not p.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        
        return FileResponse(
            path=str(p),
            filename=p.name,
            media_type='application/octet-stream'
        )
    except Exception as e:
        logger.error(f"下载文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"下载文件失败: {str(e)}")


@router.get("/binary")
async def get_file_binary(file_path: str = Query(..., description="文件路径")):
    """获取文件二进制内容（用于PDF、图片等预览）."""
    try:
        from fastapi.responses import FileResponse
        
        logger.info(f"获取二进制文件: {file_path}")
        p = Path(file_path)
        
        if not p.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        
        suffix = p.suffix.lower()
        content_types = {
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        }
        content_type = content_types.get(suffix, 'application/octet-stream')
        
        return FileResponse(
            path=str(p),
            media_type=content_type,
            headers={
                'Cache-Control': 'no-cache'
            }
        )
    except Exception as e:
        logger.error(f"读取二进制文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取文件失败: {str(e)}")


@router.get("/session/{session_id}")
async def get_session_generated_files(session_id: str, username: str = None):
    """获取会话生成的文件列表（从workspace目录读取）."""
    if username is None:
        db = get_database()
        user = db.get_or_create_default_user()
        username = user.username
    
    session_dir = get_user_chat_dir(session_id, username)
    
    logger.info(f"检查生成文件目录: {session_dir}")
    
    def build_tree(dir_path: Path, rel_path: str = "") -> list:
        """递归构建目录树结构"""
        items = []
        try:
            for item in sorted(dir_path.iterdir()):
                if item.name.startswith('.'):
                    continue
                
                item_rel_path = str(item.relative_to(session_dir))
                
                if item.is_file():
                    items.append({
                        'id': str(item),
                        'name': item.name,
                        'path': item_rel_path,
                        'file_path': str(item),
                        'type': 'file',
                        'file_type': item.suffix.lstrip('.') if item.suffix else '',
                        'size': item.stat().st_size,
                        'created_at': item.stat().st_mtime,
                    })
                elif item.is_dir():
                    children = build_tree(item, item_rel_path)
                    items.append({
                        'id': str(item),
                        'name': item.name,
                        'path': item_rel_path,
                        'type': 'directory',
                        'children': children
                    })
        except PermissionError:
            pass
        return items
    
    files = []
    if session_dir.exists() and session_dir.is_dir():
        files = build_tree(session_dir)
    
    logger.info(f"找到 {len(files)} 个生成文件/目录")
    return files


@router.get(
    "/users/files",
    summary="获取用户所有文件",
    description="获取当前用户上传的所有文件列表（从文件系统扫描）。"
)
async def get_user_files(
    username: Annotated[str, Depends(get_current_username)],
):
    """获取当前用户上传的所有文件列表."""
    upload_dir = get_user_upload_dir(username)

    files = []
    if upload_dir.exists():
        for file_path in upload_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                file_ext = file_path.suffix[1:] if file_path.suffix else "unknown"
                files.append({
                    "id": file_path.name,
                    "filename": file_path.name,
                    "file_path": str(file_path),
                    "file_type": file_ext,
                    "size": stat.st_size,
                    "uploaded_at": stat.st_mtime,
                    "username": username,
                    "session_title": "",
                })

    logger.info(f"获取用户文件 | 用户: {username} | 用户目录: {upload_dir} | 文件总数: {len(files)}")
    return {"files": files}


@router.post(
    "/users/files/upload",
    summary="上传文件到用户目录",
    description="上传文件到用户目录并建立向量索引。"
)
async def upload_user_file(
    username: Annotated[str, Depends(get_current_username)],
    file: UploadFile = File(...),
):
    """上传文件到用户目录，返回文件信息."""
    upload_dir = get_user_upload_dir(username)

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

    logger.info(f"文件上传成功 | 文件: {file_path.name} | 用户: {username}")
    logger.info(f"[异步索引] 向量数据库索引任务已创建，将在后台执行")

    return {
        "id": file_path.name,
        "filename": file_path.name,
        "file_path": str(file_path),
        "file_type": file_type,
        "size": file_size,
        "username": username,
    }


@router.delete(
    "/users/files/{file_id}",
    summary="删除用户文件",
    description="删除用户目录下的指定文件。"
)
async def delete_user_file(
    file_id: str,
    username: Annotated[str, Depends(get_current_username)],
):
    """删除用户文件."""
    from urllib.parse import unquote
    file_id = unquote(file_id)

    upload_dir = get_user_upload_dir(username)
    file_to_delete_path = upload_dir / file_id

    logger.info(f"[删除文件] 搜索文件 | upload_dir: {upload_dir} | file_id: {file_id} | username: {username}")
    logger.info(f"[删除文件] 完整路径: {file_to_delete_path} | exists: {file_to_delete_path.exists()}")

    if not file_to_delete_path.exists():
        logger.warning(f"[删除文件] 文件不存在: {file_to_delete_path}")
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        os.remove(file_to_delete_path)
        logger.info(f"[删除文件] ✅ 文件系统删除成功: {file_to_delete_path}")
    except Exception as e:
        logger.error(f"[删除文件] ❌ 文件系统删除失败: {file_to_delete_path} | 错误: {e}")
        raise HTTPException(status_code=500, detail=f"删除文件失败: {str(e)}")

    try:
        vector_store = get_vector_store(username)
        if vector_store and vector_store.config.enabled:
            logger.info(f"[删除文件] 开始从向量数据库删除文件: {file_to_delete_path} | 用户: {username}")
            deleted = vector_store.delete_by_file(
                file_path=str(file_to_delete_path),
                username=username
            )
            if deleted:
                logger.info(f"[删除文件] ✅ 文件从向量数据库删除完成: {file_to_delete_path}")
    except Exception as e:
        logger.error(f"[删除文件] ❌ 从向量数据库删除文件失败: {file_to_delete_path} | 错误: {e}")

    logger.info(f"[删除文件] ✅ 文件删除完成: {file_id}")
    return {"status": "deleted", "filename": file_id}
