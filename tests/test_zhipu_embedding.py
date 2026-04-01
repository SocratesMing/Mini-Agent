"""测试使用智谱 Embedding API 解析 Excel 文件并存储到 Chroma 向量数据库"""

import sys
import time
import logging
from pathlib import Path

# 配置 logging 输出到终端
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from mini_agent.web.utils.vector_store import VectorStore, VectorStoreConfig


def test_zhipu_embedding():
    """测试使用智谱 Embedding API"""
    print("\n" + "=" * 60)
    print("测试：使用智谱 Embedding API 解析 Excel 文件")
    print("=" * 60)

    # 1. 配置向量数据库 - 使用智谱 Embedding
    print("\n[1/5] 配置向量数据库...")
    config = VectorStoreConfig(
        enabled=True,
        db_path="./data/test_chroma_db_zhipu",
        collection_name="test_excel_docs_zhipu",
        embedding_provider="zhipu",
        embedding_dimension=1024,
        batch_size=32,
        search_top_k=10,
        similarity_threshold=0.5,
        zhipu_api_key="e85df0ae47b44929b0450939084de077.47Af1uq8jZVsUgHO",  # TODO: 填入你的智谱 API Key
        zhipu_model="embedding-3"  # 或 embedding-3-128k
    )

    # 检查 API Key
    if not config.zhipu_api_key:
        print("⚠️ 请在代码中设置智谱 API Key")
        print("   修改 zhipu_api_key 参数")
        return

    print(f"   使用智谱 Embedding | model: {config.zhipu_model} | dimension: {config.embedding_dimension}")

    # 2. 初始化向量数据库
    print("\n[2/5] 初始化向量数据库...")
    vector_store = VectorStore(config)

    if vector_store.collection is None:
        print("❌ 向量数据库初始化失败")
        return

    print("✅ 向量数据库初始化成功")

    # 3. 解析 Excel 文件
    excel_file = r"C:\Users\sutut\Desktop\员工个人培训信息列表.xlsx"
    print(f"\n[3/5] 解析 Excel 文件：{excel_file}")

    if not Path(excel_file).exists():
        print(f"❌ 文件不存在：{excel_file}")
        return

    # 使用 FileParser 解析
    from mini_agent.web.utils.file_parser import FileParser
    parser = FileParser()
    result = parser.extract_content(excel_file)

    if not result:
        print("❌ 文件解析失败")
        return

    content = result if isinstance(result, str) else result
    print(f"✅ 文件解析成功，内容长度：{len(content)} 字符")
    print(f"\n内容预览（前 500 字符）:\n{content[:500]}...")

    # 4. 将内容存储到向量数据库
    print("\n[4/5] 将内容存储到向量数据库...")

    # 使用 add_file 方法直接添加文件
    print("   正在添加到向量数据库...")
    count = vector_store.add_file(
        file_path=excel_file,
        username="test_user",
        file_type="xlsx"
    )

    if count > 0:
        print(f"✅ 添加成功，共 {count} 个文本块")
    else:
        print("❌ 添加失败")
        return

    # 5. 测试检索
    print("\n[5/5] 测试检索功能...")

    # 等待一下确保数据已存储
    time.sleep(1)

    # 测试查询
    test_queries = [
        "培训内容",
        "培训时间",
        "培训地点"
    ]

    for query in test_queries:
        print(f"\n   查询：'{query}'")
        results = vector_store.search(
            query=query,
            username="test_user",
            top_k=3
        )

        if results:
            print(f"   找到 {len(results)} 条结果:")
            for i, result in enumerate(results, 1):
                print(f"   [{i}] 相似度：{result.get('score', 0):.4f}")
                print(f"       内容：{result['content'][:100]}...")
        else:
            print("   未找到相关结果")

    print("\n" + "=" * 60)
    print("✅ 测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_zhipu_embedding()
