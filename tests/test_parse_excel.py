"""测试 Sentence Transformers 解析 Excel"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# 直接导入需要的模块
from mini_agent.web.utils.vector_store import VectorStore, VectorStoreConfig
from mini_agent.web.utils.file_parser import FileParser

def test_parse_excel():
    """测试解析 Excel 文件"""
    print("\n" + "=" * 60)
    print("测试：Sentence Transformers 解析 Excel 文件")
    print("=" * 60)
    
    excel_file = r"C:\Users\sutut\Desktop\员工个人培训信息列表.xlsx"
    print(f"\n文件路径：{excel_file}")
    
    # 1. 检查文件是否存在
    if not Path(excel_file).exists():
        print(f"❌ 文件不存在：{excel_file}")
        return
    
    print("✅ 文件存在")
    
    # 2. 解析 Excel 文件
    print("\n[1/4] 解析 Excel 文件...")
    parser = FileParser()
    result = parser.extract_content(excel_file)
    
    if not result:
        print("❌ 文件解析失败")
        return
    
    # FileParser 返回的是字符串，不是字典
    content = result if isinstance(result, str) else result
    print(f"✅ 文件解析成功，内容长度：{len(content)} 字符")
    print(f"\n内容预览（前 1000 字符）:\n")
    print(content[:1000])
    
    # 3. 配置向量数据库
    print("\n[2/4] 配置向量数据库...")
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
    
    # 4. 初始化向量数据库
    print("\n[3/4] 初始化向量数据库...")
    vector_store = VectorStore(config)
    
    if vector_store.collection is None:
        print("❌ 向量数据库初始化失败")
        return
    
    print("✅ 向量数据库初始化成功")
    
    # 5. 添加文档到向量数据库
    print("\n[4/4] 添加文档到向量数据库...")
    
    # 按行分割内容
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    print(f"   共 {len(lines)} 行")
    
    # 使用 vector_store.add_file 方法
    count = vector_store.add_file(
        file_path=excel_file,
        username="test_user",
        file_type="xlsx"
    )
    
    if count > 0:
        print(f"✅ 添加成功，共 {count} 个文本块")
    else:
        print("❌ 添加失败")
    
    print("\n" + "=" * 60)
    print("✅ 测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_parse_excel()
