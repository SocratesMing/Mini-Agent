"""流式响应日志记录器."""

import json
import logging
from datetime import datetime


class StreamLogger:
    """流式响应日志记录器."""

    def __init__(self, session_id: str, message_id: str, user_message: str):
        self.session_id = session_id
        self.message_id = message_id
        self.user_message = user_message
        self.start_time = datetime.now()
        self.chunk_count = 0
        self.thinking_count = 0
        self.tool_calls = []
        self._logger = logging.getLogger("mini_agent.chat")
        self._content_buffer = ""

    def log_request(self):
        """记录请求开始."""
        self._logger.info(f"=" * 50)
        self._logger.info(f"📥 收到聊天请求")
        self._logger.info(f"  会话ID: {self.session_id}")
        self._logger.info(f" 消息ID: {self.message_id}")
        self._logger.info(f"  用户消息: {self.user_message}")
        self._logger.info(f"=" * 50)

    def log_llm_request(self, messages: list, tools: list):
        """记录 LLM 请求信息."""
        self._logger.info(f"=" * 50)
        self._logger.info(f"📤 发送请求到 LLM")
        self._logger.info(f"  消息数: {len(messages)}")
        self._logger.info(f"  工具数: {len(tools)}")

        for i, msg in enumerate(messages, 1):
            if hasattr(msg, 'role'):
                role = msg.role
                content = getattr(msg, 'content', '')
            else:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
            self._logger.info(f"  消息[{i}] role={role}: {content}")

        for tool in tools:
            if hasattr(tool, 'name'):
                tool_name = tool.name
                tool_desc = getattr(tool, 'description', '')
            else:
                tool_name = tool.get('name', 'unknown')
                tool_desc = tool.get('description', '')
            self._logger.info(f"  🔧 工具: {tool_name} - {tool_desc}")
        self._logger.info(f"=" * 50)

    def log_thinking(self, thinking: str):
        """记录思考内容."""
        self.thinking_count += 1
        self._logger.info(f"🧠 思考 #{self.thinking_count}: {thinking}")

    def log_content_chunk(self, chunk: str, is_first: bool):
        """记录内容块."""
        self._content_buffer += chunk
        if is_first:
            self._logger.info("🤖 开始生成响应")

    def log_tool_call(self, tool_name: str, arguments: dict):
        """记录工具调用."""
        self.tool_calls.append(tool_name)
        self._logger.info(f"=" * 50)
        self._logger.info(f"🔧 工具调用")
        self._logger.info(f"  工具名称: {tool_name}")
        self._logger.info(f"  参数: {json.dumps(arguments, ensure_ascii=False, indent=2)}")
        self._logger.info(f"=" * 50)

    def log_tool_result(self, tool_name: str, success: bool, result: str = None):
        """记录工具执行结果."""
        status = "成功 ✓" if success else "失败 ✗"
        self._logger.info(f"=" * 50)
        self._logger.info(f"📋 工具执行结果")
        self._logger.info(f"  工具名称: {tool_name}")
        self._logger.info(f"  执行状态: {status}")
        if result:
            self._logger.info(f"  执行结果: {result}")
        self._logger.info(f"=" * 50)

    def log_response_complete(self, full_response: str, thinking: str = None):
        """记录响应完成."""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        self._logger.info(f"=" * 50)
        self._logger.info(f"✅ 响应完成")
        self._logger.info(f"  耗时: {elapsed:.2f}s")
        self._logger.info(f"  字符数: {len(full_response)}")
        self._logger.info(f"  思考事件数: {self.thinking_count}")
        self._logger.info(f"  工具调用数: {len(self.tool_calls)}")
        if thinking:
            self._logger.info(f"  思考内容: {thinking}")
        if full_response:
            self._logger.info(f"  完整响应内容:\n{full_response}")
        self._logger.info(f"=" * 50)

    def log_error(self, error: str):
        """记录错误."""
        self._logger.error(f"错误: {error}")
