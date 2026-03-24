"""向量数据库模块 - 使用 Chroma + Embedding 实现本地 RAG"""

import logging
import hashlib
import requests
import time
from pathlib import Path
from typing import Optional

from mini_agent.web.utils.file_parser import FileParser

logger = logging.getLogger(__name__)


class VectorStoreConfig:
    """向量数据库配置"""

    def __init__(self, config_dict: dict = None):
        if config_dict is None:
            config_dict = {}

        self.enabled = config_dict.get("enabled", False) if isinstance(config_dict, dict) else getattr(config_dict, "enabled", False)
        self.db_path = config_dict.get("db_path", "./data/chroma_db") if isinstance(config_dict, dict) else getattr(config_dict, "db_path", "./data/chroma_db")
        self.collection_name = config_dict.get("collection_name", "mini_agent_docs") if isinstance(config_dict, dict) else getattr(config_dict, "collection_name", "mini_agent_docs")
        self.embedding_provider = config_dict.get("embedding_provider", "ollama") if isinstance(config_dict, dict) else getattr(config_dict, "embedding_provider", "ollama")
        self.ollama_model = config_dict.get("ollama_model", "nomic-embed-text") if isinstance(config_dict, dict) else getattr(config_dict, "ollama_model", "nomic-embed-text")
        self.embedding_dimension = config_dict.get("embedding_dimension", 768) if isinstance(config_dict, dict) else getattr(config_dict, "embedding_dimension", 768)
        self.batch_size = config_dict.get("batch_size", 100) if isinstance(config_dict, dict) else getattr(config_dict, "batch_size", 100)
        self.ollama_base_url = config_dict.get("ollama_base_url", "http://localhost:11434") if isinstance(config_dict, dict) else getattr(config_dict, "ollama_base_url", "http://localhost:11434")
        self.zhipu_api_key = config_dict.get("zhipu_api_key", "") if isinstance(config_dict, dict) else getattr(config_dict, "zhipu_api_key", "")
        self.zhipu_model = config_dict.get("zhipu_model", "embedding-3") if isinstance(config_dict, dict) else getattr(config_dict, "zhipu_model", "embedding-3")
        self.search_top_k = config_dict.get("search_top_k", 10) if isinstance(config_dict, dict) else getattr(config_dict, "search_top_k", 10)
        self.similarity_threshold = config_dict.get("similarity_threshold", 0.5) if isinstance(config_dict, dict) else getattr(config_dict, "similarity_threshold", 0.5)


