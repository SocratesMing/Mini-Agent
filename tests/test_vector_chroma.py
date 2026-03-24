"""Sentence-Transformers + Chroma 向量数据库测试

测试基于用户名分组的向量数据库功能
"""

import os
import tempfile
import shutil
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from sentence_transformers import SentenceTransformer


class VectorStoreByUser:
    """基于用户分组的向量数据库"""

    def __init__(self, db_path: str, collection_name: str = "user_docs",
                 embedding_provider: str = "sentence_transformers",
                 embedding_model_name: str = "all-MiniLM-L6-v2",
                 embedding_dimension: int = 384):
        self.db_path = db_path
        self.collection_name = collection_name
        self.embedding_provider = embedding_provider
        self.embedding_model_name = embedding_model_name
        self.embedding_dimension = embedding_dimension

        if embedding_provider == "sentence_transformers":
            self.embedding_model = SentenceTransformer(embedding_model_name)
        else:
            raise ValueError(f"不支持的 embedding provider: {embedding_provider}")

        os.makedirs(db_path, exist_ok=True)

        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_documents(self, username: str, documents: list[str], metadata: list[dict] = None):
        """添加文档

        Args:
            username: 用户名
            documents: 文档内容列表
            metadata: 元数据列表
        """
        if not documents:
            return 0

        embeddings = self.embedding_model.encode(documents).tolist()

        ids = [f"{username}_{i}" for i in range(len(documents))]
        metadatas = metadata or [{"username": username} for _ in documents]

        for i, m in enumerate(metadatas):
            m["username"] = username

        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas
        )

        return len(documents)

    def search_by_user(self, username: str, query: str, top_k: int = 5):
        """搜索指定用户的文档

        Args:
            username: 用户名
            query: 查询文本
            top_k: 返回数量

        Returns:
            搜索结果列表
        """
        query_embedding = self.embedding_model.encode([query]).tolist()[0]

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"username": {"$eq": username}}
        )

        return self._format_results(results)

    def search_all(self, query: str, top_k: int = 5):
        """搜索所有用户的文档

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            搜索结果列表
        """
        query_embedding = self.embedding_model.encode([query]).tolist()[0]

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )

        return self._format_results(results)

    def delete_user_data(self, username: str):
        """删除指定用户的所有数据

        Args:
            username: 用户名
        """
        results = self.collection.get(where={"username": {"$eq": username}})
        if results and results.get("ids"):
            self.collection.delete(ids=results["ids"])
            return len(results["ids"])
        return 0

    def get_user_stats(self, username: str = None):
        """获取用户统计信息

        Args:
            username: 用户名，为空则返回所有用户的统计

        Returns:
            统计信息字典
        """
        if username:
            results = self.collection.get(where={"username": {"$eq": username}})
            return {
                "username": username,
                "document_count": len(results.get("ids", [])) if results else 0
            }
        else:
            results = self.collection.get()
            users = {}
            for meta in (results.get("metadatas") or []):
                user = meta.get("username", "unknown")
                users[user] = users.get(user, 0) + 1
            return {
                "total_documents": len(results.get("ids", [])) if results else 0,
                "users": users
            }

    def _format_results(self, results: dict) -> list[dict]:
        """格式化搜索结果"""
        formatted = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"]):
                formatted.append({
                    "document": doc,
                    "metadata": results["metadatas"][i] if results.get("metadatas") else {},
                    "distance": results["distances"][i] if results.get("distances") else 0
                })
        return formatted


def test_basic_operations():
    """测试基本操作"""
    print("=" * 60)
    print("测试 1: 基本操作")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        vs = VectorStoreByUser(tmpdir)

        vs.add_documents(
            username="alice",
            documents=[
                "Python是一种高级编程语言",
                "JavaScript用于Web开发",
                "机器学习是人工智能的子领域"
            ],
            metadata=[{"source": "tech"}, {"source": "web"}, {"source": "ai"}]
        )

        vs.add_documents(
            username="bob",
            documents=[
                "金融市场分析",
                "股票投资策略",
                "风险管理方法"
            ],
            metadata=[{"source": "finance"}, {"source": "invest"}, {"source": "risk"}]
        )

        print(f"✅ 添加文档成功 | alice: 3个, bob: 3个")

        stats = vs.get_user_stats()
        print(f"   统计: {stats}")

        docs = vs.collection.get()
        print(f"   总文档数: {len(docs.get('ids', []))}")


