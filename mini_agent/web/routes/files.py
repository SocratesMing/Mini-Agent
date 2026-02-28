"""文件相关API路由."""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

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
    import logging
    logger = logging.getLogger(__name__)
    
    from pathlib import Path
    
    if username is None:
        from mini_agent.web.database import Database
        db = Database()
        user = db.get_or_create_default_user()
        username = user.username
    
    project_root = Path(__file__).parent.parent.parent
    workspace = project_root / "workspace"
    
    safe_username = "".join(c for c in username if c.isalnum() or c in ('_', '-')) or "user"
    session_dir = workspace / safe_username / session_id
    
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
