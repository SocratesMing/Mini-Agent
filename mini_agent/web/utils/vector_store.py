"""向量数据库模块 - 多租户架构，使用 Chroma + Embedding 实现本地 RAG"""

import logging
import hashlib
import time
import threading
from pathlib import Path
from typing import Optional, Dict

from mini_agent.web.utils.file_parser import FileParser

logger = logging.getLogger(__name__)


class VectorStoreConfig:
    """向量数据库配置"""

    def __init__(
        self,
        enabled: bool = False,
        db_path: str = "./data/chroma_db",
        collection_name: str = "mini_agent_docs",
        embedding_provider: str = "sentence_transformers",
        embedding_dimension: int = 4096,
        batch_size: int = 100,
        zhipu_api_key: str = "",
        zhipu_model: str = "embedding-3",
        sentence_transformers_model: str = "Qwen/Qwen3-Embedding-4B",
        search_top_k: int = 10,
        similarity_threshold: float = 0.5,
        config_dict: dict = None
    ):
        if config_dict is not None and isinstance(config_dict, dict):
            self.enabled = config_dict.get("enabled", enabled)
            self.db_path = config_dict.get("db_path", db_path)
            self.collection_name = config_dict.get("collection_name", collection_name)
            self.embedding_provider = config_dict.get("embedding_provider", embedding_provider)
            self.embedding_dimension = config_dict.get("embedding_dimension", embedding_dimension)
            self.batch_size = config_dict.get("batch_size", batch_size)
            self.zhipu_api_key = config_dict.get("zhipu_api_key", zhipu_api_key)
            self.zhipu_model = config_dict.get("zhipu_model", zhipu_model)
            self.sentence_transformers_model = config_dict.get("sentence_transformers_model", sentence_transformers_model)
            self.search_top_k = config_dict.get("search_top_k", search_top_k)
            self.similarity_threshold = config_dict.get("similarity_threshold", similarity_threshold)
        else:
            self.enabled = enabled
            self.db_path = db_path
            self.collection_name = collection_name
            self.embedding_provider = embedding_provider
            self.embedding_dimension = embedding_dimension
            self.batch_size = batch_size
            self.zhipu_api_key = zhipu_api_key
            self.zhipu_model = zhipu_model
            self.sentence_transformers_model = sentence_transformers_model
            self.search_top_k = search_top_k
            self.similarity_threshold = similarity_threshold


class VectorStoreManager:
    """向量数据库管理器 - 多租户版本

    每个用户有独立的数据库目录和集合，实现完全隔离。
    目录结构:
        ./data/chroma_db/
            user1/
                user1_docs/
                    (chroma sqlite files)
            user2/
                user2_docs/
                    (chroma sqlite files)
    """

    _instances: Dict[str, "VectorStore"] = {}
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, username: str = "default") -> "VectorStore":
        """获取指定用户的 VectorStore 实例（单例）

        Args:
            username: 用户名，用于隔离不同用户的数据

        Returns:
            VectorStore 实例
        """
        with cls._lock:
            if username not in cls._instances:
                config = cls._load_config_from_app_config()
                logger.info(
                    f"[向量数据库管理器] 为用户 '{username}' 创建 VectorStore 实例 | "
                    f"enabled: {config.enabled} | db_path: {config.db_path} | provider: {config.embedding_provider}"
                )
                cls._instances[username] = VectorStore(config, username=username)
            return cls._instances[username]

    @classmethod
    def _load_config_from_app_config(cls) -> VectorStoreConfig:
        """从应用配置加载向量数据库配置"""
        try:
            from mini_agent.config import Config
            config_path = Config.get_default_config_path()
            logger.info(f"加载配置文件: {config_path}")
            app_config = Config.load()
            vector_config = app_config.vector_store
            logger.info(
                f"向量配置已加载 | "
                f"enabled: {vector_config.enabled} | model: {vector_config.sentence_transformers_model}"
            )
            return vector_config
        except Exception as e:
            logger.warning(f"加载配置失败: {e}")
            import traceback
            logger.warning(f"详细错误: {traceback.format_exc()}")
            return VectorStoreConfig()

    @classmethod
    def delete_instance(cls, username: str):
        """删除指定用户的 VectorStore 实例

        Args:
            username: 用户名
        """
        with cls._lock:
            if username in cls._instances:
                del cls._instances[username]
                logger.info(f"[向量数据库管理器] 已删除用户 '{username}' 的实例")

    @classmethod
    def clear_all_instances(cls):
        """清除所有 VectorStore 实例"""
        with cls._lock:
            cls._instances.clear()
            logger.info("[向量数据库管理器] 已清除所有实例")


