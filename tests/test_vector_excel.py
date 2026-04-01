"""测试使用 Sentence Transformers qwen3-embedding 模型解析 Excel 文件并存储到 Chroma 向量数据库"""

import sys
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 直接导入需要的模块，避免导入整个 mini_agent
from mini_agent.web.utils.vector_store import VectorStore, VectorStoreConfig
from mini_agent.web.utils.file_parser import FileParser


def test_vector_excel():
    """测试使用 Sentence Transformers qwen3-embedding 模型"""
    print("\n" + "=" * 60)
    print("测试：使用 Sentence Transformers Qwen/Qwen3-Embedding-4B 模型解析 Excel 文件")
    print("=" * 60)
    
    # 1. 配置向量数据库
    print("\n[1/5] 配置向量数据库...")
    config = VectorStoreConfig(
        enabled=True,
        db_path="./data/test_chroma_db",
        collection_name="test_excel_docs",
        embedding_provider="sentence_transformers",
        sentence_transformers_model="Qwen/Qwen3-Embedding-4B",
        embedding_dimension=4096,
        batch_size=100,
        search_top_k=10,
        similarity_threshold=0.5
    )
    
    # 2. 初始化向量数据库
    print("\n[2/5] 初始化向量数据库...")
    vector_store = VectorStore(config)
    
    if vector_store.collection is None:
        print("❌ 向量数据库初始化失败")
        return
    
    print("✅ 向量数据库初始化成功")
    
    # 3. 解析 Excel 文件
    excel_file = r"C:\Users\sutut\Desktop\RAG\员工个人培训信息列表 -0319.xlsx"
    print(f"\n[3/5] 解析 Excel 文件：{excel_file}")
    
    if not Path(excel_file).exists():
        print(f"❌ 文件不存在：{excel_file}")
        return
    
    parser = FileParser()
    result = parser.extract_content(excel_file)
    
    if not result:
        print("❌ 文件解析失败")
        return
    
    print(f"✅ 文件解析成功，文本长度：{len(result)}")
    print(f"\n预览（前 500 字符）:\n{result[:500]}...")
    
    # 4. 存储到向量数据库
    print("\n[4/5] 存储到向量数据库...")
    
    # 按行分割，每行作为一个文档
    lines = [line.strip() for line in result.split('\n') if line.strip()]
    
    if not lines:
        print("❌ 没有可存储的内容")
        return
    
    # 批量存储
    batch_size = config.batch_size
    total = len(lines)
    stored = 0
    
    print(f"   共 {total} 行，批量大小：{batch_size}")
    
    for i in range(0, total, batch_size):
        batch = lines[i:i + batch_size]
        success = vector_store.add_documents(
            documents=batch,
            metadata_list=[{"source": "excel", "index": j} for j in range(i, i + len(batch))]
        )
        if success:
            stored += len(batch)
            print(f"   已存储 {stored}/{total} 行")
        else:
            print(f"   ❌ 批量 {i//batch_size + 1} 存储失败")
    
    print(f"\n✅ 存储完成，共存储 {stored}/{total} 行")
    
    # 5. 测试搜索
    print("\n[5/5] 测试搜索...")
    test_query = "培训"
    print(f"   搜索查询：{test_query}")
    
    results = vector_store.search(test_query, top_k=3)
    
    if results:
        print(f"\n✅ 找到 {len(results)} 条相关结果:\n")
        for i, doc in enumerate(results, 1):
            print(f"[{i}] 相似度：{doc.get('score', 0):.4f}")
            print(f"    内容：{doc['content'][:200]}...")
            print()
    else:
        print("❌ 未找到相关结果")
    
    print("\n" + "=" * 60)
    print("✅ 测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_vector_excel()