class VectorStore:
    """向量数据库管理器 - 使用 Chroma + Ollama Embedding"""

    _instance: Optional["VectorStore"] = None

    def __init__(self, config: VectorStoreConfig = None):
        self.config = config or VectorStoreConfig()
        self.client = None
        self.collection = None
        self._embedding_function = None

        if self.config.enabled:
            self._connect()

    @classmethod
    def get_instance(cls) -> "VectorStore":
        """获取单例实例"""
        if cls._instance is None:
            config = cls._load_config_from_app_config()
            logger.info(f"[向量数据库] 加载配置 | enabled: {config.enabled} | db_path: {config.db_path} | ollama_model: {config.ollama_model}")
            cls._instance = cls(config)
            logger.info(f"[向量数据库] 配置详情 | enabled: {cls._instance.config.enabled}")
        return cls._instance

    @classmethod
    def _load_config_from_app_config(cls) -> VectorStoreConfig:
        """从应用配置加载向量数据库配置"""
        try:
            from mini_agent.config import Config
            config_path = Config.get_default_config_path()
            logger.info(f"[向量数据库] 加载配置文件: {config_path}")
            app_config = Config.load()
            vector_config = app_config.vector_store
            logger.info(f"[向量数据库] 向量配置已加载 | enabled: {vector_config.enabled} | model: {vector_config.ollama_model}")
            return vector_config
        except Exception as e:
            logger.warning(f"[向量数据库] 加载配置失败: {e}")
            import traceback
            logger.warning(f"[向量数据库] 详细错误: {traceback.format_exc()}")
            return VectorStoreConfig()

    def _connect(self):
        """连接到 Chroma 向量数据库"""
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            db_path = Path(self.config.db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

            logger.info(f"初始化 Chroma 数据库: {self.config.db_path}")

            provider = getattr(self.config, 'embedding_provider', 'ollama')
            if provider == 'zhipu':
                logger.info(f"[向量数据库] 使用智谱 Embedding | model: {self.config.zhipu_model} | dimension: {self.config.embedding_dimension}")
                self._embedding_function = None
                self._test_zhipu_connection()
            else:
                logger.info(f"[向量数据库] 使用 Ollama Embedding | url: {self.config.ollama_base_url} | model: {self.config.ollama_model}")
                self._embedding_function = embedding_functions.OllamaEmbeddingFunction(
                    url=f"{self.config.ollama_base_url}/api/embeddings",
                    model_name=self.config.ollama_model
                )
                self._test_ollama_connection()

            self.client = chromadb.PersistentClient(path=str(db_path))

            self.collection = self.client.get_or_create_collection(
                name=self.config.collection_name,
                embedding_function=self._embedding_function,
                metadata={"hnsw:space": "cosine"}
            )

            logger.info("Chroma 数据库初始化成功")

        except ImportError:
            logger.error("请安装 chromadb: pip install chromadb")
            self.config.enabled = False
        except Exception as e:
            logger.error(f"初始化 Chroma 数据库失败: {e}")
            self.config.enabled = False

    def _test_ollama_connection(self):
        """测试 Ollama 连接"""
        try:
            response = requests.post(
                f"{self.config.ollama_base_url}/api/embeddings",
                json={"model": self.config.ollama_model, "prompt": "test"},
                timeout=10
            )
            if response.status_code == 200:
                logger.info(f"[向量数据库] ✅ Ollama 连接成功")
            else:
                logger.warning(f"[向量数据库] ⚠️ Ollama 返回异常状态码: {response.status_code}")
        except Exception as e:
            logger.error(f"[向量数据库] ❌ Ollama 连接失败: {e}")

    def _test_zhipu_connection(self):
        """测试智谱 API 连接"""
        try:
            from zai import ZhipuAiClient
            client = ZhipuAiClient(api_key=self.config.zhipu_api_key)
            response = client.embeddings.create(
                model=self.config.zhipu_model,
                input=["测试连接"]
            )
            if response and response.data:
                logger.info(f"[向量数据库] ✅ 智谱 API 连接成功 | embedding dimension: {len(response.data[0].embedding)}")
            else:
                logger.warning(f"[向量数据库] ⚠️ 智谱 API 返回异常")
        except Exception as e:
            logger.error(f"[向量数据库] ❌ 智谱 API 连接失败: {e}")

    def _compute_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """预先计算文本的 embeddings

        Args:
            texts: 文本列表

        Returns:
            embeddings 列表
        """
        provider = getattr(self.config, 'embedding_provider', 'ollama')

        if provider == 'zhipu':
            return self._compute_embeddings_batch_zhipu(texts)

        import concurrent.futures

        total = len(texts)
        results = [None] * total
        completed = 0

        def compute_single_embedding(idx: int, text: str):
            for attempt in range(3):
                try:
                    response = self._compute_ollama_embedding(text)
                    if response:
                        return idx, response
                except Exception as e:
                    if attempt == 2:
                        logger.error(f"[向量数据库] Embedding 计算失败: {e}")
                        return idx, [0.0] * self.config.embedding_dimension
                time.sleep(0.2)
            return idx, [0.0] * self.config.embedding_dimension

        max_workers = 3

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(compute_single_embedding, i, text): i for i, text in enumerate(texts)}

            for future in concurrent.futures.as_completed(futures):
                idx, embedding = future.result()
                results[idx] = embedding
                completed += 1
                if completed % 10 == 0 or completed == total:
                    logger.info(f"[向量数据库] Embedding进度: {completed}/{total}")

        return results

    def _compute_embeddings_batch_zhipu(self, texts: list[str]) -> list[list[float]]:
        """使用智谱批量计算 embedding"""
        import concurrent.futures

        total = len(texts)
        results = [None] * total
        completed = 0

        batch_size = 10

        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            batch_num = i // batch_size + 1
            batch_count = (total + batch_size - 1) // batch_size

            for attempt in range(3):
                try:
                    batch_embeddings = self._compute_zhipu_embeddings_batch(batch)
                    if batch_embeddings and len(batch_embeddings) == len(batch):
                        for j, emb in enumerate(batch_embeddings):
                            results[i + j] = emb
                        break
                except Exception as e:
                    if attempt == 2:
                        logger.error(f"[向量数据库] 智谱批量Embedding失败: {e}")
                    time.sleep(1)

            completed = min(i + batch_size, total)
            if batch_num % 5 == 0 or batch_num == batch_count or completed == total:
                logger.info(f"[向量数据库] Embedding进度: {completed}/{total}")

        fallback_count = sum(1 for r in results if r is None)
        if fallback_count > 0:
            logger.warning(f"[向量数据库] {fallback_count} 个文本Embedding失败，使用零向量")

        for i, r in enumerate(results):
            if r is None:
                results[i] = [0.0] * self.config.embedding_dimension

        return results

    def _compute_ollama_embedding(self, text: str) -> list[float]:
        """使用 Ollama 计算 embedding"""
        response = requests.post(
            f"{self.config.ollama_base_url}/api/embeddings",
            json={
                "model": self.config.ollama_model,
                "prompt": text
            },
            timeout=60
        )
        if response.status_code == 200:
            return response.json().get("embedding", [])
        return None

    def _compute_zhipu_embedding(self, text: str) -> list[float]:
        """使用智谱 SDK 计算 embedding"""
        try:
            from zai import ZhipuAiClient
        except ImportError:
            raise ImportError("请安装智谱 SDK: pip install zai-sdk")

        api_key = getattr(self.config, 'zhipu_api_key', '')
        model = getattr(self.config, 'zhipu_model', 'embedding-3')

        if not api_key:
            raise ValueError("智谱 API key 未配置")

        client = ZhipuAiClient(api_key=api_key)
        response = client.embeddings.create(
            model=model,
            input=[text]
        )

        if response and response.data and len(response.data) > 0:
            return response.data[0].embedding
        return None

    def _compute_zhipu_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """使用智谱 SDK 批量计算 embedding"""
        try:
            from zai import ZhipuAiClient
        except ImportError:
            raise ImportError("请安装智谱 SDK: pip install zai-sdk")

        api_key = getattr(self.config, 'zhipu_api_key', '')
        model = getattr(self.config, 'zhipu_model', 'embedding-3')

        if not api_key:
            raise ValueError("智谱 API key 未配置")

        client = ZhipuAiClient(api_key=api_key)
        response = client.embeddings.create(
            model=model,
            input=texts
        )

        embeddings = []
        if response and response.data:
            for item in response.data:
                embeddings.append(item.embedding)
        return embeddings

    def _generate_doc_id(self, file_path: str, chunk_index: int) -> str:
        """生成文档 ID"""
        unique_str = f"{file_path}_{chunk_index}"
        return hashlib.md5(unique_str.encode()).hexdigest()

    def _generate_chunk_id(self, file_path: str, chunk_index: int) -> str:
        """生成 chunk ID"""
        return self._generate_doc_id(file_path, chunk_index)

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """使用 RecursiveCharacterTextSplitter 将文本分割成块

        Args:
            text: 原始文本
            chunk_size: 每个块的字符数
            overlap: 块之间的重叠字符数

        Returns:
            文本块列表
        """
        if not text or not text.strip():
            return []

        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            logger.info(f"[向量数据库] 初始化 RecursiveCharacterTextSplitter | chunk_size: {chunk_size}, overlap: {overlap}")

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=overlap,
                length_function=len,
                separators=["\n\n", "\n", "。", "！", "？", " ", ""]
            )

            logger.info(f"[向量数据库] 开始分割文本 | 原文长度: {len(text)} 字符")
            chunks = text_splitter.split_text(text)
            logger.info(f"[向量数据库] 文本分割完成 | 生成 {len(chunks)} 个块")

            for i, chunk in enumerate(chunks[:3]):
                logger.debug(f"[向量数据库] Chunk {i}: {chunk[:50]}...")

            return chunks

        except ImportError:
            logger.warning(f"[向量数据库] langchain-text-splitters 未安装，使用简单分块")
            return self._simple_chunk_text(text, chunk_size, overlap)
        except Exception as e:
            logger.error(f"[向量数据库] 文本分割失败: {e}")
            return self._simple_chunk_text(text, chunk_size, overlap)

    def _simple_chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """简单的文本分块方法（备用）"""
        if not text or not text.strip():
            return []

        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = start + chunk_size

            if end >= text_length:
                chunks.append(text[start:].strip())
                break

            chunk = text[start:end]
            newline_idx = chunk.rfind('\n')
            if newline_idx > chunk_size // 2:
                end = start + newline_idx + 1

            chunks.append(text[start:end].strip())
            start = end - overlap

        return [c for c in chunks if c.strip()]

    def _clean_text(self, text: str) -> str:
        """清洗文本：去除无关字符、格式统一

        Args:
            text: 原始文本

        Returns:
            清洗后的文本
        """
        if not text:
            return ""

        import re

        original_length = len(text)
        logger.info(f"[向量数据库] 开始清洗文本 | 原始长度: {original_length} 字符")

        cleaned = text

        cleaned = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', cleaned)

        cleaned = re.sub(r'https?://\S+', '[链接]', cleaned)

        cleaned = re.sub(r'\[\[(\d+)\]\]', r'[\1]', cleaned)

        cleaned = re.sub(r'(\w+)\s{3,}', r'\1  ', cleaned)

        lines = cleaned.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line:
                cleaned_lines.append(line)
        cleaned = '\n'.join(cleaned_lines)

        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        logger.info(f"[向量数据库] 文本清洗完成 | 清洗后长度: {len(cleaned)} 字符 | 移除: {original_length - len(cleaned)} 字符")

        return cleaned

    def add_file(self, file_path: str, username: str, file_type: str = "") -> int:
        """添加文件到向量数据库 - 完整的 RAG 流程

        Args:
            file_path: 文件路径
            username: 用户名
            file_type: 文件类型 (pdf, docx, xlsx, etc.)

        Returns:
            添加的 chunk 数量
        """
        logger.info(f"=" * 60)
        logger.info(f"[向量数据库] 开始处理文件")
        logger.info(f"[向量数据库] 文件路径: {file_path}")
        logger.info(f"[向量数据库] 用户名: {username}")
        logger.info(f"[向量数据库] 文件类型: {file_type}")
        logger.info(f"=" * 60)

        if not self.config.enabled:
            logger.info(f"[向量数据库] 向量数据库未启用，跳过文件添加")
            return 0

        if self.collection is None:
            logger.error(f"[向量数据库] 向量数据库未连接")
            return 0

        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                logger.error(f"[向量数据库] 文件不存在: {file_path}")
                return 0

            file_size = file_path_obj.stat().st_size
            logger.info(f"[向量数据库] 文件大小: {file_size} bytes")

            logger.info(f"[向量数据库] 步骤1/5: 文档加载")
            content = self._extract_file_content(file_path, file_type)
            if not content:
                logger.warning(f"[向量数据库] 无法提取文件内容: {file_path}")
                return 0
            logger.info(f"[向量数据库] 文档加载完成 | 原始内容长度: {len(content)} 字符")

            logger.info(f"[向量数据库] 步骤2/5: 文本清洗")
            content = self._clean_text(content)
            if not content:
                logger.warning(f"[向量数据库] 清洗后内容为空: {file_path}")
                return 0
            logger.info(f"[向量数据库] 文本清洗完成 | 清洗后长度: {len(content)} 字符")

            logger.info(f"[向量数据库] 步骤3/5: 文本分块 (RecursiveCharacterTextSplitter)")
            logger.info(f"[向量数据库] 分块参数 | chunk_size: 500, overlap: 50")
            chunks = self._chunk_text(content, chunk_size=500, overlap=50)
            if not chunks:
                logger.warning(f"[向量数据库] 文件内容分块后为空: {file_path}")
                return 0
            logger.info(f"[向量数据库] 文本分块完成 | 生成 {len(chunks)} 个块")

            if len(chunks) <= 5:
                for i, chunk in enumerate(chunks):
                    logger.debug(f"[向量数据库] Chunk {i} (长度 {len(chunk)}): {chunk[:80]}...")
            else:
                logger.debug(f"[向量数据库] 前3个Chunk预览:")
                for i, chunk in enumerate(chunks[:3]):
                    logger.debug(f"[向量数据库]   Chunk {i} (长度 {len(chunk)}): {chunk[:80]}...")

            logger.info(f"[向量数据库] 步骤4/5: 向量化文本块")
            provider = getattr(self.config, 'embedding_provider', 'ollama')
            if provider == 'zhipu':
                logger.info(f"[向量数据库] 使用智谱 Embedding | model: {self.config.zhipu_model}")
            else:
                logger.info(f"[向量数据库] 使用 Ollama Embedding | model: {self.config.ollama_model} | url: {self.config.ollama_base_url}")

            ids = []
            documents = []
            metadatas = []

            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue

                chunk_id = self._generate_chunk_id(file_path, i)

                ids.append(chunk_id)
                documents.append(chunk)
                metadatas.append({
                    "file_path": str(file_path),
                    "file_name": file_path_obj.name,
                    "file_type": file_type or file_path_obj.suffix.lstrip('.'),
                    "username": username,
                    "chunk_index": i,
                    "chunk_length": len(chunk)
                })

                if (i + 1) % 10 == 0:
                    logger.info(f"[向量数据库] 已处理 {i + 1}/{len(chunks)} 个块")

            logger.info(f"[向量数据库] 预先计算 {len(documents)} 个文本块的 embeddings...")

            embeddings = self._compute_embeddings_batch(documents)

            if not embeddings or len(embeddings) == 0:
                logger.error(f"[向量数据库] Embedding 计算失败")
                return 0

            logger.info(f"[向量数据库] Embedding 计算完成 | 有效向量: {len([e for e in embeddings if any(e)])}/{len(embeddings)}")

            logger.info(f"[向量数据库] 步骤5/5: 存储到向量数据库 (Chroma)")
            logger.info(f"[向量数据库] 准备插入 {len(ids)} 个文档")

            if ids:
                batch_size = getattr(self.config, 'batch_size', 50) or 50
                total_batches = (len(ids) + batch_size - 1) // batch_size
                total_inserted = 0

                logger.info(f"[向量数据库] 开始分批插入 | 每批 {batch_size} 个 | 总共 {total_batches} 批")

                for batch_idx in range(total_batches):
                    start_idx = batch_idx * batch_size
                    end_idx = min(start_idx + batch_size, len(ids))
                    batch_ids = ids[start_idx:end_idx]
                    batch_docs = documents[start_idx:end_idx]
                    batch_metas = metadatas[start_idx:end_idx]
                    batch_embeddings = embeddings[start_idx:end_idx]

                    batch_num = batch_idx + 1
                    max_retries = 3
                    retry_delay = 2

                    for attempt in range(1, max_retries + 1):
                        try:
                            self.collection.add(
                                ids=batch_ids,
                                documents=batch_docs,
                                metadatas=batch_metas,
                                embeddings=batch_embeddings
                            )
                            total_inserted += len(batch_ids)
                            logger.info(f"[向量数据库] 批次 {batch_num}/{total_batches} 插入成功 | 已插入 {total_inserted}/{len(ids)}")
                            break
                        except Exception as add_error:
                            error_str = str(add_error).lower()
                            is_timeout = "timeout" in error_str or "timed out" in error_str
                            if attempt < max_retries and is_timeout:
                                logger.warning(f"[向量数据库] 批次 {batch_num} 超时，第 {attempt}/{max_retries} 次重试，{retry_delay}秒后重试...")
                                import time
                                time.sleep(retry_delay)
                                retry_delay *= 2
                            else:
                                logger.error(f"[向量数据库] 批次 {batch_num} 插入失败: {add_error}")
                                raise

                    import time
                    time.sleep(0.3)

                logger.info(f"[向量数据库] 插入完成 | 文件: {file_path}")
                logger.info(f"[向量数据库] 索引完成 | 总chunk数: {total_inserted}")
                logger.info(f"=" * 60)
                logger.info(f"[向量数据库] ✅ 文件索引成功!")
                logger.info(f"=" * 60)
                return total_inserted

            return 0

        except Exception as e:
            logger.error(f"[向量数据库] 添加文件到向量数据库失败: {e}")
            import traceback
            logger.error(f"[向量数据库] 详细错误: {traceback.format_exc()}")
            return 0

    def _extract_file_content(self, file_path: str, file_type: str = "") -> str:
        """从文件中提取文本内容

        Args:
            file_path: 文件路径
            file_type: 文件类型

        Returns:
            提取的文本内容
        """
        return FileParser.extract_content(file_path, file_type)

    def delete_file(self, file_path: str, username: str = "") -> int:
        """从向量数据库中删除文件

        Args:
            file_path: 文件路径
            username: 用户名（可选，用于精确匹配）

        Returns:
            删除的 chunk 数量
        """
        logger.info(f"[向量数据库] 开始删除文件: {file_path}, 用户: {username}")

        if not self.config.enabled:
            logger.info(f"[向量数据库] 向量数据库未启用，跳过删除")
            return 0

        if self.collection is None:
            logger.error(f"[向量数据库] 向量数据库未连接")
            return 0

        try:
            path_variations = [
                file_path,
                file_path.replace('/', '\\'),
                file_path.replace('\\', '/'),
                Path(file_path).resolve().as_posix() if Path(file_path).is_absolute() else file_path,
            ]
            path_variations = list(set(path_variations))

            total_deleted = 0

            for path_to_delete in path_variations:
                if username:
                    where_filter = {
                        "$and": [
                            {"file_path": {"$eq": path_to_delete}},
                            {"username": {"$eq": username}}
                        ]
                    }
                else:
                    where_filter = {"file_path": {"$eq": path_to_delete}}

                logger.info(f"[向量数据库] 尝试删除路径: {path_to_delete}")
                existing = self.collection.get(where=where_filter)

                if existing and existing.get('ids'):
                    doc_ids = existing['ids']
                    logger.info(f"[向量数据库] 找到 {len(doc_ids)} 个文档待删除 (路径: {path_to_delete})")
                    self.collection.delete(ids=doc_ids)
                    total_deleted += len(doc_ids)
                    logger.info(f"[向量数据库] 已删除 {len(doc_ids)} 个文档 (路径: {path_to_delete})")

            if total_deleted == 0:
                file_name = Path(file_path).name
                logger.info(f"[向量数据库] 精确路径未找到，尝试按文件名删除: {file_name}")
                where_filter = {"file_name": {"$eq": file_name}}
                if username:
                    where_filter["username"] = {"$eq": username}
                existing = self.collection.get(where=where_filter)
                if existing and existing.get('ids'):
                    doc_ids = existing['ids']
                    logger.info(f"[向量数据库] 按文件名找到 {len(doc_ids)} 个文档待删除")
                    self.collection.delete(ids=doc_ids)
                    total_deleted += len(doc_ids)

            logger.info(f"[向量数据库] 文件删除完成: {file_path}, 总删除chunk数量: {total_deleted}")
            return total_deleted

        except Exception as e:
            logger.error(f"[向量数据库] 从向量数据库删除文件失败: {e}")
            import traceback
            logger.error(f"[向量数据库] 详细错误: {traceback.format_exc()}")
            return 0

    def search(self, query: str, username: str = "", top_k: int = None, similarity_threshold: float = None) -> list[dict]:
        """搜索相关文档

        Args:
            query: 查询文本
            username: 用户名（可选）
            top_k: 返回数量（默认使用配置中的 search_top_k）
            similarity_threshold: 相似度阈值，0-1 之间，越大越精准（默认使用配置中的 similarity_threshold）

        Returns:
            相关的文档片段列表
        """
        if top_k is None:
            top_k = self.config.search_top_k
        if similarity_threshold is None:
            similarity_threshold = self.config.similarity_threshold
            
        logger.info(f"[向量数据库] 开始检索：query={query[:50]}..., username={username}, top_k={top_k}, threshold={similarity_threshold}")

        if not self.config.enabled:
            logger.info(f"[向量数据库] 向量数据库未启用，返回空结果")
            return []

        if self.collection is None:
            logger.error(f"[向量数据库] 向量数据库未连接")
            return []

        try:
            logger.info(f"[向量数据库] 正在执行向量检索")

            provider = getattr(self.config, 'embedding_provider', 'ollama')
            if provider == 'zhipu':
                logger.info(f"[向量数据库] 使用智谱 Embedding 检索 | model: {self.config.zhipu_model}")
                query_embedding = self._compute_zhipu_embeddings_batch([query])
                if not query_embedding:
                    logger.error(f"[向量数据库] 智谱 Embedding 计算失败")
                    return []
                query_embeddings = query_embedding
            else:
                if self._embedding_function is None:
                    logger.error(f"[向量数据库] Embedding函数未初始化")
                    return []
                query_embeddings = None

            where_filter = None
            if username:
                where_filter = {"username": {"$eq": username}}

            if query_embeddings:
                results = self.collection.query(
                    query_embeddings=query_embeddings,
                    n_results=top_k,
                    where=where_filter
                )
            else:
                results = self.collection.query(
                    query_texts=[query],
                    n_results=top_k,
                    where=where_filter
                )

            if not results or not results.get('documents') or not results['documents'][0]:
                logger.info(f"[向量数据库] 检索结果为空")
                return []

            logger.info(f"[向量数据库] 检索完成，返回 {len(results['documents'][0])} 条结果")

            search_results = []
            documents = results['documents'][0]
            metadatas = results.get('metadatas', [[]])[0]
            distances = results.get('distances', [[]])[0]

            for i, doc in enumerate(documents):
                metadata = metadatas[i] if i < len(metadatas) else {}
                distance = distances[i] if i < len(distances) else 0
                
                # Chroma 返回的是余弦距离，转换为相似度分数 (similarity = 1 - distance)
                similarity = 1.0 - distance
                
                # 只保留相似度大于阈值的文档
                if similarity >= similarity_threshold:
                    search_results.append({
                        "content": doc,
                        "file_path": metadata.get("file_path", ""),
                        "file_name": metadata.get("file_name", ""),
                        "file_type": metadata.get("file_type", ""),
                        "distance": distance,
                        "similarity": similarity,
                        "chunk_id": results['ids'][0][i] if 'ids' in results else ""
                    })

            logger.info(f"[向量数据库] 过滤后返回 {len(search_results)} 条结果 (threshold={similarity_threshold})")
            return search_results

        except Exception as e:
            logger.error(f"[向量数据库] 检索失败: {e}")
            return []

    def get_context_for_query(self, query: str, username: str = "", top_k: int = 5) -> str:
        """获取查询的上下文内容

        Args:
            query: 查询文本
            username: 用户名
            top_k: 返回数量

        Returns:
            格式化的上下文字符串
        """
        results = self.search(query, username, top_k)

        if not results:
            return ""

        context_parts = []
        context_parts.append("【参考文档】")
        context_parts.append("")

        for i, result in enumerate(results, 1):
            context_parts.append(f"[文档 {i}] {result['file_name']}")
            context_parts.append(f"内容: {result['content']}")
            context_parts.append("")

        return "\n".join(context_parts)


def get_vector_store() -> VectorStore:
    """获取向量数据库实例"""
    return VectorStore.get_instance()
