"""Ollama 服务测试脚本

用于测试 Ollama 服务的可用性和性能
"""

import time
import requests


def check_ollama_service(base_url: str = "http://localhost:11434", model: str = "qwen3-embedding:latest"):
    """检查 Ollama 服务状态"""

    print("=" * 60)
    print("Ollama 服务测试")
    print("=" * 60)

    print(f"\n1. 检查服务可用性...")
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        if response.status_code == 200:
            print(f"   ✅ Ollama 服务正常运行")
            models = response.json().get("models", [])
            print(f"   已加载模型数量: {len(models)}")
            for m in models:
                print(f"   - {m.get('name', 'unknown')}")
        else:
            print(f"   ❌ Ollama 服务返回错误: {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        print(f"   ❌ 连接超时")
        return False
    except requests.exceptions.ConnectionError:
        print(f"   ❌ 无法连接到 Ollama 服务 (http://localhost:11434)")
        print(f"   请确保 Ollama 服务已启动: ollama serve")
        return False
    except Exception as e:
        print(f"   ❌ 错误: {e}")
        return False

    print(f"\n2. 检查指定模型是否存在...")
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        models = [m.get('name', '') for m in response.json().get("models", [])]
        if model in models:
            print(f"   ✅ 模型 '{model}' 已存在")
        else:
            print(f"   ⚠️ 模型 '{model}' 未找到，可用模型:")
            for m in models:
                print(f"   - {m}")
            print(f"\n   请拉取模型: ollama pull {model}")
    except Exception as e:
        print(f"   ❌ 错误: {e}")

    return True


def test_embedding_performance(base_url: str = "http://localhost:11434", model: str = "qwen3-embedding:latest"):
    """测试 Embedding 性能"""

    print(f"\n3. 测试 Embedding 性能...")

    test_texts = [
        "这是一个测试文本",
        "这是一个较长的测试文本，用于测试embedding的速度和性能表现。",
    ]

    for i, text in enumerate(test_texts, 1):
        print(f"\n   测试 {i}: \"{text[:30]}...\"")

        start_time = time.time()
        try:
            response = requests.post(
                f"{base_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=60
            )
            elapsed = time.time() - start_time

            if response.status_code == 200:
                result = response.json()
                embedding = result.get("embedding", [])
                print(f"   ✅ 成功 | 向量维度: {len(embedding)} | 耗时: {elapsed:.2f}秒")
            else:
                print(f"   ❌ 失败: {response.status_code} - {response.text}")
        except requests.exceptions.Timeout:
            elapsed = time.time() - start_time
            print(f"   ❌ 超时 (>{elapsed:.2f}秒)")
        except Exception as e:
            print(f"   ❌ 错误: {e}")

    print(f"\n4. 批量测试...")
    batch_size = 5
    batch_texts = [f"测试文本编号 {j}" for j in range(batch_size)]

    print(f"\n   批量提交 {batch_size} 个短文本...")
    start_time = time.time()
    success_count = 0

    for j, text in enumerate(batch_texts, 1):
        try:
            response = requests.post(
                f"{base_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=30
            )
            if response.status_code == 200:
                success_count += 1
        except Exception:
            pass

    elapsed = time.time() - start_time
    print(f"   完成: {success_count}/{batch_size} 成功 | 总耗时: {elapsed:.2f}秒")
    if success_count > 0:
        print(f"   平均每条: {elapsed/success_count:.2f}秒")


def test_concurrent_embedding(base_url: str = "http://localhost:11434", model: str = "qwen3-embedding:latest"):
    """测试并发 Embedding"""

    import concurrent.futures

    print(f"\n5. 并发测试 (5个线程同时请求)...")

    def single_embedding(text: str, thread_id: int) -> tuple:
        start_time = time.time()
        try:
            response = requests.post(
                f"{base_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=60
            )
            elapsed = time.time() - start_time
            return (thread_id, response.status_code == 200, elapsed)
        except Exception:
            elapsed = time.time() - start_time
            return (thread_id, False, elapsed)

    threads = 5
    texts = [f"并发测试文本 {i}" for i in range(threads)]

    start_time = time.time()
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(single_embedding, text, i) for i, text in enumerate(texts)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    total_elapsed = time.time() - start_time

    success = sum(1 for r in results if r[1])
    print(f"   完成: {success}/{threads} 成功 | 总耗时: {total_elapsed:.2f}秒")

    for thread_id, ok, elapsed in sorted(results):
        status = "✅" if ok else "❌"
        print(f"   线程 {thread_id}: {status} {elapsed:.2f}秒")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ollama 服务测试")
    parser.add_argument("--url", default="http://localhost:11434", help="Ollama 服务地址")
    parser.add_argument("--model", default="qwen3-embedding:latest", help="Embedding 模型名称")
    args = parser.parse_args()

    if check_ollama_service(args.url, args.model):
        test_embedding_performance(args.url, args.model)
        test_concurrent_embedding(args.url, args.model)

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
