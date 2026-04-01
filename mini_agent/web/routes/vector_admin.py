"""向量数据库管理路由.

提供向量数据库的管理接口：查询、删除、检索等。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mini_agent.web.utils.vector_store import get_vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vector", tags=["向量数据库管理"])


class VectorSearchRequest(BaseModel):
    """向量检索请求"""
    query: str = Field(..., description="检索内容")
    username: str = Field(..., description="用户名")
    top_k: int = Field(default=5, description="返回数量")


class VectorSearchResult(BaseModel):
    """向量检索结果"""
    file_path: str
    file_name: str
    content: str
    chunk_index: int
    distance: float


class VectorDataInfo(BaseModel):
    """向量数据信息"""
    file_path: str
    file_name: str
    file_type: str
    chunk_index: int
    chunk_length: int


class VectorStatsResponse(BaseModel):
    """向量数据库统计响应"""
    total_count: int
    user_count: int
    users: list[str]


@router.get(
    "/stats",
    summary="获取向量数据库统计信息",
    description="获取向量数据库中总文档数和用户列表"
)
async def get_vector_stats():
    """获取向量数据库统计信息"""
    try:
        vector_store = get_vector_store()
        if not vector_store or not vector_store.config.enabled:
            raise HTTPException(status_code=400, detail="向量数据库未启用")

        if vector_store.collection is None:
            raise HTTPException(status_code=500, detail="向量数据库未连接")

        all_data = vector_store.collection.get()

        if not all_data or not all_data.get('ids'):
            return {
                "total_count": 0,
                "user_count": 0,
                "users": []
            }

        metadatas = all_data.get('metadatas', [])
        users = set()
        for meta in metadatas:
            if meta and meta.get('username'):
                users.add(meta['username'])

        return {
            "total_count": len(all_data['ids']),
            "user_count": len(users),
            "users": sorted(list(users))
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取向量数据库统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/users/{username}/data",
    summary="查询用户的所有向量数据",
    description="根据用户名查询该用户的所有向量数据"
)
async def get_user_vector_data(username: str):
    """查询用户的所有向量数据"""
    try:
        vector_store = get_vector_store()
        if not vector_store or not vector_store.config.enabled:
            raise HTTPException(status_code=400, detail="向量数据库未启用")

        if vector_store.collection is None:
            raise HTTPException(status_code=500, detail="向量数据库未连接")

        where_filter = {"username": {"$eq": username}}
        all_data = vector_store.collection.get(where=where_filter)

        if not all_data or not all_data.get('ids'):
            return {
                "username": username,
                "total_count": 0,
                "data": []
            }

        documents = all_data.get('documents', [])
        metadatas = all_data.get('metadatas', [])

        data_list = []
        for i, (doc, meta) in enumerate(zip(documents, metadatas)):
            if doc and meta:
                data_list.append({
                    "file_path": meta.get('file_path', ''),
                    "file_name": meta.get('file_name', ''),
                    "file_type": meta.get('file_type', ''),
                    "chunk_index": meta.get('chunk_index', i),
                    "content": doc[:500] + '...' if len(doc) > 500 else doc,
                    "chunk_length": len(doc)
                })

        return {
            "username": username,
            "total_count": len(data_list),
            "data": data_list
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询用户向量数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/users/{username}/data",
    summary="删除用户的所有向量数据",
    description="根据用户名删除该用户的所有向量数据"
)
async def delete_user_vector_data(username: str):
    """删除用户的所有向量数据"""
    try:
        vector_store = get_vector_store()
        if not vector_store or not vector_store.config.enabled:
            raise HTTPException(status_code=400, detail="向量数据库未启用")

        if vector_store.collection is None:
            raise HTTPException(status_code=500, detail="向量数据库未连接")

        where_filter = {"username": {"$eq": username}}
        existing = vector_store.collection.get(where=where_filter)

        if not existing or not existing.get('ids'):
            return {
                "username": username,
                "deleted_count": 0,
                "message": "用户没有向量数据"
            }

        doc_ids = existing['ids']
        vector_store.collection.delete(ids=doc_ids)

        logger.info(f"[向量数据库] 删除用户 {username} 的所有向量数据，共 {len(doc_ids)} 条")
        return {
            "username": username,
            "deleted_count": len(doc_ids),
            "message": f"成功删除 {len(doc_ids)} 条向量数据"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除用户向量数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/search",
    summary="检索相关文档",
    description="根据用户名和查询内容，返回最相关的文档"
)
async def search_vector_data(request: VectorSearchRequest):
    """检索相关文档"""
    try:
        vector_store = get_vector_store()
        if not vector_store or not vector_store.config.enabled:
            raise HTTPException(status_code=400, detail="向量数据库未启用")

        if vector_store.collection is None:
            raise HTTPException(status_code=500, detail="向量数据库未连接")

        logger.info(f"[向量数据库] 检索请求 | 用户: {request.username} | 查询: {request.query[:50]}...")

        where_filter = {"username": {"$eq": request.username}}
        results = vector_store.collection.query(
            query_texts=[request.query],
            n_results=request.top_k,
            where=where_filter
        )

        if not results or not results.get('documents') or not results['documents'][0]:
            return {
                "query": request.query,
                "username": request.username,
                "total_count": 0,
                "results": []
            }

        documents = results['documents'][0]
        metadatas = results.get('metadatas', [[]])[0]
        distances = results.get('distances', [[]])[0]

        result_list = []
        for i, (doc, meta, distance) in enumerate(zip(documents, metadatas, distances)):
            if doc and meta:
                result_list.append({
                    "rank": i + 1,
                    "file_path": meta.get('file_path', ''),
                    "file_name": meta.get('file_name', ''),
                    "content": doc,
                    "chunk_index": meta.get('chunk_index', 0),
                    "distance": distance,
                    "relevance_score": round(1 - distance, 4) if distance is not None else 0
                })

        logger.info(f"[向量数据库] 检索完成 | 用户: {request.username} | 返回: {len(result_list)} 条")
        return {
            "query": request.query,
            "username": request.username,
            "total_count": len(result_list),
            "results": result_list
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"检索向量数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/status",
    summary="获取向量数据库状态",
    description="获取向量数据库连接状态"
)
async def get_vector_status():
    """获取向量数据库状态"""
    try:
        vector_store = get_vector_store()
        if not vector_store:
            return {
                "enabled": False,
                "connected": False,
                "message": "向量数据库未初始化"
            }

        return {
            "enabled": vector_store.config.enabled,
            "connected": vector_store.collection is not None,
            "db_path": vector_store.config.db_path,
            "collection_name": vector_store.config.collection_name,
            "embedding_provider": vector_store.config.embedding_provider,
            "sentence_transformers_model": vector_store.config.sentence_transformers_model,
            "embedding_dimension": vector_store.config.embedding_dimension
        }

    except Exception as e:
        logger.error(f"获取向量数据库状态失败: {e}")
        return {
            "enabled": False,
            "connected": False,
            "error": str(e)
        }
