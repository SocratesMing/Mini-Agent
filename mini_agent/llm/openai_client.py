"""OpenAI LLM client implementation."""

import json
import logging
from typing import Any, AsyncGenerator

from openai import AsyncOpenAI

from ..retry import RetryConfig, async_retry
from ..schema import FunctionCall, LLMResponse, Message, TokenUsage, ToolCall
from .base import LLMClientBase

logger = logging.getLogger(__name__)


class OpenAIClient(LLMClientBase):
    """LLM client using OpenAI's protocol.

    This client uses the official OpenAI SDK and supports:
    - Reasoning content (via reasoning_split=True)
    - Tool calling
    - Retry logic
    """

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.minimaxi.com/v1",
        model: str = "MiniMax-M2.1",
        retry_config: RetryConfig | None = None,
    ):
        """Initialize OpenAI client.

        Args:
            api_key: API key for authentication
            api_base: Base URL for the API (default: MiniMax OpenAI endpoint)
            model: Model name to use (default: MiniMax-M2.1)
            retry_config: Optional retry configuration
        """
        super().__init__(api_key, api_base, model, retry_config)

        # Initialize OpenAI client
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
        )

    async def _make_api_request(
        self,
        api_messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
        enable_deep_think: bool = False,
    ) -> Any:
        """Execute API request (core method that can be retried).

        Args:
            api_messages: List of messages in OpenAI format
            tools: Optional list of tools
            enable_deep_think: Whether to enable deep thinking mode

        Returns:
            OpenAI ChatCompletion response (full response including usage)

        Raises:
            Exception: API call failed
        """
        logger.info("=" * 80)
        logger.info("[LLM] 开始API请求")
        logger.info("-" * 80)
        logger.info(f"[LLM] 请求参数:")
        logger.info(f"[LLM]   - model: {self.model}")
        logger.info(f"[LLM]   - api_base: {self.client.base_url}")
        logger.info(f"[LLM]   - enable_deep_think: {enable_deep_think}")
        logger.info(f"[LLM]   - messages_count: {len(api_messages)}")
        
        for i, msg in enumerate(api_messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str):
                content_preview = content[:100] + "..." if len(content) > 100 else content
            else:
                content_preview = str(content)[:100] + "..."
            logger.info(f"[LLM]   - message[{i}]: role={role}, content={content_preview}")
        
        if tools:
            logger.info(f"[LLM]   - tools_count: {len(tools)}")
            for i, tool in enumerate(tools):
                if isinstance(tool, dict) and "function" in tool:
                    tool_name = tool["function"].get("name", "unknown")
                elif hasattr(tool, "name"):
                    tool_name = tool.name
                else:
                    tool_name = "unknown"
                logger.info(f"[LLM]     - tool[{i}]: {tool_name}")
        
        params = {
            "model": self.model,
            "messages": api_messages,
        }

        # MiniMax API: 使用reasoning_enabled参数控制思考内容
        if enable_deep_think:
            params["extra_body"] = {"reasoning_split": True}
            logger.info(f"[LLM]   - extra_body: reasoning_split=True")
        else:
            # 禁用思考内容
            params["extra_body"] = {"reasoning_enabled": False}
            logger.info(f"[LLM]   - extra_body: reasoning_enabled=False")

        if tools:
            params["tools"] = self._convert_tools(tools)

        logger.info(f"[LLM] 发送请求到API...")
        response = await self.client.chat.completions.create(**params)
        
        logger.info(f"[LLM] 收到API响应")
        if hasattr(response, 'usage') and response.usage:
            logger.info(f"[LLM]   - usage: prompt_tokens={response.usage.prompt_tokens}, completion_tokens={response.usage.completion_tokens}, total_tokens={response.usage.total_tokens}")
        if response.choices and len(response.choices) > 0:
            msg = response.choices[0].message
            content_preview = (msg.content or "")[:100] + "..." if msg.content and len(msg.content) > 100 else msg.content
            logger.info(f"[LLM]   - content_preview: {content_preview}")
            if msg.tool_calls:
                logger.info(f"[LLM]   - tool_calls_count: {len(msg.tool_calls)}")
        logger.info("-" * 80)
        
        return response

    def _convert_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
        """Convert tools to OpenAI format.

        Args:
            tools: List of Tool objects or dicts

        Returns:
            List of tools in OpenAI dict format
        """
        result = []
        for tool in tools:
            if isinstance(tool, dict):
                # If already a dict, check if it's in OpenAI format
                if "type" in tool and tool["type"] == "function":
                    result.append(tool)
                else:
                    # Assume it's in Anthropic format, convert to OpenAI
                    result.append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool["name"],
                                "description": tool["description"],
                                "parameters": tool["input_schema"],
                            },
                        }
                    )
            elif hasattr(tool, "to_openai_schema"):
                # Tool object with to_openai_schema method
                result.append(tool.to_openai_schema())
            else:
                raise TypeError(f"Unsupported tool type: {type(tool)}")
        return result

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert internal messages to OpenAI format.

        Args:
            messages: List of internal Message objects

        Returns:
            Tuple of (system_message, api_messages)
            Note: OpenAI includes system message in the messages array
        """
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                # OpenAI includes system message in messages array
                api_messages.append({"role": "system", "content": msg.content})
                continue

            # For user messages
            if msg.role == "user":
                api_messages.append({"role": "user", "content": msg.content})

            # For assistant messages
            elif msg.role == "assistant":
                assistant_msg = {"role": "assistant"}

                # Add content if present
                if msg.content:
                    assistant_msg["content"] = msg.content

                # Add tool calls if present
                if msg.tool_calls:
                    tool_calls_list = []
                    for tool_call in msg.tool_calls:
                        tool_calls_list.append(
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": json.dumps(tool_call.function.arguments),
                                },
                            }
                        )
                    assistant_msg["tool_calls"] = tool_calls_list

                # IMPORTANT: Add reasoning_details if thinking is present
                # This is CRITICAL for Interleaved Thinking to work properly!
                # The complete response_message (including reasoning_details) must be
                # preserved in Message History and passed back to the model in the next turn.
                # This ensures the model's chain of thought is not interrupted.
                if msg.thinking:
                    assistant_msg["reasoning_details"] = [{"text": msg.thinking}]

                api_messages.append(assistant_msg)

            # For tool result messages
            elif msg.role == "tool":
                api_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                )

        return None, api_messages

    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        enable_deep_think: bool = False,
    ) -> dict[str, Any]:
        """Prepare the request for OpenAI API.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools
            enable_deep_think: Whether to enable deep thinking mode

        Returns:
            Dictionary containing request parameters
        """
        _, api_messages = self._convert_messages(messages)

        return {
            "api_messages": api_messages,
            "tools": tools,
            "enable_deep_think": enable_deep_think,
        }

    def _parse_response(self, response: Any, enable_deep_think: bool = False) -> LLMResponse:
        """Parse OpenAI response into LLMResponse.

        Args:
            response: OpenAI ChatCompletion response (full response object)
            enable_deep_think: Whether deep thinking mode was enabled

        Returns:
            LLMResponse object
        """
        # Get message from response
        message = response.choices[0].message

        # Extract text content
        text_content = message.content or ""

        # Extract thinking content from reasoning_details (only if deep think is enabled)
        thinking_content = ""
        if enable_deep_think and hasattr(message, "reasoning_details") and message.reasoning_details:
            # reasoning_details is a list of reasoning blocks
            for detail in message.reasoning_details:
                if hasattr(detail, "text"):
                    thinking_content += detail.text

        # Extract tool calls
        tool_calls = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                # Parse arguments from JSON string
                arguments = json.loads(tool_call.function.arguments)

                tool_calls.append(
                    ToolCall(
                        id=tool_call.id,
                        type="function",
                        function=FunctionCall(
                            name=tool_call.function.name,
                            arguments=arguments,
                        ),
                    )
                )

        # Extract token usage from response
        usage = None
        if hasattr(response, "usage") and response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
                total_tokens=response.usage.total_tokens or 0,
            )

        return LLMResponse(
            content=text_content,
            thinking=thinking_content if thinking_content else None,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason="stop",  # OpenAI doesn't provide finish_reason in the message
            usage=usage,
        )

    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        enable_deep_think: bool = False,
    ) -> LLMResponse:
        """Generate response from OpenAI LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools
            enable_deep_think: Whether to enable deep thinking mode

        Returns:
            LLMResponse containing the generated content
        """
        request_params = self._prepare_request(messages, tools, enable_deep_think)

        if self.retry_config.enabled:
            retry_decorator = async_retry(config=self.retry_config, on_retry=self.retry_callback)
            api_call = retry_decorator(self._make_api_request)
            response = await api_call(
                request_params["api_messages"],
                request_params["tools"],
                request_params["enable_deep_think"],
            )
        else:
            response = await self._make_api_request(
                request_params["api_messages"],
                request_params["tools"],
                request_params["enable_deep_think"],
            )

        return self._parse_response(response, enable_deep_think=request_params["enable_deep_think"])

    async def stream_generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        enable_deep_think: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Stream generate response from OpenAI LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of Tool objects or dicts
            enable_deep_think: Whether to enable deep thinking mode

        Yields:
            Text chunks as they are generated
        """
        logger.info("=" * 80)
        logger.info("[LLM_STREAM] 开始流式API请求")
        logger.info("-" * 80)
        
        _, api_messages = self._convert_messages(messages)
        
        logger.info(f"[LLM_STREAM] 请求参数:")
        logger.info(f"[LLM_STREAM]   - model: {self.model}")
        logger.info(f"[LLM_STREAM]   - api_base: {self.client.base_url}")
        logger.info(f"[LLM_STREAM]   - enable_deep_think: {enable_deep_think}")
        logger.info(f"[LLM_STREAM]   - messages_count: {len(api_messages)}")
        
        for i, msg in enumerate(api_messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str):
                content_preview = content[:100] + "..." if len(content) > 100 else content
            else:
                content_preview = str(content)[:100] + "..."
            logger.info(f"[LLM_STREAM]   - message[{i}]: role={role}, content={content_preview}")
        
        if tools:
            logger.info(f"[LLM_STREAM]   - tools_count: {len(tools)}")
            for i, tool in enumerate(tools):
                if isinstance(tool, dict) and "function" in tool:
                    tool_name = tool["function"].get("name", "unknown")
                elif hasattr(tool, "name"):
                    tool_name = tool.name
                else:
                    tool_name = "unknown"
                logger.info(f"[LLM_STREAM]     - tool[{i}]: {tool_name}")

        params = {
            "model": self.model,
            "messages": api_messages,
            "stream": True,
        }

        # MiniMax API: 使用reasoning_enabled参数控制思考内容
        if enable_deep_think:
            params["extra_body"] = {"reasoning_split": True}
            logger.info(f"[LLM_STREAM]   - extra_body: reasoning_split=True")
        else:
            # 禁用思考内容
            params["extra_body"] = {"reasoning_enabled": False}
            logger.info(f"[LLM_STREAM]   - extra_body: reasoning_enabled=False")

        if tools:
            params["tools"] = self._convert_tools(tools)

        logger.info(f"[LLM_STREAM] 发送流式请求到API...")
        response_stream = await self.client.chat.completions.create(**params)

        logger.info(f"[LLM_STREAM] 开始接收流式响应...")
        chunk_count = 0
        content_length = 0
        thinking_length = 0
        
        async for chunk in response_stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta:
                    if delta.content:
                        chunk_count += 1
                        content_length += len(delta.content)
                        yield delta.content
                    # 只有启用深度思考时才处理思考内容
                    if enable_deep_think and hasattr(delta, "reasoning_details") and delta.reasoning_details:
                        for detail in delta.reasoning_details:
                            if hasattr(detail, "text"):
                                thinking_length += len(detail.text)
                                yield f"[THINKING]{detail.text}[/THINKING]"
        
        logger.info(f"[LLM_STREAM] 流式响应完成")
        logger.info(f"[LLM_STREAM]   - 总chunk数: {chunk_count}")
        logger.info(f"[LLM_STREAM]   - 内容长度: {content_length}")
        logger.info(f"[LLM_STREAM]   - 思考内容长度: {thinking_length}")
        logger.info("-" * 80)