class VectorStore:
    """向量数据库 - 多租户版本

    每个用户独立的数据库连接和集合，实现数据隔离。
    """

    def __init__(self, config: VectorStoreConfig = None, username: str = "default"):
        self.config = config or VectorStoreConfig()
        self.username = username
        self.client = None
        self.collection = None
        self._embedding_function = None
        self._user_db_path = None
        self._user_collection_name = None

        if self.config.enabled:
            self._connect()

    def _get_user_paths(self) -> tuple:
        """获取用户独立的数据库路径和集合名

        Returns:
            (user_db_path, user_collection_name)
        """
        base_path = Path(self.config.db_path)
        user_db_path = base_path / self.username
        user_db_path.mkdir(parents=True, exist_ok=True)

        user_collection_name = f"{self.username}_collection"

        return str(user_db_path), user_collection_name

    def _connect(self):
        """连接到用户独立的 Chroma 向量数据库"""
        try:
            import chromadb

            self._user_db_path, self._user_collection_name = self._get_user_paths()

            logger.info(f"用户 '{self.username}' 初始化 Chroma 数据库")
            logger.info(f"数据库路径: {self._user_db_path}")
            logger.info(f"集合名称: {self._user_collection_name}")

            provider = getattr(self.config, 'embedding_provider', 'sentence_transformers')
            if provider == 'zhipu':
                logger.info(
                    f"使用智谱 Embedding | model: {self.config.zhipu_model} | "
                    f"dimension: {self.config.embedding_dimension}"
                )
                self._embedding_function = None
                self._test_zhipu_connection()
            elif provider == 'sentence_transformers':
                logger.info(
                    f"使用 Sentence Transformers Embedding | "
                    f"model: {self.config.sentence_transformers_model} | "
                    f"dimension: {self.config.embedding_dimension}"
                )
                self._embedding_function = self._init_sentence_transformers()
            else:
                logger.warning(
                    f"未知的 embedding provider: {provider}，将使用默认配置"
                )

            self.client = chromadb.PersistentClient(path=self._user_db_path)

            self.collection = self.client.get_or_create_collection(
                name=self._user_collection_name,
                embedding_function=self._embedding_function,
                metadata={"hnsw:space": "cosine"}
            )

            logger.info(f"✅ Chroma 数据库初始化成功 | 用户: {self.username}")

        except ImportError:
            logger.error("请安装 chromadb: pip install chromadb")
            self.config.enabled = False
        except Exception as e:
            logger.error(f"初始化 Chroma 数据库失败: {e}")
            self.config.enabled = False

    def _test_zhipu_connection(self):
        """测试智谱 API 连接"""
        try:
            from zhipuai import ZhipuAI
            client = ZhipuAI(api_key=self.config.zhipu_api_key)
            response = client.embeddings.create(
                model=self.config.zhipu_model,
                input=["测试连接"]
            )
            if response and response.data:
                logger.info(
                    f"✅ 智谱 API 连接成功 | "
                    f"embedding dimension: {len(response.data[0].embedding)}"
                )
            else:
                logger.warning("智谱 API 响应异常")
        except Exception as e:
            logger.error(f"❌ 智谱 API 连接失败: {e}")
            self.config.enabled = False

    def _init_sentence_transformers(self):
        """初始化 Sentence Transformers embedding 函数"""
        try:
            from sentence_transformers import SentenceTransformer
            import os

            model_name = getattr(
                self.config, 'sentence_transformers_model', 'Qwen/Qwen3-Embedding-4B'
            )

            modelscope_cache = os.path.join(os.getcwd(), "models")
            modelscope_model_path = os.path.join(modelscope_cache, model_name)
            model_name_only = model_name.split("/")[-1]
            modelscope_model_path_alt = os.path.join(modelscope_cache, model_name_only)

            logger.info(f"加载 Sentence Transformers 模型：{model_name}")
            logger.info(f"本地模型目录: {modelscope_cache}")

            cache_folder = None
            if os.path.exists(modelscope_model_path):
                logger.info(f"✅ 从本地缓存加载模型: {modelscope_model_path}")
                cache_folder = modelscope_model_path
            elif os.path.exists(modelscope_model_path_alt):
                logger.info(f"✅ 从本地缓存加载模型: {modelscope_model_path_alt}")
                cache_folder = modelscope_model_path_alt
            else:
                logger.info(f"从 HuggingFace 下载并加载模型: {model_name}")

            if cache_folder:
                model_instance = SentenceTransformer(cache_folder)
            else:
                model_instance = SentenceTransformer(model_name)

            class SentenceTransformerEmbedding:
                def __init__(self, model):
                    self.model = model

                def __call__(self, input: list[str]) -> list[list[float]]:
                    embeddings = self.model.encode(input, convert_to_numpy=True)
                    return embeddings.tolist()

                def name(self) -> str:
                    return "sentence_transformers"

                def dimension(self) -> int:
                    return self.model.get_sentence_embedding_dimension()

            embed_fn = SentenceTransformerEmbedding(model_instance)

            logger.info(f"✅ Sentence Transformers 模型加载成功")
            return embed_fn

        except ImportError:
            logger.error(
                f"❌ 请安装 sentence-transformers: pip install sentence-transformers"
            )
            self.config.enabled = False
            return None
        except Exception as e:
            logger.error(f"❌ Sentence Transformers 初始化失败：{e}")
            self.config.enabled = False
            return None

    def _compute_embeddings_batch_zhipu(self, texts: list[str]) -> list[list[float]]:
        """使用智谱 API 批量计算 embedding"""
        try:
            from zhipuai import ZhipuAI
            client = ZhipuAI(api_key=self.config.zhipu_api_key)

            response = client.embeddings.create(
                model=self.config.zhipu_model,
                input=texts
            )

            if response and response.data:
                embeddings = [item.embedding for item in response.data]
                logger.info(
                    f"智谱 API 批量 embedding 成功 | "
                    f"texts: {len(texts)}, embeddings: {len(embeddings)}"
                )
                return embeddings
            else:
                logger.error("智谱 API 响应异常")
                return [[0.0] * self.config.embedding_dimension] * len(texts)

        except Exception as e:
            logger.error(f"智谱 API 调用失败: {e}")
            return [[0.0] * self.config.embedding_dimension] * len(texts)

    def _compute_embeddings_batch_sentence_transformers(
        self, texts: list[str]
    ) -> list[list[float]]:
        """使用 Sentence Transformers 批量计算 embedding"""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "请安装 sentence-transformers: pip install sentence-transformers"
            )

        model_name = getattr(
            self.config, 'sentence_transformers_model', 'Qwen/Qwen3-Embedding-4B'
        )
        logger.info(
            f"使用 Sentence Transformers 计算 Embedding | model: {model_name}"
        )

        if self._embedding_function is not None:
            logger.info(f"使用预加载的 embedding 函数")
            embeddings = self._embedding_function(texts)
            return embeddings

        import os
        modelscope_cache = os.path.join(os.getcwd(), "models")
        modelscope_model_path = os.path.join(modelscope_cache, model_name)

        if os.path.exists(modelscope_model_path):
            logger.info(
                f"从本地模型目录加载模型: {modelscope_model_path}"
            )
            model = SentenceTransformer(modelscope_model_path)
        else:
            logger.info(
                f"从 HuggingFace 下载并加载模型: {model_name}"
            )
            model = SentenceTransformer(model_name)

        embeddings = model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def _generate_chunk_id(self, file_path: str, chunk_index: int) -> str:
        """生成 chunk ID"""
        unique_str = f"{self.username}_{file_path}_{chunk_index}"
        return hashlib.md5(unique_str.encode()).hexdigest()

    def _chunk_text(
        self, text: str, chunk_size: int = 500, overlap: int = 50
    ) -> list[str]:
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

            logger.info(
                f"初始化 RecursiveCharacterTextSplitter | "
                f"chunk_size: {chunk_size}, overlap: {overlap}"
            )

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=overlap,
                length_function=len,
                separators=["\n\n", "\n", "。", "！", "？", " ", ""]
            )

            logger.info(
                f"开始分割文本 | 原文长度: {len(text)} 字符"
            )
            chunks = text_splitter.split_text(text)
            logger.info(
                f"文本分割完成 | 生成 {len(chunks)} 个块"
            )

            for i, chunk in enumerate(chunks[:3]):
                logger.debug(
                    f"Chunk {i}: {chunk[:50]}..."
                )

            return chunks

        except ImportError:
            logger.warning(
                f"langchain-text-splitters 未安装，使用简单分块"
            )
            return self._simple_chunk_text(text, chunk_size, overlap)
        except Exception as e:
            logger.error(f"文本分割失败: {e}")
            return self._simple_chunk_text(text, chunk_size, overlap)

    def _simple_chunk_text(
        self, text: str, chunk_size: int = 500, overlap: int = 50
    ) -> list[str]:
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
        logger.info(
            f"开始清洗文本 | 原始长度: {original_length} 字符"
        )

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

        logger.info(
            f"文本清洗完成 | "
            f"清洗后长度: {len(cleaned)} 字符 | 移除: {original_length - len(cleaned)} 字符"
        )

        return cleaned

    def _extract_file_content(self, file_path: str, file_type: str = "") -> str:
        """提取文件内容

        Args:
            file_path: 文件路径
            file_type: 文件类型

        Returns:
            文件内容
        """
        try:
            parser = FileParser()
            content = parser.extract_content(file_path)

            if isinstance(content, dict):
                content = content.get('content', '')

            return content if content else ""

        except Exception as e:
            logger.error(f"提取文件内容失败: {e}")
            return ""

    def add_file(
        self, file_path: str, username: str = None, file_type: str = ""
    ) -> int:
        """添加文件到向量数据库 - 完整的 RAG 流程

        Args:
            file_path: 文件路径
            username: 用户名（如果不使用多租户管理器，则使用此用户名）
            file_type: 文件类型 (pdf, docx, xlsx, etc.)

        Returns:
            添加的 chunk 数量
        """
        effective_username = username or self.username

        logger.info(f"=" * 60)
        logger.info(f"开始处理文件")
        logger.info(f"文件路径: {file_path}")
        logger.info(f"用户名: {effective_username}")
        logger.info(f"文件类型: {file_type}")
        logger.info(f"=" * 60)

        if not self.config.enabled:
            logger.info(f"向量数据库未启用，跳过文件添加")
            return 0

        if self.collection is None:
            logger.error(f"向量数据库未连接")
            return 0

        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                logger.error(f"文件不存在: {file_path}")
                return 0

            self.delete_by_file(file_path, effective_username)

            file_size = file_path_obj.stat().st_size
            logger.info(f"文件大小: {file_size} bytes")

            logger.info(f"步骤1/5: 文档加载")
            content = self._extract_file_content(file_path, file_type)
            if not content:
                logger.warning(f"无法提取文件内容: {file_path}")
                return 0
            logger.info(
                f"文档加载完成 | 原始内容长度: {len(content)} 字符"
            )

            logger.info(f"步骤2/5: 文本清洗")
            content = self._clean_text(content)
            if not content:
                logger.warning(f"清洗后内容为空: {file_path}")
                return 0
            logger.info(
                f"文本清洗完成 | 清洗后长度: {len(content)} 字符"
            )

            logger.info(
                f"步骤3/5: 文本分块 (RecursiveCharacterTextSplitter)"
            )
            logger.info(f"分块参数 | chunk_size: 500, overlap: 50")
            chunks = self._chunk_text(content, chunk_size=500, overlap=50)
            if not chunks:
                logger.warning(f"文件内容分块后为空: {file_path}")
                return 0
            logger.info(f"文本分块完成 | 生成 {len(chunks)} 个块")

            if len(chunks) <= 5:
                for i, chunk in enumerate(chunks):
                    logger.debug(
                        f"Chunk {i} (长度 {len(chunk)}): {chunk[:80]}..."
                    )
            else:
                logger.debug(f"前3个Chunk预览:")
                for i, chunk in enumerate(chunks[:3]):
                    logger.debug(
                        f"  Chunk {i} (长度 {len(chunk)}): {chunk[:80]}..."
                    )

            logger.info(f"步骤4/5: 向量化文本块")
            provider = getattr(
                self.config, 'embedding_provider', 'sentence_transformers'
            )
            if provider == 'zhipu':
                logger.info(
                    f"使用智谱 Embedding | model: {self.config.zhipu_model}"
                )
            elif provider == 'sentence_transformers':
                logger.info(
                    f"使用 Sentence Transformers Embedding | "
                    f"model: {self.config.sentence_transformers_model}"
                )
            else:
                logger.info(
                    f"使用默认 Embedding | "
                    f"model: {self.config.sentence_transformers_model}"
                )

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
                    "file_path": file_path,
                    "file_name": file_path_obj.name,
                    "file_type": file_type,
                    "chunk_index": i,
                    "username": effective_username,
                    "source": "file_parser"
                })

            batch_size = getattr(self.config, 'batch_size', 32)

            logger.info(
                f"步骤5/5: 批量插入向量数据库 | "
                f"总数: {len(ids)} | 批次大小: {batch_size}"
            )

            total_batches = (len(ids) + batch_size - 1) // batch_size
            success_count = 0

            for batch_idx in range(total_batches):
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, len(ids))

                batch_ids = ids[start_idx:end_idx]
                batch_documents = documents[start_idx:end_idx]
                batch_metadatas = metadatas[start_idx:end_idx]

                try:
                    self.collection.add(
                        ids=batch_ids,
                        documents=batch_documents,
                        metadatas=batch_metadatas
                    )
                    success_count += len(batch_ids)
                    logger.info(
                        f"已处理 {success_count}/{len(ids)} 个块"
                    )
                except Exception as e:
                    logger.error(
                        f"批次 {batch_idx + 1} 插入失败: {e}"
                    )
                    continue

            logger.info(
                f"✅ 文件添加完成 | 成功: {success_count}/{len(ids)} | "
                f"用户: {effective_username}"
            )
            return success_count

        except Exception as e:
            logger.error(f"添加文件到向量数据库失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return 0

    def search(
        self,
        query: str,
        username: str = None,
        top_k: int = None,
        filters: dict = None
    ) -> list:
        """搜索向量数据库

        Args:
            query: 查询文本
            username: 用户名（用于过滤该用户的数据，如果不指定则使用当前实例用户）
            top_k: 返回结果数量
            filters: 额外的过滤条件

        Returns:
            搜索结果列表
        """
        if not self.config.enabled:
            logger.warning("向量数据库未启用")
            return []

        if self.collection is None:
            logger.error("向量数据库未连接")
            return []

        effective_username = username or self.username

        try:
            if top_k is None:
                top_k = getattr(self.config, 'search_top_k', 10)

            logger.info(
                f"开始搜索 | 查询: '{query}' | "
                f"用户: {effective_username} | top_k: {top_k}"
            )

            where_filter = {"username": effective_username}
            if filters:
                where_filter.update(filters)

            provider = getattr(
                self.config, 'embedding_provider', 'sentence_transformers'
            )

            if provider == 'zhipu':
                query_embedding = self._compute_embeddings_batch_zhipu([query])[0]
            elif provider == 'sentence_transformers':
                query_embedding = self._compute_embeddings_batch_sentence_transformers([query])[0]
            else:
                query_embedding = self._compute_embeddings_batch_sentence_transformers([query])[0]

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter
            )

            search_results = []
            if results and results.get('documents'):
                doc_list = results['documents'][0]
                meta_list = results.get('metadatas', [[]])[0]
                dist_list = results.get('distances', [[]])[0]

                for i, doc in enumerate(doc_list):
                    metadata = meta_list[i] if i < len(meta_list) else {}
                    distance = dist_list[i] if i < len(dist_list) else 0.0

                    similarity = 1.0 / (1.0 + distance)

                    if similarity >= getattr(
                        self.config, 'similarity_threshold', 0.5
                    ):
                        search_results.append({
                            "content": doc,
                            "score": similarity,
                            "distance": distance,
                            "metadata": metadata
                        })

            logger.info(
                f"搜索完成 | 找到 {len(search_results)} 条结果 | "
                f"用户: {effective_username}"
            )
            
            for i, result in enumerate(search_results, 1):
                file_name = result.get('metadata', {}).get('file_name', '未知文件')
                logger.info(f"结果{i}: {file_name} | 相似度: {result.get('score', 0):.3f}")

            return search_results

        except Exception as e:
            logger.error(f"搜索失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return []

    def delete_by_file(self, file_path: str, username: str = None) -> bool:
        """删除指定文件的所有 chunks

        Args:
            file_path: 文件路径
            username: 用户名

        Returns:
            是否删除成功
        """
        if not self.config.enabled:
            return False

        if self.collection is None:
            return False

        effective_username = username or self.username

        try:
            logger.info(
                f"删除文件 chunks | "
                f"文件: {file_path} | 用户: {effective_username}"
            )

            self.collection.delete(
                where={"$and": [{"file_path": file_path}, {"username": effective_username}]}
            )

            logger.info(f"✅ 文件 chunks 删除成功")
            return True

        except Exception as e:
            logger.error(f"删除文件 chunks 失败: {e}")
            return False

    def get_stats(self, username: str = None) -> dict:
        """获取向量数据库统计信息

        Args:
            username: 用户名

        Returns:
            统计信息字典
        """
        effective_username = username or self.username

        if not self.config.enabled:
            return {"enabled": False}

        if self.collection is None:
            return {"enabled": True, "connected": False}

        try:
            count = self.collection.count()

            return {
                "enabled": True,
                "connected": True,
                "username": effective_username,
                "db_path": self._user_db_path,
                "collection_name": self._user_collection_name,
                "total_chunks": count,
                "embedding_provider": getattr(
                    self.config, 'embedding_provider', 'sentence_transformers'
                ),
                "embedding_model": getattr(
                    self.config, 'sentence_transformers_model',
                    getattr(self.config, 'zhipu_model', 'unknown')
                ),
                "embedding_dimension": getattr(
                    self.config, 'embedding_dimension', 4096
                )
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {"enabled": True, "error": str(e)}


def get_vector_store(username: str = None) -> VectorStore:
    """获取 VectorStore 实例的兼容函数

    为了向后兼容而保留。对于新的多租户架构，建议直接使用 VectorStoreManager.get_instance(username)。

    Args:
        username: 用户名，如果为 None 则使用 "default"

    Returns:
        VectorStore 实例
    """
    effective_username = username or "default"
    return VectorStoreManager.get_instance(effective_username)
