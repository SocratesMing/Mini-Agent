"""OpenAI LLM client implementation."""

import json
import logging
import time
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
        model: str = "MiniMax-M2.5",
        retry_config: RetryConfig | None = None,
    ):
        """Initialize OpenAI client.

        Args:
            api_key: API key for authentication
            api_base: Base URL for the API (default: MiniMax OpenAI endpoint)
            model: Model name to use (default: MiniMax-M2.5)
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
        logger.info(f"开始API请求 | model={self.model} | messages={len(api_messages)} | deep_think={enable_deep_think}")
        
        params = {
            "model": self.model,
            "messages": api_messages,
        }

        if enable_deep_think:
            params["extra_body"] = {"reasoning_split": True}
        else:
            params["extra_body"] = {"reasoning_enabled": False}

        if tools:
            params["tools"] = self._convert_tools(tools)

        response = await self.client.chat.completions.create(**params)
        
        if hasattr(response, 'usage') and response.usage:
            logger.info(f"API响应 | prompt={response.usage.prompt_tokens} | completion={response.usage.completion_tokens} | total={response.usage.total_tokens}")
        
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

                # DeepSeek thinking mode: add reasoning_content for tool calls
                if msg.thinking:
                    assistant_msg["reasoning_content"] = msg.thinking

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
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream generate response from OpenAI LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of Tool objects or dicts
            enable_deep_think: Whether to enable deep thinking mode

        Yields:
            Dict with type and content
        """
        _, api_messages = self._convert_messages(messages)
        logger.info(f"model={self.model} | messages={len(api_messages)} | deep_think={enable_deep_think}")
        
        params = {
            "model": self.model,
            "messages": api_messages,
            "stream": True,
        }

        if enable_deep_think:
            params["extra_body"] = {"reasoning_split": True}
        else:
            params["extra_body"] = {"reasoning_enabled": False}

        if tools:
            params["tools"] = self._convert_tools(tools)

        response_stream = await self.client.chat.completions.create(**params)

        chunk_count = 0
        content_length = 0
        thinking_length = 0
        tool_calls_data = {}
        thinking_started = False
        thinking_start_time = None
        thinking_duration_value = None
        full_thinking = ""
        full_content = ""
        
        async for chunk in response_stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                
                if enable_deep_think and hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    if not thinking_started:
                        thinking_started = True
                        thinking_start_time = time.time()
                        logger.info(f"思考开始")
                        yield {"type": "thinking_start", "content": ""}
                    thinking_length += len(delta.reasoning_content)
                    full_thinking += delta.reasoning_content
                    yield {"type": "thinking", "content": delta.reasoning_content}
                
                if delta.content:
                    if thinking_started and thinking_start_time:
                        thinking_duration_value = round(time.time() - thinking_start_time, 1)
                        logger.info(f"思考结束 | 用时: {thinking_duration_value}s")
                        yield {"type": "thinking_end", "duration": thinking_duration_value}
                        thinking_started = False
                    chunk_count += 1
                    content_length += len(delta.content)
                    full_content += delta.content
                    yield {"type": "content", "content": delta.content}
                
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        idx = tool_call.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {
                                "id": tool_call.id or "",
                                "name": "",
                                "arguments": ""
                            }
                            if tool_call.id:
                                yield {
                                    "type": "tool_call_start",
                                    "tool_call_id": tool_call.id,
                                    "tool_name": ""
                                }
                        
                        if tool_call.function:
                            if tool_call.function.name:
                                tool_calls_data[idx]["name"] = tool_call.function.name
                                yield {
                                    "type": "tool_call_start",
                                    "tool_call_id": tool_calls_data[idx]["id"],
                                    "tool_name": tool_call.function.name
                                }
                            if tool_call.function.arguments:
                                tool_calls_data[idx]["arguments"] += tool_call.function.arguments
                                yield {
                                    "type": "tool_call_args",
                                    "tool_call_id": tool_calls_data[idx]["id"],
                                    "arguments": tool_call.function.arguments
                                }
        
        final_tool_calls = []
        for idx in sorted(tool_calls_data.keys()):
            tc = tool_calls_data[idx]
            if tc["name"]:
                final_tool_calls.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"]
                    }
                })
        
        if thinking_started and thinking_start_time:
            thinking_duration_value = round(time.time() - thinking_start_time, 1)
            logger.info(f"思考结束 | 用时: {thinking_duration_value}s")
            yield {"type": "thinking_end", "duration": thinking_duration_value}
        
        logger.info(f"完成 | chunks={chunk_count} | content={content_length} | thinking={thinking_length} | thinking_duration={thinking_duration_value} | tool_calls={len(final_tool_calls)}")
        
        if full_thinking:
            logger.info(f"思考内容:\n{full_thinking}")
        if full_content:
            logger.info(f"正式内容:\n{full_content}")
        if final_tool_calls:
            for tc in final_tool_calls:
                logger.info(f"工具调用: {tc['function']['name']} | 参数: {tc['function']['arguments']}")
        
        yield {"type": "done", "tool_calls": final_tool_calls}
