"""Core Agent implementation."""

import asyncio
from datetime import datetime
import json
import logging
from pathlib import Path
import time
from time import perf_counter
from typing import AsyncGenerator, Optional

import tiktoken

from .llm import LLMClient
from .schema import FunctionCall, Message, ToolCall
from .tools.base import Tool, ToolResult
from .utils import calculate_display_width
from .logger import AgentLogger

logger = logging.getLogger("mini_agent.agent")


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
        session_id: str = None,
    ):
        self.llm = llm_client
        self.tools = {tool.name: tool for tool in tools}
        self.max_steps = max_steps
        self.token_limit = token_limit
        self.workspace_dir = Path(workspace_dir)
        self.cancel_event: Optional[asyncio.Event] = None
        self.session_id = session_id or "-----"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        if "Current Workspace" not in system_prompt:
            workspace_info = f"\n\n## Current Workspace\nYou are currently working in: `{self.workspace_dir.absolute()}`\nAll relative paths will be resolved relative to this directory."
            system_prompt = system_prompt + workspace_info

        self.system_prompt = system_prompt

        self.messages: list[Message] = [Message(role="system", content=system_prompt)]
        self.logger = AgentLogger()

        self.api_total_tokens: int = 0
        self._skip_next_token_check: bool = False
        self.run_logger = logging.getLogger("mini_agent.agent")

    def _log_message(self, log_type: str, data: dict, level: str = "info"):
        """Log message using the main logger
        
        Args:
            log_type: Type of log (REQUEST, RESPONSE, TOOL_RESULT)
            data: Log data to be JSON serialized
            level: Log level (info, debug, warning, error)
        """
        content = f"{log_type}:\n\n"
        content += json.dumps(data, indent=2, ensure_ascii=False)
        
        log_entry = f"\n" + "-" * 80 + f"\n[{log_type}]\n{content}\n"
        
        if level == "debug":
            self.run_logger.debug(log_entry)
        elif level == "warning":
            self.run_logger.warning(log_entry)
        elif level == "error":
            self.run_logger.error(log_entry)
        else:
            self.run_logger.info(log_entry)

    def _log_llm_request(self, messages: list[Message], tools: list[Tool]):
        """Log LLM request
        
        Args:
            messages: Message list
            tools: Tool list
        """
        request_data = {
            "messages": [],
            "tools": [],
        }

        for msg in messages:
            msg_dict = {
                "role": msg.role,
                "content": msg.content,
            }
            if msg.thinking:
                msg_dict["thinking"] = msg.thinking
            if msg.tool_calls:
                msg_dict["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id
            if msg.name:
                msg_dict["name"] = msg.name

            request_data["messages"].append(msg_dict)

        if tools:
            request_data["tools"] = [tool.name for tool in tools]

        self._log_message("REQUEST", request_data, "debug")

    def _log_llm_response(self, content: str, thinking: Optional[str] = None, 
                         tool_calls: Optional[list[ToolCall]] = None, 
                         finish_reason: Optional[str] = None):
        """Log LLM response
        
        Args:
            content: Response content
            thinking: Thinking content
            tool_calls: Tool call list
            finish_reason: Finish reason
        """
        response_data = {
            "content": content,
        }

        if thinking:
            response_data["thinking"] = thinking

        if tool_calls:
            response_data["tool_calls"] = [tc.model_dump() for tc in tool_calls]

        if finish_reason:
            response_data["finish_reason"] = finish_reason

        self._log_message("RESPONSE", response_data)

    def _log_tool_result(self, tool_name: str, arguments: dict, 
                        success: bool, content: Optional[str] = None, 
                        error: Optional[str] = None):
        """Log tool execution result
        
        Args:
            tool_name: Tool name
            arguments: Tool arguments
            success: Whether successful
            content: Result content
            error: Error message
        """
        tool_result_data = {
            "tool_name": tool_name,
            "arguments": arguments,
            "success": success,
        }

        if success:
            tool_result_data["result"] = content
        else:
            tool_result_data["error"] = error

        self._log_message("TOOL_RESULT", tool_result_data)

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
    async def run(self, cancel_event: Optional[asyncio.Event] = None) -> str:
        """Execute agent loop until task is complete or max steps reached.

        Args:
            cancel_event: Optional asyncio.Event that can be set to cancel execution.
                          When set, the agent will stop at the next safe checkpoint
                          (after completing the current step to keep messages consistent).

        Returns:
            The final response content, or error message (including cancellation message).
        """
        # Set cancellation event (can also be set via self.cancel_event before calling run())
        if cancel_event is not None:
            self.cancel_event = cancel_event

        # Start new run, initialize log file
        self.logger.start_new_run()
        print(f"{Colors.DIM}📝 Log file: {self.logger.get_log_file_path()}{Colors.RESET}")

        step = 0
        run_start_time = perf_counter()

        while step < self.max_steps:
            # Check for cancellation at start of each step
            if self._check_cancelled():
                self._cleanup_incomplete_messages()
                cancel_msg = "Task cancelled by user."
                print(f"\n{Colors.BRIGHT_YELLOW}⚠️  {cancel_msg}{Colors.RESET}")
                return cancel_msg

            step_start_time = perf_counter()
            # Check and summarize message history to prevent context overflow
            await self._summarize_messages()

            # Step header with proper width calculation
            BOX_WIDTH = 58
            step_text = f"{Colors.BOLD}{Colors.BRIGHT_CYAN}💭 Step {step + 1}/{self.max_steps}{Colors.RESET}"
            step_display_width = calculate_display_width(step_text)
            padding = max(0, BOX_WIDTH - 1 - step_display_width)  # -1 for leading space

            print(f"\n{Colors.DIM}╭{'─' * BOX_WIDTH}╮{Colors.RESET}")
            print(f"{Colors.DIM}│{Colors.RESET} {step_text}{' ' * padding}{Colors.DIM}│{Colors.RESET}")
            print(f"{Colors.DIM}╰{'─' * BOX_WIDTH}╯{Colors.RESET}")

            # Get tool list for LLM call
            tool_list = list(self.tools.values())

            # Log LLM request and call LLM with Tool objects directly

            self.logger.log_request(messages=self.messages, tools=tool_list)

            try:
                response = await self.llm.generate(messages=self.messages, tools=tool_list)
            except Exception as e:
                # Check if it's a retry exhausted error
                from .retry import RetryExhaustedError

                if isinstance(e, RetryExhaustedError):
                    error_msg = f"LLM call failed after {e.attempts} retries\nLast error: {str(e.last_exception)}"
                    print(f"\n{Colors.BRIGHT_RED}❌ Retry failed:{Colors.RESET} {error_msg}")
                else:
                    error_msg = f"LLM call failed: {str(e)}"
                    print(f"\n{Colors.BRIGHT_RED}❌ Error:{Colors.RESET} {error_msg}")
                return error_msg

            # Accumulate API reported token usage
            if response.usage:
                self.api_total_tokens = response.usage.total_tokens

            # Log LLM response
            self.logger.log_response(
                content=response.content,
                thinking=response.thinking,
                tool_calls=response.tool_calls,
                finish_reason=response.finish_reason,
            )

            # Add assistant message
            assistant_msg = Message(
                role="assistant",
                content=response.content,
                thinking=response.thinking,
                tool_calls=response.tool_calls,
            )
            self.messages.append(assistant_msg)

            # Print thinking if present
            if response.thinking:
                print(f"\n{Colors.BOLD}{Colors.MAGENTA}🧠 Thinking:{Colors.RESET}")
                print(f"{Colors.DIM}{response.thinking}{Colors.RESET}")

            # Print assistant response
            if response.content:
                print(f"\n{Colors.BOLD}{Colors.BRIGHT_BLUE}🤖 Assistant:{Colors.RESET}")
                print(f"{response.content}")

            # Check if task is complete (no tool calls)
            if not response.tool_calls:
                step_elapsed = perf_counter() - step_start_time
                total_elapsed = perf_counter() - run_start_time
                print(f"\n{Colors.DIM}⏱️  Step {step + 1} completed in {step_elapsed:.2f}s (total: {total_elapsed:.2f}s){Colors.RESET}")
                return response.content

            # Check for cancellation before executing tools
            if self._check_cancelled():
                self._cleanup_incomplete_messages()
                cancel_msg = "Task cancelled by user."
                print(f"\n{Colors.BRIGHT_YELLOW}⚠️  {cancel_msg}{Colors.RESET}")
                return cancel_msg

            # Execute tool calls
            for tool_call in response.tool_calls:
                tool_call_id = tool_call.id
                function_name = tool_call.function.name
                arguments = tool_call.function.arguments

                # Tool call header
                print(f"\n{Colors.BRIGHT_YELLOW}🔧 Tool Call:{Colors.RESET} {Colors.BOLD}{Colors.CYAN}{function_name}{Colors.RESET}")

                # Arguments (formatted display)
                print(f"{Colors.DIM}   Arguments:{Colors.RESET}")
                # Truncate each argument value to avoid overly long output
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

                # Execute tool
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
                        # Catch all exceptions during tool execution, convert to failed ToolResult
                        import traceback

                        error_detail = f"{type(e).__name__}: {str(e)}"
                        error_trace = traceback.format_exc()
                        result = ToolResult(
                            success=False,
                            content="",
                            error=f"Tool execution failed: {error_detail}\n\nTraceback:\n{error_trace}",
                        )

                # Log tool execution result
                self.logger.log_tool_result(
                    tool_name=function_name,
                    arguments=arguments,
                    result_success=result.success,
                    result_content=result.content if result.success else None,
                    result_error=result.error if not result.success else None,
                )

                # Print result
                if result.success:
                    result_text = result.content
                    if len(result_text) > 300:
                        result_text = result_text[:300] + f"{Colors.DIM}...{Colors.RESET}"
                    print(f"{Colors.BRIGHT_GREEN}✓ Result:{Colors.RESET} {result_text}")
                else:
                    print(f"{Colors.BRIGHT_RED}✗ Error:{Colors.RESET} {Colors.RED}{result.error}{Colors.RESET}")

                # Add tool result message
                tool_msg = Message(
                    role="tool",
                    content=result.content if result.success else f"Error: {result.error}",
                    tool_call_id=tool_call_id,
                    name=function_name,
                )
                self.messages.append(tool_msg)

                # Check for cancellation after each tool execution
                if self._check_cancelled():
                    self._cleanup_incomplete_messages()
                    cancel_msg = "Task cancelled by user."
                    print(f"\n{Colors.BRIGHT_YELLOW}⚠️  {cancel_msg}{Colors.RESET}")
                    return cancel_msg

            step_elapsed = perf_counter() - step_start_time
            total_elapsed = perf_counter() - run_start_time
            print(f"\n{Colors.DIM}⏱️  Step {step + 1} completed in {step_elapsed:.2f}s (total: {total_elapsed:.2f}s){Colors.RESET}")

            step += 1

        # Max steps reached
        error_msg = f"Task couldn't be completed after {self.max_steps} steps."
        print(f"\n{Colors.BRIGHT_YELLOW}⚠️  {error_msg}{Colors.RESET}")
        return error_msg


    async def run_stream(
        self,
        user_message: str,
        cancel_event: Optional[asyncio.Event] = None,
        enable_deep_think: bool = False,
    ) -> AsyncGenerator[dict, None]:
        """Execute agent loop with structured streaming output."""
        start_time = time.time()
        sid = self.session_id[-5:] if self.session_id else "-----"
        
        logger.info(f"[{sid}] 开始 | message: {user_message[:50]}{'...' if len(user_message) > 50 else ''} | deep_think: {enable_deep_think}")
        
        if cancel_event is not None:
            self.cancel_event = cancel_event

        self.run_logger = logging.getLogger("mini_agent.agent")

        if enable_deep_think:
            print(f"{Colors.BRIGHT_MAGENTA}🔮 Deep Think Mode Enabled{Colors.RESET}")
        else:
            print(f"{Colors.DIM}📝 Using main application log{Colors.RESET}")

        self.add_user_message(user_message)

        step = 0
        run_start_time = perf_counter()

        while step < self.max_steps:
            if self._check_cancelled():
                self._cleanup_incomplete_messages()
                logger.error(f"[{sid}] 任务被用户取消")
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

            logger.info(f"[{sid}] 💭 Step {step + 1}/{self.max_steps} 开始")

            tool_list = list(self.tools.values())

            self._log_llm_request(self.messages, tool_list)

            thinking_content = None
            assistant_started = False
            full_response = ""
            thinking_content = ""
            thinking_duration_value = None

            llm_start_time = time.time()
            thinking_start_time = None
            
            try:
                chunk_count = 0
                collected_tool_calls = []
                
                async for chunk in self.llm.stream_generate(messages=self.messages, tools=tool_list, enable_deep_think=enable_deep_think):
                    chunk_count += 1
                    chunk_type = chunk.get("type", "")
                    
                    if chunk_type == "thinking_start":
                        thinking_started = True
                        thinking_start_time = time.time()
                        yield {"type": "thinking_start", "content": ""}
                    
                    elif chunk_type == "thinking":
                        thinking_content = (thinking_content or "") + chunk.get("content", "")
                        yield {"type": "thinking", "content": chunk.get("content", "")}
                    
                    elif chunk_type == "thinking_end":
                        thinking_duration_value = chunk.get("duration")
                        if thinking_duration_value is not None:
                            yield {"type": "thinking_end", "duration": thinking_duration_value}
                    
                    elif chunk_type == "content":
                        content = chunk.get("content", "")
                        if content and not assistant_started:
                            assistant_started = True
                            if thinking_start_time and not thinking_duration_value:
                                thinking_duration_value = round(time.time() - thinking_start_time, 1)
                                yield {"type": "thinking_end", "duration": thinking_duration_value}
                            yield {"type": "assistant_start", "content": ""}
                        if content:
                            full_response += content
                            yield {"type": "content", "content": content}
                    
                    elif chunk_type == "done":
                        collected_tool_calls = chunk.get("tool_calls", [])

                if thinking_content and thinking_duration_value is None and thinking_start_time:
                    thinking_duration_value = round(time.time() - thinking_start_time, 1)
                    yield {"type": "thinking_end", "duration": thinking_duration_value}

                llm_elapsed = time.time() - llm_start_time
                logger.info(f"[{sid}] LLM完成 | chunks={chunk_count} | content={len(full_response)} | thinking={len(thinking_content) if thinking_content else 0} | thinking_duration={thinking_duration_value} | tools={len(collected_tool_calls)} | 耗时: {llm_elapsed:.2f}s")
                
                if collected_tool_calls:
                    for tc in collected_tool_calls:
                        if tc.get("type") == "function" and "function" in tc:
                            logger.info(f"[{sid}] 工具调用: {tc['function']['name']} | 参数: {tc['function']['arguments']}")
                        elif "name" in tc:
                            logger.info(f"[{sid}] 工具调用: {tc['name']} | 参数: {tc['arguments']}")

                tool_calls_for_msg = None
                if collected_tool_calls:
                    tool_calls_for_msg = []
                    for tc in collected_tool_calls:
                        if tc.get("type") == "function" and "function" in tc:
                            args = tc["function"]["arguments"]
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except:
                                    args = {}
                            tool_calls_for_msg.append(ToolCall(
                                id=tc["id"],
                                type="function",
                                function=FunctionCall(
                                    name=tc["function"]["name"],
                                    arguments=args,
                                ),
                            ))
                        elif "name" in tc:
                            args = tc["arguments"]
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except:
                                    args = {}
                            tool_calls_for_msg.append(ToolCall(
                                id=tc["id"],
                                type="function",
                                function=FunctionCall(
                                    name=tc["name"],
                                    arguments=args,
                                ),
                            ))

                self._log_llm_response(
                    content=full_response,
                    thinking=thinking_content or None,
                    tool_calls=tool_calls_for_msg,
                    finish_reason="stop",
                )

                assistant_msg = Message(
                    role="assistant",
                    content=full_response,
                    thinking=thinking_content or None,
                    tool_calls=tool_calls_for_msg,
                )
                self.messages.append(assistant_msg)

                if not collected_tool_calls:
                    step_elapsed = perf_counter() - step_start_time
                    total_elapsed = perf_counter() - run_start_time
                    print(f"\n{Colors.DIM}⏱️  Step {step + 1} completed in {step_elapsed:.2f}s (total: {total_elapsed:.2f}s){Colors.RESET}")
                    yield {
                        "type": "done",
                        "content": full_response,
                        "thinking": thinking_content,
                        "thinking_duration": thinking_duration_value,
                        "steps": step + 1,
                        "tool_calls": 0,
                    }
                    logger.info(f"[{sid}] 完成 | steps={step + 1} | 耗时: {time.time() - start_time:.2f}s")
                    return

                if self._check_cancelled():
                    self._cleanup_incomplete_messages()
                    logger.error(f"[{sid}] 任务被用户取消")
                    yield {"type": "error", "content": "Task cancelled by user."}
                    return
                
                for tool_call in collected_tool_calls:
                    tool_call_id = tool_call["id"]
                    if tool_call.get("type") == "function" and "function" in tool_call:
                        function_name = tool_call["function"]["name"]
                        arguments = tool_call["function"]["arguments"]
                    else:
                        function_name = tool_call["name"]
                        arguments = tool_call["arguments"]
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except:
                            arguments = {}

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
                        logger.error(f"[{sid}] 未知工具: {function_name}")
                        tool_start_time = time.time()
                        result = ToolResult(
                            success=False,
                            content="",
                            error=f"Unknown tool: {function_name}",
                        )
                    else:
                        try:
                            tool = self.tools[function_name]
                            tool_start_time = time.time()
                            result = await tool.execute(**arguments)
                            logger.info(f"[{sid}] 工具 {function_name} | success={result.success} | 耗时: {time.time() - tool_start_time:.2f}s")
                        except Exception as e:
                            import traceback
                            logger.error(f"[{sid}] 工具执行异常: {function_name} | error={str(e)}")
                            error_detail = f"{type(e).__name__}: {str(e)}"
                            error_trace = traceback.format_exc()
                            result = ToolResult(
                                success=False,
                                content="",
                                error=f"Tool execution failed: {error_detail}\n\nTraceback:\n{error_trace}",
                            )

                    self._log_tool_result(
                        tool_name=function_name,
                        arguments=arguments,
                        success=result.success,
                        content=result.content if result.success else None,
                        error=result.error if not result.success else None,
                    )

                    yield {
                        "type": "tool_result",
                        "tool_name": function_name,
                        "success": result.success,
                        "result": result.content if result.success else result.error,
                        "tool_call_id": tool_call_id,
                        "duration": round(time.time() - tool_start_time, 1),
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
                        logger.error(f"[{sid}] 任务被用户取消")
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
                logger.error(f"[{sid}] 异常: {error_msg}")
                import traceback
                logger.error(f"[{sid}] 堆栈:\n{traceback.format_exc()}")
                yield {"type": "error", "content": error_msg}
                return

        error_msg = f"Task couldn't be completed after {self.max_steps} steps."
        print(f"\n{Colors.BRIGHT_YELLOW}⚠️  {error_msg}{Colors.RESET}")
        logger.error(f"[{sid}] {error_msg}")
        yield {"type": "error", "content": error_msg}

    def get_history(self) -> list[Message]:
        """Get message history."""
        return self.messages.copy()
