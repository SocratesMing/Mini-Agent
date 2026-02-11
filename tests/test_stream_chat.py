#!/usr/bin/env python3
"""
流式聊天接口测试脚本
测试 FastAPI 应用的 /api/chat/stream 接口

使用方法:
    python test_stream_chat.py [--url URL] [--message MESSAGE]

参数:
    --url: API 地址 (默认: http://localhost:8000)
    --message: 发送的消息 (默认: "你好，请做个自我介绍")
"""

import argparse
import json
import time
import sys
import requests
from typing import Iterator


class StreamingChatTester:
    """流式聊天接口测试器"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()

    def check_health(self) -> bool:
        """检查服务健康状态"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                print("✓ 服务健康检查通过")
                return True
            print(f"✗ 健康检查失败: {response.status_code}")
            return False
        except requests.exceptions.ConnectionError:
            print(f"✗ 无法连接到服务: {self.base_url}")
            return False
        except Exception as e:
            print(f"✗ 健康检查异常: {e}")
            return False

    def test_stream_chat(self, message: str, session_id: str = None, message_id: str = None) -> dict:
        """
        测试流式聊天接口

        Args:
            message: 发送的消息
            session_id: 会话ID（可选）
            message_id: 消息ID（可选，用于标识单条消息）

        Returns:
            测试结果字典
        """
        print(f"\n{'='*60}")
        print("测试流式聊天接口")
        print(f"{'='*60}")
        print(f"消息: {message}")
        print(f"会话ID: {session_id or '新会话'}")
        print(f"消息ID: {message_id or '新消息'}")
        print(f"{'='*60}\n")

        # 构建请求
        url = f"{self.base_url}/api/chat/stream"
        payload = {"message": message}
        if session_id:
            payload["session_id"] = session_id
        if message_id:
            payload["message_id"] = message_id

        start_time = time.time()
        total_chars = 0
        event_count = 0
        thinking_events = 0
        content_events = 0
        done_events = 0
        errors = []
        response_message_id = None
        last_content = ""

        try:
            print("接收流式响应:\n")

            response = self.session.post(
                url,
                json=payload,
                stream=True,
                timeout=60
            )

            if response.status_code != 200:
                print(f"✗ 请求失败: HTTP {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"错误信息: {json.dumps(error_detail, ensure_ascii=False)}")
                except:
                    print(f"响应内容: {response.text}")
                return {"success": False, "error": f"HTTP {response.status_code}"}

            # 解析 SSE 流
            response_session_id = None
            response_message_id = None
            last_content = ""
            accumulated_content = ""
            accumulated_thinking = ""
            
            for line in response.iter_lines(decode_unicode=True):
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event_count += 1

                        event_type = data.get("type", "unknown")
                        content = data.get("content", "")
                        is_final = data.get("done", False)

                        if event_type == "thinking":
                            thinking_events += 1
                            accumulated_thinking += content
                            print(content, end="", flush=True)
                        elif event_type == "content":
                            content_events += 1
                            total_chars += len(content)
                            accumulated_content += content
                            print(content, end="", flush=True)
                        elif event_type == "assistant_start":
                            print("\n🤖 AI 响应中...")
                        elif event_type == "tool_call":
                            tool_name = data.get("tool_name", "")
                            print(f"\n🔧 调用工具: {tool_name}")
                        elif event_type == "tool_result":
                            tool_name = data.get("tool_name", "")
                            success = data.get("success", False)
                            print(f"  {'✓' if success else '✗'} {tool_name}")
                        elif event_type == "done":
                            done_events += 1
                            print("\n✅ 流式响应完成")

                        # 提取会话ID
                        if "session_id" in data and response_session_id is None:
                            response_session_id = data["session_id"]

                        # 提取消息ID
                        if "message_id" in data:
                            response_message_id = data["message_id"]

                        # 显示完成信号（只显示一次）
                        if event_type == "done":
                            stats = data.get("stats", {})
                            thinking_from_done = data.get("thinking", "")
                            if thinking_from_done:
                                accumulated_thinking = thinking_from_done
                            print(f"\n{'='*60}")
                            print("📝 完整响应内容")
                            print(f"{'='*60}")
                            print(accumulated_content)
                            print(f"{'='*60}\n")
                            if accumulated_thinking:
                                print(f"\n🧠 思考内容:")
                                print(f"{'='*60}")
                                print(accumulated_thinking)
                                print(f"{'='*60}\n")
                            print("统计信息:")
                            print(f"  - 思考事件数: {thinking_events}")
                            print(f"  - 内容事件数: {content_events}")
                            print(f"  - 总字符数: {total_chars}")
                            if stats:
                                print(f"  - 步骤数: {stats.get('steps', 'N/A')}")
                                print(f"  - 工具调用数: {stats.get('tool_calls', 'N/A')}")

                    except json.JSONDecodeError as e:
                        errors.append(f"JSON解析错误: {e}")
                        print(f"⚠ 解析错误: {e}")
                        continue

            elapsed_time = time.time() - start_time

            # 输出结果
            print(f"\n{'='*60}")
            print("测试结果汇总")
            print(f"{'='*60}")
            print(f"✓ 成功接收到流式响应")
            print(f"  - 响应时间: {elapsed_time:.2f}秒")
            print(f"  - 事件总数: {event_count}")
            print(f"  - 思考事件: {thinking_events}")
            print(f"  - 内容事件: {content_events}")
            print(f"  - 完成事件: {done_events}")
            print(f"  - 总字符数: {total_chars}")
            if response_session_id:
                print(f"  - 会话ID: {response_session_id}")
            if response_message_id:
                print(f"  - 消息ID: {response_message_id}")

            if errors:
                print(f"\n警告:")
                for error in errors:
                    print(f"  - {error}")

            return {
                "success": True,
                "session_id": response_session_id,
                "message_id": response_message_id,
                "elapsed_time": elapsed_time,
                "event_count": event_count,
                "thinking_events": thinking_events,
                "content_events": content_events,
                "done_events": done_events,
                "total_chars": total_chars,
                "errors": errors
            }

        except requests.exceptions.Timeout:
            print("✗ 请求超时")
            return {"success": False, "error": "Timeout"}
        except requests.exceptions.ConnectionError as e:
            print(f"✗ 连接错误: {e}")
            return {"success": False, "error": f"Connection error: {e}"}
        except Exception as e:
            print(f"✗ 异常: {e}")
            return {"success": False, "error": str(e)}

    def test_stream_with_session(self, message: str, session_id: str) -> dict:
        """测试使用已有会话进行流式聊天"""
        print(f"\n{'='*60}")
        print(f"测试继续会话: {session_id}")
        print(f"{'='*60}")

        return self.test_stream_chat(message, session_id)

    def run_interactive_chat(self):
        """交互式聊天模式"""
        print("\n" + "="*60)
        print("交互式流式聊天模式")
        print("="*60)
        print("提示:")
        print("  - 输入消息并按回车发送")
        print("  - 输入 'quit' 或 'exit' 退出")
        print("  - 输入 'new' 创建新会话")
        print("="*60)

        current_session_id = None

        while True:
            try:
                message = input("你: ").strip()

                if message.lower() in ['quit', 'exit', 'q']:
                    print("再见！")
                    break

                if message.lower() == 'new':
                    current_session_id = None
                    print("已创建新会话")
                    continue

                if not message:
                    continue

                result = self.test_stream_chat(message, current_session_id)

                if result["success"] and result.get("session_id"):
                    current_session_id = result["session_id"]

            except KeyboardInterrupt:
                print("\n\n检测到中断，退出...")
                break
            except Exception as e:
                print(f"错误: {e}")

    def run_preset_tests(self):
        """运行预设测试用例"""
        test_cases = [
            {
                "name": "基础问候",
                "message": "你好，请做个自我介绍"
            },
            {
                "name": "数学计算",
                "message": "请计算 123 + 456 = ?"
            },
            {
                "name": "文件操作测试",
                "message": "请列出当前目录的文件"
            }
        ]

        print("\n" + "="*60)
        print("运行预设测试用例")
        print("="*60)

        current_session_id = None
        results = []

        for i, test in enumerate(test_cases, 1):
            print(f"\n\n[{i}/{len(test_cases)}] {test['name']}")
            print("-"*60)

            result = self.test_stream_chat(test["message"], current_session_id)
            results.append(result)

            if result["success"] and result.get("session_id"):
                current_session_id = result["session_id"]

            # 每个测试之间暂停一下
            if i < len(test_cases):
                time.sleep(1)

        # 输出汇总
        print("\n\n" + "="*60)
        print("测试结果汇总")
        print("="*60)

        passed = sum(1 for r in results if r["success"])
        failed = len(results) - passed

        print(f"总测试数: {len(results)}")
        print(f"通过: {passed} ✓")
        print(f"失败: {failed} ✗")

        for i, result in enumerate(results, 1):
            status = "✓" if result["success"] else "✗"
            message = test_cases[i-1]["name"]
            elapsed = f"{result.get('elapsed_time', 0):.2f}s" if result["success"] else "N/A"
            print(f"  {status} [{i}] {message} ({elapsed})")

        return failed == 0


def main():
    parser = argparse.ArgumentParser(
        description="流式聊天接口测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 检查服务健康
    python test_stream_chat.py --check

    # 发送测试消息
    python test_stream_chat.py --message "你好"

    # 运行预设测试
    python test_stream_chat.py --preset

    # 交互式聊天
    python test_stream_chat.py --interactive
        """
    )

    parser.add_argument(
        "--url", "-u",
        default="http://localhost:8000",
        help="API 服务器地址 (默认: http://localhost:8000)"
    )

    parser.add_argument(
        "--message", "-m",
        default=None,
        help="要发送的消息"
    )

    parser.add_argument(
        "--session", "-s",
        default=None,
        help="会话ID（可选）"
    )

    parser.add_argument(
        "--check", "-c",
        action="store_true",
        help="仅检查服务健康状态"
    )

    parser.add_argument(
        "--preset", "-p",
        action="store_true",
        help="运行预设测试用例"
    )

    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="交互式聊天模式"
    )

    args = parser.parse_args()

    # 初始化测试器
    tester = StreamingChatTester(args.url)

    # 健康检查
    if not args.check and not args.interactive:
        if not tester.check_health():
            print("\n请确保 FastAPI 服务已启动:")
            print("  python api_server.py")
            sys.exit(1)

    # 交互式模式
    if args.interactive:
        tester.run_interactive_chat()
        return

    # 预设测试
    if args.preset:
        tester.run_preset_tests()
        return

    # 单条消息测试
    if args.message:
        result = tester.test_stream_chat(args.message, args.session)
        sys.exit(0 if result["success"] else 1)

    # 仅健康检查
    if args.check:
        tester.check_health()
        return

    # 默认显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
