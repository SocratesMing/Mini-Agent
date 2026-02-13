"""Core Agent implementation."""

import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import AsyncGenerator, Optional

import tiktoken

from .llm import LLMClient
from .logger import AgentLogger
from .schema import LLMResponse, Message
from .tools.base import Tool, ToolResult
from .utils import calculate_display_width


# ANSI color codes
class Colors:
    """Terminal color definitions"""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"


class Agent:
    """Single agent with basic tools and MCP support."""

    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str,
        tools: list[Tool],
        max_steps: int = 50,
        workspace_dir: str = "./workspace",
        token_limit: int = 80000,
    ):
        self.llm = llm_client
        self.tools = {tool.name: tool for tool in tools}
        self.max_steps = max_steps
        self.token_limit = token_limit
        self.workspace_dir = Path(workspace_dir)
        self.cancel_event: Optional[asyncio.Event] = None

        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        if "Current Workspace" not in system_prompt:
            workspace_info = f"\n\n## Current Workspace\nYou are currently working in: `{self.workspace_dir.absolute()}`\nAll relative paths will be resolved relative to this directory."
            system_prompt = system_prompt + workspace_info

        self.system_prompt = system_prompt

        self.messages: list[Message] = [Message(role="system", content=system_prompt)]

        self.logger = AgentLogger()

        self.api_total_tokens: int = 0
        self._skip_next_token_check: bool = False

    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.messages.append(Message(role="user", content=content))

    def _check_cancelled(self) -> bool:
        """Check if agent execution has been cancelled."""
        if self.cancel_event is not None and self.cancel_event.is_set():
            return True
        return False

    def _cleanup_incomplete_messages(self):
        """Remove the incomplete assistant message and its partial tool results."""
        last_assistant_idx = -1
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].role == "assistant":
                last_assistant_idx = i
                break

        if last_assistant_idx == -1:
            return

        removed_count = len(self.messages) - last_assistant_idx
        if removed_count > 0:
            self.messages = self.messages[:last_assistant_idx]
            print(f"{Colors.DIM}   Cleaned up {removed_count} incomplete message(s){Colors.RESET}")

    def _estimate_tokens(self) -> int:
        """Accurately calculate token count for message history using tiktoken"""
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            return self._estimate_tokens_fallback()

        total_tokens = 0

        for msg in self.messages:
            if isinstance(msg.content, str):
                total_tokens += len(encoding.encode(msg.content))
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        total_tokens += len(encoding.encode(str(block)))

            if msg.thinking:
                total_tokens += len(encoding.encode(msg.thinking))

            if msg.tool_calls:
                total_tokens += len(encoding.encode(str(msg.tool_calls)))

            total_tokens += 4

        return total_tokens

    def _estimate_tokens_fallback(self) -> int:
        """Fallback token estimation method (when tiktoken is unavailable)"""
        total_chars = 0
        for msg in self.messages:
            if isinstance(msg.content, str):
                total_chars += len(msg.content)
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        total_chars += len(str(block))

            if msg.thinking:
                total_chars += len(msg.thinking)

            if msg.tool_calls:
                total_chars += len(str(msg.tool_calls))

        return int(total_chars / 2.5)

    async def _summarize_messages(self):
        """Message history summarization: summarize conversations between user messages when tokens exceed limit"""
        if self._skip_next_token_check:
            self._skip_next_token_check = False
            return

        estimated_tokens = self._estimate_tokens()

        should_summarize = estimated_tokens > self.token_limit or self.api_total_tokens > self.token_limit

        if not should_summarize:
            return

        print(
            f"\n{Colors.BRIGHT_YELLOW}📊 Token usage - Local estimate: {estimated_tokens}, API reported: {self.api_total_tokens}, Limit: {self.token_limit}{Colors.RESET}"
        )
        print(f"{Colors.BRIGHT_YELLOW}🔄 Triggering message history summarization...{Colors.RESET}")

        user_indices = [i for i, msg in enumerate(self.messages) if msg.role == "user" and i > 0]

        if len(user_indices) < 1:
            print(f"{Colors.BRIGHT_YELLOW}⚠️  Insufficient messages, cannot summarize{Colors.RESET}")
            return

        new_messages = [self.messages[0]]
        summary_count = 0

        for i, user_idx in enumerate(user_indices):
            new_messages.append(self.messages[user_idx])

            if i < len(user_indices) - 1:
                next_user_idx = user_indices[i + 1]
            else:
                next_user_idx = len(self.messages)

            execution_messages = self.messages[user_idx + 1 : next_user_idx]

            if execution_messages:
                summary_text = await self._create_summary(execution_messages, i + 1)
                if summary_text:
                    summary_message = Message(
                        role="user",
                        content=f"[Assistant Execution Summary]\n\n{summary_text}",
                    )
                    new_messages.append(summary_message)
                    summary_count += 1

        self.messages = new_messages

        self._skip_next_token_check = True

        new_tokens = self._estimate_tokens()
        print(f"{Colors.BRIGHT_GREEN}✓ Summary completed, local tokens: {estimated_tokens} → {new_tokens}{Colors.RESET}")
        print(f"{Colors.DIM}  Structure: system + {len(user_indices)} user messages + {summary_count} summaries{Colors.RESET}")

    async def _create_summary(self, messages: list[Message], round_num: int) -> str:
        """Create summary for one execution round"""
        if not messages:
            return ""

        summary_content = f"Round {round_num} execution process:\n\n"
        for msg in messages:
            if msg.role == "assistant":
                content_text = msg.content if isinstance(msg.content, str) else str(msg.content)
                summary_content += f"Assistant: {content_text}\n"
                if msg.tool_calls:
                    tool_names = [tc.function.name for tc in msg.tool_calls]
                    summary_content += f"  → Called tools: {', '.join(tool_names)}\n"
            elif msg.role == "tool":
                result_preview = msg.content if isinstance(msg.content, str) else str(msg.content)
                summary_content += f"  ← Tool returned: {result_preview}...\n"

        try:
            summary_prompt = f"""Please provide a concise summary of the following Agent execution process:

{summary_content}

Requirements:
1. Focus on what tasks were completed and which tools were called
2. Keep key execution results and important findings
3. Be concise and clear, within 1000 words
4. Use English
5. Do not include "user" related content, only summarize the Agent's execution process"""

            summary_msg = Message(role="user", content=summary_prompt)
            response = await self.llm.generate(
                messages=[
                    Message(
                        role="system",
                        content="You are an assistant skilled at summarizing Agent execution processes.",
                    ),
                    summary_msg,
                ]
            )

            summary_text = response.content
            print(f"{Colors.BRIGHT_GREEN}✓ Summary for round {round_num} generated successfully{Colors.RESET}")
            return summary_text

        except Exception as e:
            print(f"{Colors.BRIGHT_RED}✗ Summary generation failed for round {round_num}: {e}{Colors.RESET}")
            return summary_content

    async def run(self, user_message: str = "", cancel_event: Optional[asyncio.Event] = None, enable_deep_think: bool = False) -> str:
        """Execute agent loop until task is complete or max steps reached."""
        if cancel_event is not None:
            self.cancel_event = cancel_event

        self.logger.start_new_run()
        print(f"{Colors.DIM}📝 Log file: {self.logger.get_log_file_path()}{Colors.RESET}")

        if user_message:
            self.add_user_message(user_message)

        step = 0
        run_start_time = perf_counter()

        while step < self.max_steps:
            if self._check_cancelled():
                self._cleanup_incomplete_messages()
                cancel_msg = "Task cancelled by user."
                print(f"\n{Colors.BRIGHT_YELLOW}⚠️  {cancel_msg}{Colors.RESET}")
                return cancel_msg

            step_start_time = perf_counter()
            await self._summarize_messages()

            BOX_WIDTH = 58
            step_text = f"{Colors.BOLD}{Colors.BRIGHT_CYAN}💭 Step {step + 1}/{self.max_steps}{Colors.RESET}"
            step_display_width = calculate_display_width(step_text)
            padding = max(0, BOX_WIDTH - 1 - step_display_width)

            print(f"\n{Colors.DIM}╭{'─' * BOX_WIDTH}╮{Colors.RESET}")
            print(f"{Colors.DIM}│{Colors.RESET} {step_text}{' ' * padding}{Colors.DIM}│{Colors.RESET}")
            print(f"{Colors.DIM}╰{'─' * BOX_WIDTH}╯{Colors.RESET}")

            tool_list = list(self.tools.values())

            self.logger.log_request(messages=self.messages, tools=tool_list)

            try:
                response = await self.llm.generate(messages=self.messages, tools=tool_list)
            except Exception as e:
                from .retry import RetryExhaustedError

                if isinstance(e, RetryExhaustedError):
                    error_msg = f"LLM call failed after {e.attempts} retries\nLast error: {str(e.last_exception)}"
                    print(f"\n{Colors.BRIGHT_RED}❌ Retry failed:{Colors.RESET} {error_msg}")
                else:
                    error_msg = f"LLM call failed: {str(e)}"
                    print(f"\n{Colors.BRIGHT_RED}❌ Error:{Colors.RESET} {error_msg}")
                return error_msg

            if response.usage:
                self.api_total_tokens = response.usage.total_tokens

            self.logger.log_response(
                content=response.content,
                thinking=response.thinking,
                tool_calls=response.tool_calls,
                finish_reason=response.finish_reason,
            )

            assistant_msg = Message(
                role="assistant",
                content=response.content,
                thinking=response.thinking,
                tool_calls=response.tool_calls,
            )
            self.messages.append(assistant_msg)

            if response.thinking:
                print(f"\n{Colors.BOLD}{Colors.MAGENTA}🧠 Thinking:{Colors.RESET}")
                print(f"{Colors.DIM}{response.thinking}{Colors.RESET}")

            if response.content:
                print(f"\n{Colors.BOLD}{Colors.BRIGHT_BLUE}🤖 Assistant:{Colors.RESET}")
                print(f"{response.content}")

            if not response.tool_calls:
                step_elapsed = perf_counter() - step_start_time
                total_elapsed = perf_counter() - run_start_time
                print(f"\n{Colors.DIM}⏱️  Step {step + 1} completed in {step_elapsed:.2f}s (total: {total_elapsed:.2f}s){Colors.RESET}")
                return response.content

            if self._check_cancelled():
                self._cleanup_incomplete_messages()
                cancel_msg = "Task cancelled by user."
                print(f"\n{Colors.BRIGHT_YELLOW}⚠️  {cancel_msg}{Colors.RESET}")
                return cancel_msg

            for tool_call in response.tool_calls:
                tool_call_id = tool_call.id
                function_name = tool_call.function.name
                arguments = tool_call.function.arguments

                print(f"\n{Colors.BRIGHT_YELLOW}🔧 Tool Call:{Colors.RESET} {Colors.BOLD}{Colors.CYAN}{function_name}{Colors.RESET}")

                print(f"{Colors.DIM}   Arguments:{Colors.RESET}")
                truncated_args = {}
                for key, value in arguments.items():
                    value_str = str(value)
                    if len(value_str) > 200:
                        truncated_args[key] = value_str[:200] + "..."
                    else:
                        truncated_args[key] = value
                args_json = json.dumps(truncated_args, indent=2, ensure_ascii=False)
                for line in args_json.split("\n"):
                    print(f"   {Colors.DIM}{line}{Colors.RESET}")

                if function_name not in self.tools:
                    result = ToolResult(
                        success=False,
                        content="",
                        error=f"Unknown tool: {function_name}",
                    )
                else:
                    try:
                        tool = self.tools[function_name]
                        result = await tool.execute(**arguments)
                    except Exception as e:
                        import traceback

                        error_detail = f"{type(e).__name__}: {str(e)}"
                        error_trace = traceback.format_exc()
                        result = ToolResult(
                            success=False,
                            content="",
                            error=f"Tool execution failed: {error_detail}\n\nTraceback:\n{error_trace}",
                        )

                self.logger.log_tool_result(
                    tool_name=function_name,
                    arguments=arguments,
                    result_success=result.success,
                    result_content=result.content if result.success else None,
                    result_error=result.error if not result.success else None,
                )

                if result.success:
                    result_text = result.content
                    if len(result_text) > 300:
                        result_text = result_text[:300] + f"{Colors.DIM}...{Colors.RESET}"
                    print(f"{Colors.BRIGHT_GREEN}✓ Result:{Colors.RESET} {result_text}")
                else:
                    print(f"{Colors.BRIGHT_RED}✗ Error:{Colors.RESET} {Colors.RED}{result.error}{Colors.RESET}")

                tool_msg = Message(
                    role="tool",
                    content=result.content if result.success else f"Error: {result.error}",
                    tool_call_id=tool_call_id,
                    name=function_name,
                )
                self.messages.append(tool_msg)

                if self._check_cancelled():
                    self._cleanup_incomplete_messages()
                    cancel_msg = "Task cancelled by user."
                    print(f"\n{Colors.BRIGHT_YELLOW}⚠️  {cancel_msg}{Colors.RESET}")
                    return cancel_msg

            step_elapsed = perf_counter() - step_start_time
            total_elapsed = perf_counter() - run_start_time
            print(f"\n{Colors.DIM}⏱️  Step {step + 1} completed in {step_elapsed:.2f}s (total: {total_elapsed:.2f}s){Colors.RESET}")

            step += 1

        error_msg = f"Task couldn't be completed after {self.max_steps} steps."
        print(f"\n{Colors.BRIGHT_YELLOW}⚠️  {error_msg}{Colors.RESET}")
        return error_msg

    async def run_stream(
        self,
        user_message: str,
        cancel_event: Optional[asyncio.Event] = None,
        enable_deep_think: bool = False,
    ) -> AsyncGenerator[dict, None]:
        """Execute agent loop with structured streaming output.

        Args:
            user_message: The user's message
            cancel_event: Optional event to signal cancellation
            enable_deep_think: Whether to enable deep thinking mode

        Yields:
            dict: Event dictionaries with types:
                - thinking: thinking content chunks
                - content: assistant response content chunks
                - tool_call: tool call detected
                - tool_result: tool execution result
                - done: final completion with full response
        """
        if cancel_event is not None:
            self.cancel_event = cancel_event

        self.logger.start_new_run()
        
        if enable_deep_think:
            print(f"{Colors.BRIGHT_MAGENTA}🔮 Deep Think Mode Enabled{Colors.RESET}")
            print(f"{Colors.DIM}📝 Log file: {self.logger.get_log_file_path()}{Colors.RESET}")
        else:
            print(f"{Colors.DIM}📝 Log file: {self.logger.get_log_file_path()}{Colors.RESET}")

        self.add_user_message(user_message)

        step = 0
        run_start_time = perf_counter()

        while step < self.max_steps:
            if self._check_cancelled():
                self._cleanup_incomplete_messages()
                yield {"type": "error", "content": "Task cancelled by user."}
                return

            step_start_time = perf_counter()
            await self._summarize_messages()

            BOX_WIDTH = 58
            step_text = f"{Colors.BOLD}{Colors.BRIGHT_CYAN}💭 Step {step + 1}/{self.max_steps}{Colors.RESET}"
            step_display_width = calculate_display_width(step_text)
            padding = max(0, BOX_WIDTH - 1 - step_display_width)

            print(f"\n{Colors.DIM}╭{'─' * BOX_WIDTH}╮{Colors.RESET}")
            print(f"{Colors.DIM}│{Colors.RESET} {step_text}{' ' * padding}{Colors.DIM}│{Colors.RESET}")
            print(f"{Colors.DIM}╰{'─' * BOX_WIDTH}╯{Colors.RESET}")

            tool_list = list(self.tools.values())

            self.logger.log_request(messages=self.messages, tools=tool_list)

            full_content = ""
            thinking_content = None
            thinking_started = False
            assistant_started = False

            try:
                async for chunk in self.llm.stream_generate(messages=self.messages, tools=tool_list):
                    print(f"收到 chunk: {chunk}")
                    if "[THINKING]" in chunk and "[/THINKING]" in chunk:
                        thinking_text = chunk.replace("[THINKING]", "").replace("[/THINKING]", "")
                        if not thinking_started:
                            thinking_started = True
                            print(f"\n{Colors.BOLD}{Colors.MAGENTA}🧠 Thinking:{Colors.RESET}")
                            print(f"{Colors.DIM}", end="", flush=True)
                            yield {"type": "thinking_start", "content": ""}
                        print(thinking_text, end="", flush=True)
                        thinking_content = (thinking_content or "") + thinking_text
                        yield {"type": "thinking", "content": thinking_text}
                    else:
                        if chunk and not assistant_started:
                            assistant_started = True
                            print(f"\n{Colors.BOLD}{Colors.BRIGHT_BLUE}🤖 Assistant:{Colors.RESET}")
                            print(f"{Colors.CYAN}", end="", flush=True)
                            yield {"type": "assistant_start", "content": ""}
                        if chunk:
                            print(chunk, end="", flush=True)
                            full_content += chunk
                            yield {"type": "content", "content": chunk}

                print(f"{Colors.RESET}")

                if thinking_content:
                    print(f"\n{Colors.DIM}{thinking_content}{Colors.RESET}")

                response = await self.llm.generate(messages=self.messages, tools=tool_list)

                if response.usage:
                    self.api_total_tokens = response.usage.total_tokens

                self.logger.log_response(
                    content=response.content,
                    thinking=response.thinking,
                    tool_calls=response.tool_calls,
                    finish_reason=response.finish_reason,
                )

                assistant_msg = Message(
                    role="assistant",
                    content=response.content,
                    thinking=response.thinking,
                    tool_calls=response.tool_calls,
                )
                self.messages.append(assistant_msg)

                if not response.tool_calls:
                    step_elapsed = perf_counter() - step_start_time
                    total_elapsed = perf_counter() - run_start_time
                    print(f"\n{Colors.DIM}⏱️  Step {step + 1} completed in {step_elapsed:.2f}s (total: {total_elapsed:.2f}s){Colors.RESET}")
                    yield {
                        "type": "done",
                        "content": response.content,
                        "thinking": response.thinking,
                        "steps": step + 1,
                        "tool_calls": 0,
                    }
                    return

                if self._check_cancelled():
                    self._cleanup_incomplete_messages()
                    yield {"type": "error", "content": "Task cancelled by user."}
                    return

                for tool_call in response.tool_calls:
                    tool_call_id = tool_call.id
                    function_name = tool_call.function.name
                    arguments = tool_call.function.arguments

                    print(f"\n{Colors.BRIGHT_YELLOW}🔧 Tool Call:{Colors.RESET} {Colors.BOLD}{Colors.CYAN}{function_name}{Colors.RESET}")

                    print(f"{Colors.DIM}   Arguments:{Colors.RESET}")
                    truncated_args = {}
                    for key, value in arguments.items():
                        value_str = str(value)
                        if len(value_str) > 200:
                            truncated_args[key] = value_str[:200] + "..."
                        else:
                            truncated_args[key] = value
                    args_json = json.dumps(truncated_args, indent=2, ensure_ascii=False)
                    for line in args_json.split("\n"):
                        print(f"   {Colors.DIM}{line}{Colors.RESET}")

                    yield {
                        "type": "tool_call",
                        "tool_name": function_name,
                        "arguments": arguments,
                        "tool_call_id": tool_call_id,
                    }

                    if function_name not in self.tools:
                        result = ToolResult(
                            success=False,
                            content="",
                            error=f"Unknown tool: {function_name}",
                        )
                    else:
                        try:
                            tool = self.tools[function_name]
                            result = await tool.execute(**arguments)
                        except Exception as e:
                            import traceback

                            error_detail = f"{type(e).__name__}: {str(e)}"
                            error_trace = traceback.format_exc()
                            result = ToolResult(
                                success=False,
                                content="",
                                error=f"Tool execution failed: {error_detail}\n\nTraceback:\n{error_trace}",
                            )

                    self.logger.log_tool_result(
                        tool_name=function_name,
                        arguments=arguments,
                        result_success=result.success,
                        result_content=result.content if result.success else None,
                        result_error=result.error if not result.success else None,
                    )

                    yield {
                        "type": "tool_result",
                        "tool_name": function_name,
                        "success": result.success,
                        "result": result.content if result.success else result.error,
                        "tool_call_id": tool_call_id,
                    }

                    if result.success:
                        result_text = result.content
                        if len(result_text) > 300:
                            result_text = result_text[:300] + f"{Colors.DIM}...{Colors.RESET}"
                        print(f"{Colors.BRIGHT_GREEN}✓ Result:{Colors.RESET} {result_text}")
                    else:
                        print(f"{Colors.BRIGHT_RED}✗ Error:{Colors.RESET} {Colors.RED}{result.error}{Colors.RESET}")

                    tool_msg = Message(
                        role="tool",
                        content=result.content if result.success else f"Error: {result.error}",
                        tool_call_id=tool_call_id,
                        name=function_name,
                    )
                    self.messages.append(tool_msg)

                    if self._check_cancelled():
                        self._cleanup_incomplete_messages()
                        yield {"type": "error", "content": "Task cancelled by user."}
                        return

                step_elapsed = perf_counter() - step_start_time
                total_elapsed = perf_counter() - run_start_time
                print(f"\n{Colors.DIM}⏱️  Step {step + 1} completed in {step_elapsed:.2f}s (total: {total_elapsed:.2f}s){Colors.RESET}")

                step += 1

            except Exception as e:
                from .retry import RetryExhaustedError

                if isinstance(e, RetryExhaustedError):
                    error_msg = f"LLM call failed after {e.attempts} retries\nLast error: {str(e.last_exception)}"
                    print(f"\n{Colors.BRIGHT_RED}❌ Retry failed:{Colors.RESET} {error_msg}")
                else:
                    error_msg = f"LLM call failed: {str(e)}"
                    print(f"\n{Colors.BRIGHT_RED}❌ Error:{Colors.RESET} {error_msg}")
                yield {"type": "error", "content": error_msg}
                return

        error_msg = f"Task couldn't be completed after {self.max_steps} steps."
        print(f"\n{Colors.BRIGHT_YELLOW}⚠️  {error_msg}{Colors.RESET}")
        yield {"type": "error", "content": error_msg}

    def get_history(self) -> list[Message]:
        """Get message history."""
        return self.messages.copy()
