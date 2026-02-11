"""
DeepSeek/OpenAI 流式输出测试脚本
功能：
1. 流式输出思考内容（reasoning_content）
2. 流式输出最终回答内容
3. 识别并处理工具调用
"""

import json
from openai import OpenAI


# ==================== 配置 ====================
client = OpenAI(
    api_key="sk-bcff7c5f84b94262882cd4b7be499675",
    base_url="https://api.deepseek.com/v1",  # 或其他兼容 API
)


# ==================== 工具定义 ====================
def calculate(expression: str) -> str:
    """安全计算数学表达式"""
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return str(result)
    except Exception as e:
        return f"计算错误: {str(e)}"


def get_weather(city: str) -> str:
    """获取城市天气"""
    return f"{city} 天气晴朗，25°C"


# 工具注册表
TOOLS_REGISTRY = {
    "calculate": calculate,
    "get_weather": get_weather,
}

# 工具定义（用于 API）
AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "执行数学计算",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "数学表达式"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取城市天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名称"}},
                "required": ["city"],
            },
        },
    },
]


# ==================== 核心处理逻辑 ====================
class StreamProcessor:
    def __init__(self, client: OpenAI, model: str):
        self.client = client
        self.model = model
        self.tool_calls = {}  # 收集工具调用信息
        self.current_tool_id = None
        self.current_tool_name = None
        self.current_tool_args = ""
        self.thinking_content = ""
        self.final_content = ""
        self.mode = None  # 'thinking' | 'content' | None

    def _print_chunk(self, prefix: str, content: str):
        """打印增量内容（不换行）"""
        if self.mode != prefix:
            if self.mode is not None:
                print()
            print(f"[{prefix}]: ", end="", flush=True)
            self.mode = prefix
        print(content, end="", flush=True)

    def _process_delta(self, delta) -> tuple[bool, str, str]:
        """
        处理单个 delta，返回 (has_thinking, has_content, has_tools)
        """
        has_thinking = False
        has_content = False
        has_tools = False

        # 1. 处理思考内容
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            has_thinking = True
            self._print_chunk("思考", delta.reasoning_content)
            self.thinking_content += delta.reasoning_content

        # 2. 处理工具调用
        if hasattr(delta, "tool_calls") and delta.tool_calls:
            has_tools = True
            for tool_chunk in delta.tool_calls:
                # 保存工具调用 ID
                if tool_chunk.id and not self.current_tool_id:
                    self.current_tool_id = tool_chunk.id
                    print(f"\n[工具调用] ID: {tool_chunk.id}")

                # 收集工具名称
                if tool_chunk.function and tool_chunk.function.name:
                    self.current_tool_name = tool_chunk.function.name
                    print(f"[工具] 函数: {tool_chunk.function.name}")

                # 累积工具参数
                if tool_chunk.function and tool_chunk.function.arguments:
                    self.current_tool_args += tool_chunk.function.arguments

        # 3. 处理正式内容
        if hasattr(delta, "content") and delta.content:
            has_content = True
            self._print_chunk("回答", delta.content)
            self.final_content += delta.content

        return has_thinking, has_content, has_tools

    def _execute_tool(self, tool_name: str, arguments: str) -> str:
        """执行工具并返回结果"""
        print(f"\n[执行工具] {tool_name}({arguments})")

        if tool_name not in TOOLS_REGISTRY:
            return f"错误: 未知工具 '{tool_name}'"

        try:
            args_dict = json.loads(arguments)
            result = TOOLS_REGISTRY[tool_name](**args_dict)
            print(f"[工具结果] {result}")
            return result
        except json.JSONDecodeError as e:
            error_msg = f"参数解析错误: {e}"
            print(f"[工具错误] {error_msg}")
            return error_msg
        except Exception as e:
            error_msg = f"执行错误: {e}"
            print(f"[工具错误] {error_msg}")
            return error_msg

    def _build_assistant_message(
        self, content: str, thinking: str
    ) -> dict:
        """构建助手消息（包含思考内容和工具调用）"""
        message = {"role": "assistant", "content": content or None}

        # 添加思考内容（DeepSeek 专用）
        if thinking:
            message["reasoning_content"] = thinking

        # 添加工具调用
        if self.current_tool_id and self.current_tool_name:
            message["tool_calls"] = [
                {
                    "id": self.current_tool_id,
                    "type": "function",
                    "function": {
                        "name": self.current_tool_name,
                        "arguments": self.current_tool_args,
                    },
                }
            ]

        return message

    def chat(self, messages: list, stream: bool = True) -> str:
        """
        发送消息并处理流式响应

        Args:
            messages: 对话历史
            stream: 是否使用流式输出

        Returns:
            最终回答内容
        """
        print("=" * 50)
        print("[开始流式请求]")
        print(f"[模型] {self.model}")
        print(f"[消息数] {len(messages)}")
        print("=" * 50)

        # 重置状态
        self.tool_calls = {}
        self.current_tool_id = None
        self.current_tool_name = None
        self.current_tool_args = ""
        self.thinking_content = ""
        self.final_content = ""
        self.mode = None

        # 发送请求
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=AVAILABLE_TOOLS,
            stream=stream,
            extra_body={"showThinking": True} if "deepseek" in self.model else False,
        )

        if not stream:
            # 非流式响应处理
            choice = response.choices[0]
            if hasattr(choice.message, "reasoning_content"):
                self.thinking_content = choice.message.reasoning_content or ""
            self.final_content = choice.message.content or ""
            return self.final_content

        # 流式响应处理
        print()
        for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue
            self._process_delta(delta)

        if self.mode is not None:
            print()

        # 处理工具调用
        if self.current_tool_id and self.current_tool_name:
            print(f"\n[检测到工具调用]")
            print(f"  工具ID: {self.current_tool_id}")
            print(f"  工具名: {self.current_tool_name}")
            print(f"  参数: {self.current_tool_args}")

            # 执行工具
            tool_result = self._execute_tool(
                self.current_tool_name, self.current_tool_args
            )

            # 构建消息
            assistant_msg = self._build_assistant_message(
                self.final_content, self.thinking_content
            )

            tool_msg = {
                "role": "tool",
                "tool_call_id": self.current_tool_id,
                "content": tool_result,
            }

            # 第二次请求
            print(f"\n[第二次请求 - 获取最终回答]")
            new_messages = [messages[-1], assistant_msg, tool_msg]
            print(f"  消息数: {len(new_messages)}")

            second_response = self.client.chat.completions.create(
                model=self.model,
                messages=new_messages,
                stream=True,
                extra_body={"showThinking": False}
                if "deepseek" in self.model
                else False,
            )

            print()
            self.mode = None

            for chunk in second_response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue
                self._process_delta(delta)

            if self.mode is not None:
                print()

        # 输出总结
        print("\n" + "=" * 50)
        print("[处理完成]")
        print("=" * 50)

        if self.thinking_content:
            print(f"\n[思考内容] ({len(self.thinking_content)} 字符)")
            print("-" * 40)
            print(self.thinking_content)

        print(f"\n[最终回答] ({len(self.final_content)} 字符)")
        print("-" * 40)
        print(self.final_content)

        return self.final_content


# ==================== 测试用例 ====================
def test_math_calculation():
    """测试数学计算"""
    print("\n" + "#" * 60)
    print("# 测试1: 数学计算")
    print("#" * 60)

    processor = StreamProcessor(client, "deepseek-reasoner")
    messages = [
        {"role": "user", "content": "请计算 (15 * 3) + (28 / 4) 等于多少？并解释步骤。"}
    ]
    processor.chat(messages)


def test_weather():
    """测试天气查询"""
    print("\n" + "#" * 60)
    print("# 测试2: 天气查询")
    print("#" * 60)

    processor = StreamProcessor(client, "deepseek-reasoner")
    messages = [
        {"role": "user", "content": "请查询北京的天气。"}
    ]
    processor.chat(messages)


def test_no_tool():
    """测试无需工具的问题"""
    print("\n" + "#" * 60)
    print("# 测试3: 无需工具的问题")
    print("#" * 60)

    processor = StreamProcessor(client, "deepseek-reasoner")
    messages = [
        {"role": "user", "content": "你好，请介绍一下你自己。"}
    ]
    processor.chat(messages)


# ==================== 主程序 ====================
if __name__ == "__main__":
    # 选择测试用例
    test_math_calculation()
    test_weather()
    # test_no_tool()
