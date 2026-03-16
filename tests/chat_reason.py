"""
DeepSeek 思考内容打印 Demo
功能：
1. 流式输出思考内容（reasoning_content）
2. 流式输出正式回答内容
"""

from openai import OpenAI



API_KEY = "sk-bcff7c5f84b94262882cd4b7be499675"  # 替换为你的 API Key
MODEL = "deepseek-reasoner"  # 或 deepseek-chat


client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com/v1",
)


def stream_chat():
    """流式对话，区分思考内容和回答内容"""
    
    messages = [
        {"role": "user", "content": "请计算 123 * 456 的结果，并解释计算过程"}
    ]
    
    print("=" * 60)
    print("[请求] DeepSeek 流式输出")
    print(f"[模型] {MODEL}")
    print("=" * 60)
    print()
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=True,
    )
    
    thinking_content = ""
    answer_content = ""
    current_mode = None  # 'thinking' | 'answer' | None
    
    for chunk in response:
        delta = chunk.choices[0].delta if chunk.choices else None
        if not delta:
            continue
        
        # 处理思考内容
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            if current_mode != "thinking":
                if current_mode is not None:
                    print()
                print("[思考中] ", end="", flush=True)
                current_mode = "thinking"
            
            print(delta.reasoning_content, end="", flush=True)
            thinking_content += delta.reasoning_content
        
        # 处理回答内容
        if hasattr(delta, "content") and delta.content:
            if current_mode != "answer":
                if current_mode is not None:
                    print()
                print("[回答] ", end="", flush=True)
                current_mode = "answer"
            
            print(delta.content, end="", flush=True)
            answer_content += delta.content
    
    if current_mode is not None:
        print()
    
    print()
    print("=" * 60)
    print("[完成]")
    print(f"[思考内容长度] {len(thinking_content)} 字符")
    print(f"[回答内容长度] {len(answer_content)} 字符")
    print("=" * 60)
    
    return answer_content


def non_stream_chat():
    """非流式对话"""
    
    messages = [
        {"role": "user", "content": "什么是量子计算？请用一句话解释"}
    ]
    
    print("=" * 60)
    print("[请求] DeepSeek 非流式输出")
    print("=" * 60)
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=False,
    )
    
    message = response.choices[0].message
    
    # 获取思考内容
    thinking = getattr(message, "reasoning_content", "") or ""
    if thinking:
        print()
        print("[思考内容]")
        print(thinking)
        print()
    
    # 获取回答内容
    answer = message.content or ""
    print("[回答]")
    print(answer)
    print("=" * 60)
    
    return answer


if __name__ == "__main__":
    # 流式输出示例
    print("\n===== 流式输出示例 =====\n")
    stream_chat()
    
    # 非流式输出示例
    print("\n===== 非流式输出示例 =====\n")
    non_stream_chat()
