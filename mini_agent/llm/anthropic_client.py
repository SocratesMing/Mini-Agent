"""Anthropic LLM client implementation."""

import json
import logging
from typing import Any, AsyncGenerator

import anthropic

from ..retry import RetryConfig, async_retry
from ..schema import FunctionCall, LLMResponse, Message, TokenUsage, ToolCall
from .base import LLMClientBase

logger = logging.getLogger(__name__)


class AnthropicClient(LLMClientBase):
    """LLM client using Anthropic's protocol.

    This client uses the official Anthropic SDK and supports:
    - Extended thinking content
    - Tool calling
    - Retry logic
    """

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.minimaxi.com/anthropic",
        model: str = "MiniMax-M2.5",
        retry_config: RetryConfig | None = None,
    ):
        """Initialize Anthropic client.

        Args:
            api_key: API key for authentication
            api_base: Base URL for the API (default: MiniMax Anthropic endpoint)
            model: Model name to use (default: MiniMax-M2.5)
            retry_config: Optional retry configuration
        """
        super().__init__(api_key, api_base, model, retry_config)

        # Initialize Anthropic async client
        self.client = anthropic.AsyncAnthropic(
            base_url=api_base,
            api_key=api_key,
            default_headers={"Authorization": f"Bearer {api_key}"},
        )

    async def _make_api_request(
        self,
        system_message: str | None,
        api_messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> anthropic.types.Message:
        """Execute API request (core method that can be retried).

        Args:
            system_message: Optional system message
            api_messages: List of messages in Anthropic format
            tools: Optional list of tools

        Returns:
            Anthropic Message response

        Raises:
            Exception: API call failed
        """
        params = {
            "model": self.model,
            "max_tokens": 16384,
            "messages": api_messages,
        }

        if system_message:
            params["system"] = system_message

        if tools:
            params["tools"] = self._convert_tools(tools)

        # Use Anthropic SDK's async messages.create
        response = await self.client.messages.create(**params)
        return response

    def _convert_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
        """Convert tools to Anthropic format.

        Anthropic tool format:
        {
            "name": "tool_name",
            "description": "Tool description",
            "input_schema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }

        Args:
            tools: List of Tool objects or dicts

        Returns:
            List of tools in Anthropic dict format
        """
        result = []
        for tool in tools:
            if isinstance(tool, dict):
                result.append(tool)
            elif hasattr(tool, "to_schema"):
                # Tool object with to_schema method
                result.append(tool.to_schema())
            else:
                raise TypeError(f"Unsupported tool type: {type(tool)}")
        return result

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert internal messages to Anthropic format.

        Args:
            messages: List of internal Message objects

        Returns:
            Tuple of (system_message, api_messages)
        """
        system_message = None
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
                continue

            # For user and assistant messages
            if msg.role in ["user", "assistant"]:
                # Handle assistant messages with thinking or tool calls
                if msg.role == "assistant" and (msg.thinking or msg.tool_calls):
                    # Build content blocks for assistant with thinking and/or tool calls
                    content_blocks = []

                    # Add thinking block if present
                    if msg.thinking:
                        content_blocks.append({"type": "thinking", "thinking": msg.thinking})

                    # Add text content if present
                    if msg.content:
                        content_blocks.append({"type": "text", "text": msg.content})

                    # Add tool use blocks
                    if msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            content_blocks.append(
                                {
                                    "type": "tool_use",
                                    "id": tool_call.id,
                                    "name": tool_call.function.name,
                                    "input": tool_call.function.arguments,
                                }
                            )

                    api_messages.append({"role": "assistant", "content": content_blocks})
                else:
                    api_messages.append({"role": msg.role, "content": msg.content})

            # For tool result messages
            elif msg.role == "tool":
                # Anthropic uses user role with tool_result content blocks
                api_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.content,
                            }
                        ],
                    }
                )

        return system_message, api_messages

    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare the request for Anthropic API.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            Dictionary containing request parameters
        """
        system_message, api_messages = self._convert_messages(messages)

        return {
            "system_message": system_message,
            "api_messages": api_messages,
            "tools": tools,
        }

    def _parse_response(self, response: anthropic.types.Message) -> LLMResponse:
        """Parse Anthropic response into LLMResponse.

        Args:
            response: Anthropic Message response

        Returns:
            LLMResponse object
        """
        # Extract text content, thinking, and tool calls
        text_content = ""
        thinking_content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "thinking":
                thinking_content += block.thinking
            elif block.type == "tool_use":
                # Parse Anthropic tool_use block
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        type="function",
                        function=FunctionCall(
                            name=block.name,
                            arguments=block.input,
                        ),
                    )
                )

        # Extract token usage from response
        # Anthropic usage includes: input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens
        usage = None
        if hasattr(response, "usage") and response.usage:
            input_tokens = response.usage.input_tokens or 0
            output_tokens = response.usage.output_tokens or 0
            cache_read_tokens = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            cache_creation_tokens = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
            total_input_tokens = input_tokens + cache_read_tokens + cache_creation_tokens
            usage = TokenUsage(
                prompt_tokens=total_input_tokens,
                completion_tokens=output_tokens,
                total_tokens=total_input_tokens + output_tokens,
            )

        return LLMResponse(
            content=text_content,
            thinking=thinking_content if thinking_content else None,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=response.stop_reason or "stop",
            usage=usage,
        )

    async def _make_streaming_request(
        self,
        system_message: str | None,
        api_messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ):
        """Execute streaming API request (core method that can be retried).

        Args:
            system_message: Optional system message
            api_messages: List of messages in Anthropic format
            tools: Optional list of tools

        Returns:
            Async iterator of Anthropic Message response events
        """
        params = {
            "model": self.model,
            "max_tokens": 16384,
            "messages": api_messages,
        }

        if system_message:
            params["system"] = system_message

        if tools:
            params["tools"] = self._convert_tools(tools)

        # Use Anthropic SDK's async messages.stream for streaming
        async with self.client.messages.stream(**params) as stream:
            async for event in stream:
                yield event

    async def stream_generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        enable_deep_think: bool = False,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Generate streaming response from Anthropic LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools
            enable_deep_think: Not supported for Anthropic (ignored)

        Yields:
            Dict with type and content
        """
        request_params = self._prepare_request(messages, tools)

        if self.retry_config.enabled:
            async def streaming_call():
                return self._make_streaming_request(
                    request_params["system_message"],
                    request_params["api_messages"],
                    request_params["tools"],
                )
            
            retry_decorator = async_retry(config=self.retry_config, on_retry=self.retry_callback)
            wrapped_stream = retry_decorator(streaming_call)
            stream_iterator = await wrapped_stream()
        else:
            stream_iterator = self._make_streaming_request(
                request_params["system_message"],
                request_params["api_messages"],
                request_params["tools"],
            )

        content_length = 0
        thinking_length = 0
        tool_calls_data = {}
        event_count = 0
        
        async for event in stream_iterator:
            event_count += 1
            
            if event_count <= 10:
                logger.debug(f"[LLM_STREAM] event {event_count}: type={event.type}")
            
            if event.type == "content_block_delta":
                if event.delta.type == "text_delta":
                    content_length += len(event.delta.text)
                    yield {"type": "content", "content": event.delta.text}
                elif event.delta.type == "thinking_delta":
                    thinking_length += len(event.delta.thinking)
                    yield {"type": "thinking", "content": event.delta.thinking}
                elif event.delta.type == "input_json_delta":
                    if hasattr(event, 'index'):
                        idx = event.index
                        if idx in tool_calls_data:
                            partial_json = getattr(event.delta, 'partial_json', '')
                            if isinstance(partial_json, dict):
                                partial_json = json.dumps(partial_json)
                            tool_calls_data[idx]["arguments"] += str(partial_json)
            
            elif event.type == "content_block_start":
                if hasattr(event, "content_block") and event.content_block:
                    if event.content_block.type == "thinking":
                        if hasattr(event.content_block, "thinking"):
                            thinking_length += len(event.content_block.thinking)
                            yield {"type": "thinking", "content": event.content_block.thinking}
                    elif event.content_block.type == "text":
                        if hasattr(event.content_block, "text"):
                            content_length += len(event.content_block.text)
                            yield {"type": "content", "content": event.content_block.text}
                    elif event.content_block.type == "tool_use":
                        idx = event.index if hasattr(event, 'index') else len(tool_calls_data)
                        tool_calls_data[idx] = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "arguments": ""
                        }
                        yield {
                            "type": "tool_call_start",
                            "tool_name": event.content_block.name,
                            "tool_call_id": event.content_block.id
                        }
        
        tool_calls = []
        for idx, tc in tool_calls_data.items():
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({
                "id": tc["id"],
                "name": tc["name"],
                "arguments": args
            })
        
        logger.info(f"[LLM_STREAM] 流式响应完成")
        logger.info(f"[LLM_STREAM]   - 内容长度: {content_length}")
        logger.info(f"[LLM_STREAM]   - 思考内容长度: {thinking_length}")
        logger.info(f"[LLM_STREAM]   - 工具调用数: {len(tool_calls)}")
        
        yield {"type": "done", "tool_calls": tool_calls}

    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        enable_deep_think: bool = False,
    ) -> LLMResponse:
        """Generate response from Anthropic LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools
            enable_deep_think: Not supported for Anthropic (ignored)

        Returns:
            LLMResponse containing the generated content
        """
        # Prepare request
        request_params = self._prepare_request(messages, tools)

        # Make API request with retry logic
        if self.retry_config.enabled:
            # Apply retry logic
            retry_decorator = async_retry(config=self.retry_config, on_retry=self.retry_callback)
            api_call = retry_decorator(self._make_api_request)
            response = await api_call(
                request_params["system_message"],
                request_params["api_messages"],
                request_params["tools"],
            )
        else:
            # Don't use retry
            response = await self._make_api_request(
                request_params["system_message"],
                request_params["api_messages"],
                request_params["tools"],
            )

        # Parse and return response
        return self._parse_response(response)
