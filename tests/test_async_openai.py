import asyncio
import os
from openai import AsyncOpenAI

# 初始化异步客户端
client = AsyncOpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),  # 从环境变量读取，或直接填写
    base_url="https://api.deepseek.com/v1",      # DeepSeek API 地址
)

async def main():
    try:
        # 发起流式请求
        stream = await client.chat.completions.create(
            model="deepseek-reasoner",           # 推理模型名称
            messages=[
                {"role": "user", "content": "请解释一下量子计算的基本原理。"}
            ],
            stream=True,                          # 启用流式返回
        )

        print("===== 思考过程 =====")
        reasoning_content = ""   # 累积思考内容
        content = ""             # 累积正式内容
        is_reasoning = True       # 标记是否还在思考阶段（仅用于打印提示）

        # 异步迭代流式响应
        async for chunk in stream:
            # 获取当前块中的增量内容
            delta = chunk.choices[0].delta

            # 处理思考内容（如果有）
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content is not None:
                # 如果之前已切换到正式内容，此处可以添加分隔提示，但一般思考内容先于正式内容出现
                reasoning_chunk = delta.reasoning_content
                reasoning_content += reasoning_chunk
                print(reasoning_chunk, end='', flush=True)  # 实时打印思考内容

            # 处理正式内容（如果有）
            if hasattr(delta, 'content') and delta.content is not None:
                # 如果刚进入正式内容阶段，打印一个分隔提示（可选）
                if is_reasoning and reasoning_content:
                    print("\n\n===== 正式回答 =====")
                    is_reasoning = False
                content_chunk = delta.content
                content += content_chunk
                print(content_chunk, end='', flush=True)  # 实时打印正式内容

        # 打印完整的累积内容（可选，因为上面已实时打印）
        print("\n\n===== 完整内容汇总 =====")
        print(f"思考过程：\n{reasoning_content}")
        print(f"\n正式回答：\n{content}")

    except Exception as e:
        print(f"\n调用失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())