"""测试使用 Sentence Transformers qwen3-embedding 模型解析 Excel 文件并存储到 Chroma 向量数据库（多租户版本）"""

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

from mini_agent.web.utils.vector_store import VectorStoreManager


def test_sentence_transformers_multitenant():
    """测试使用 Sentence Transformers 多租户版本"""
    print("\n" + "=" * 60)
    print("测试：使用 Sentence Transformers 多租户向量数据库")
    print("=" * 60)

    # 测试用户名列表
    test_users = ["user1", "user2", "user3"]
    excel_file = r"C:\Users\sutut\Desktop\员工个人培训信息列表.xlsx"

    # 检查文件是否存在
    if not Path(excel_file).exists():
        print(f"❌ 文件不存在：{excel_file}")
        return

    for username in test_users:
        print(f"\n{'=' * 60}")
        print(f"测试用户: {username}")
        print(f"{'=' * 60}")

        # 1. 配置向量数据库
        print("\n[1/5] 配置向量数据库...")
        vector_store = VectorStoreManager.get_instance(username)
        print(f"✅ VectorStore 实例获取成功 | 用户: {username}")

        # 2. 检查初始化状态
        print("\n[2/5] 检查数据库状态...")
        if vector_store.collection is None:
            print("❌ 向量数据库初始化失败")
            continue
        print("✅ 向量数据库初始化成功")

        # 3. 解析 Excel 文件
        print(f"\n[3/5] 解析 Excel 文件...")
        from mini_agent.web.utils.file_parser import FileParser
        parser = FileParser()
        result = parser.extract_content(excel_file)

        if not result:
            print("❌ 文件解析失败")
            continue

        content = result if isinstance(result, str) else result
        print(f"✅ 文件解析成功，内容长度：{len(content)} 字符")

        # 4. 将内容存储到向量数据库
        print("\n[4/5] 将内容存储到向量数据库...")
        print("   正在添加到向量数据库...")
        count = vector_store.add_file(
            file_path=excel_file,
            username=username,
            file_type="xlsx"
        )

        if count > 0:
            print(f"✅ 添加成功，共 {count} 个文本块")
        else:
            print("❌ 添加失败")
            continue

        # 5. 测试检索
        print("\n[5/5] 测试检索功能...")

        time.sleep(1)

        test_queries = [
            "培训内容",
            "培训时间",
            "培训地点"
        ]

        for query in test_queries:
            print(f"\n   查询：'{query}'")
            results = vector_store.search(
                query=query,
                username=username,
                top_k=3
            )

            if results:
                print(f"   找到 {len(results)} 条结果:")
                for i, result in enumerate(results, 1):
                    print(f"   [{i}] 相似度：{result.get('score', 0):.4f}")
                    print(f"       内容：{result['content'][:100]}...")
            else:
                print("   未找到相关结果")

        # 打印统计信息
        print("\n   统计信息:")
        stats = vector_store.get_stats(username)
        for key, value in stats.items():
            print(f"   {key}: {value}")

    print("\n" + "=" * 60)
    print("✅ 多租户测试完成")
    print(f"✅ 目录结构: ./data/chroma_db/{test_users[0]}/, ./data/chroma_db/{test_users[1]}/, ...")
    print("=" * 60)


if __name__ == "__main__":
    test_sentence_transformers_multitenant()