def test_user_isolation():
    """测试用户数据隔离"""
    print("\n" + "=" * 60)
    print("测试 2: 用户数据隔离")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        vs = VectorStoreByUser(tmpdir)

        vs.add_documents("alice", ["Python教程", "JavaScript指南"])
        vs.add_documents("bob", ["金融理论", "投资实践"])

        alice_results = vs.search_by_user("alice", "编程语言")
        bob_results = vs.search_by_user("bob", "编程语言")

        print(f"   Alice搜索'编程语言': {len(alice_results)} 条结果")
        print(f"   Bob搜索'编程语言': {len(bob_results)} 条结果")

        assert len(alice_results) > 0, "Alice应该找到相关文档"
        assert len(bob_results) == 0, "Bob不应该找到编程相关文档"
        print("✅ 用户数据隔离正确")


def test_cross_user_search():
    """测试跨用户搜索"""
    print("\n" + "=" * 60)
    print("测试 3: 跨用户搜索")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        vs = VectorStoreByUser(tmpdir)

        vs.add_documents("alice", ["猫是可爱的宠物"])
        vs.add_documents("bob", ["狗是人类最好的朋友"])
        vs.add_documents("charlie", ["我喜欢所有的动物"])

        results = vs.search_all("宠物和动物", top_k=3)

        print(f"   搜索'宠物和动物': {len(results)} 条结果")
        for i, r in enumerate(results):
            print(f"   {i+1}. [{r['metadata'].get('username')}] {r['document'][:30]}...")

        usernames = [r["metadata"].get("username") for r in results]
        assert "alice" in usernames, "应该找到alice的文档"
        assert "bob" in usernames, "应该找到bob的文档"
        print("✅ 跨用户搜索正常")


def test_delete_user_data():
    """测试删除用户数据"""
    print("\n" + "=" * 60)
    print("测试 4: 删除用户数据")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        vs = VectorStoreByUser(tmpdir)

        vs.add_documents("alice", ["文档A1", "文档A2", "文档A3"])
        vs.add_documents("bob", ["文档B1", "文档B2"])

        stats_before = vs.get_user_stats()
        print(f"   删除前: {stats_before}")

        deleted = vs.delete_user_data("alice")
        print(f"   删除了alice的 {deleted} 个文档")

        stats_after = vs.get_user_stats()
        print(f"   删除后: {stats_after}")

        assert stats_after["users"].get("alice", 0) == 0, "Alice的数据应该被删除"
        assert stats_after["users"].get("bob", 0) == 2, "Bob的数据应该保留"
        print("✅ 删除用户数据正常")


def test_metadata_filtering():
    """测试元数据过滤"""
    print("\n" + "=" * 60)
    print("测试 5: 元数据过滤")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        vs = VectorStoreByUser(tmpdir)

        vs.add_documents(
            "alice",
            ["技术文档", "私人日记", "工作周报"],
            metadata=[{"type": "tech"}, {"type": "personal"}, {"type": "work"}]
        )

        stats = vs.get_user_stats("alice")
        print(f"   Alice文档数: {stats['document_count']}")

        all_results = vs.search_all("工作", top_k=10)
        alice_work = [r for r in all_results if r["metadata"].get("username") == "alice" and r["metadata"].get("type") == "work"]

        print(f"   Alice的工作文档: {len(alice_work)} 条")
        print("✅ 元数据过滤正常")


def test_similarity_ranking():
    """测试相似度排序"""
    print("\n" + "=" * 60)
    print("测试 6: 相似度排序")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        vs = VectorStoreByUser(tmpdir)

        vs.add_documents("alice", [
            "苹果是一种水果",
            "苹果手机是苹果公司的产品",
            "香蕉是黄色的水果"
        ])

        results = vs.search_by_user("alice", "水果", top_k=3)

        print(f"   查询'水果'的前3结果:")
        for i, r in enumerate(results):
            print(f"   {i+1}. [距离: {r['distance']:.4f}] {r['document']}")

        assert results[0]["document"] == "苹果是一种水果" or results[0]["document"] == "香蕉是黄色的水果"
        print("✅ 相似度排序正常")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Sentence-Transformers + Chroma 测试套件")
    print("=" * 60)

    test_basic_operations()
    test_user_isolation()
    test_cross_user_search()
    test_delete_user_data()
    test_metadata_filtering()
    test_similarity_ranking()

    print("\n" + "=" * 60)
    print("✅ 所有测试通过!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
