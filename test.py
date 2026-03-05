import asyncio
import sys
import json
from datetime import datetime
from fastmcp import Client
from fastmcp.client.logging import LogMessage
import time
import argparse

parser = argparse.ArgumentParser(description="Shell MCP Server Tester")


parser.add_argument(
    "-t", "--transport", type=str, default="stdio", choices=["stdio", "http"]
)
args = parser.parse_args()


def on_log_message(message):
    level = getattr(message, "level", "info")
    data = getattr(message, "data", str(message))
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

    if level in ("warning", "error"):
        print(f"  ⚠ [{ts}] {data}", file=sys.stderr, flush=True)
    else:
        print(f"  │ [{ts}] {data}", file=sys.stderr, flush=True)


async def log_handler(message: LogMessage):
    print(f"Server log: {message.data}")


async def progress_handler(progress: float, total: float | None, message: str | None):
    print(f"Progress: {progress}/{total} - {message}")


async def sampling_handler(messages, params, context):
    return "Generated response"



if args.transport == "http":
    SERVER = "http://localhost:8000/mcp"
else:
    from shell_mcp_server import server

    SERVER = server.server


try:
    client = Client(
        SERVER,
        log_handler=log_handler,
        progress_handler=progress_handler,
        sampling_handler=sampling_handler,
    )
    STREAMING = True
except TypeError:
    client = Client(SERVER)
    STREAMING = False


def print_result(result):
    print("─── result ───")
    for content in result.content:
        text = content.text
        try:
            parsed = json.loads(text.replace("'", '"'))
            for k, v in parsed.items():
                print(f"  {k} → {v}")
        except (json.JSONDecodeError, AttributeError):
            print(text)
    print("──────────────")


async def call(tool: str, args: dict, expect_error: bool = False):
    """Call a tool, showing streamed output + final result."""
    print(f"\n{'═' * 60}")
    print(f"▶ {tool}({json.dumps(args, ensure_ascii=False)})")
    if STREAMING:
        print(f"  (streaming enabled)")
    print(f"{'═' * 60}")

    try:
        result = await client.call_tool(tool, args)
        print()
        if expect_error:
            print("  ⚠ Expected error but got result:")
        print_result(result)
        return result
    except Exception as e:
        if expect_error:
            print(f"  ✓ Expected error: {e}")
        else:
            print(f"  ✖ ERROR: {e}")
        return None


async def main():
    async with client:
        # ═══════════════════════════════════════════════════════════
        # 1. BASIC TOOLS
        # ═══════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("  SECTION 1: Basic Tools")
        print("=" * 60)

        await call("greet", {"name": "Test"})
        await call("bye", {"name": "Test"})

        # ═══════════════════════════════════════════════════════════
        # 2. PATH VALIDATION TESTS
        # ═══════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("  SECTION 2: Path Validation")
        print("=" * 60)

        # uv_install
        await call(
            "execute_command", {"command": "uv_install", "shell": "powershell", "cwd": "."}
        )

        # 2a. Valid path (current directory)
        await call(
            "execute_command", {"command": "pwd && ls -la", "shell": "bash", "cwd": "."}
        )

        # 2b. Valid path - /tmp
        await call(
            "execute_command",
            {
                "command": "echo 'test' > /tmp/test_file.txt && cat /tmp/test_file.txt",
                "shell": "bash",
                "cwd": "/tmp",
            },
        )
        result = await call(
            "tmux_execute",
            {
                "command": "for i in {1..5}; do echo mcp Tmux processing $i; done",
                "cwd": ".",
                "session_name": "mcp_test",
            },
        )
        # 10f. Get output again
        await call("tmux_get_output", {"session_name": "mcp_test","clear_after":True})

        # tmux_execute_command
        
        await call(
            "tmux_execute", {"command": 'echo "hello mcp" >> a.log && cat a.log', "shell": "bash", "cwd": ".","session_name": "mcp_test1"}
        )
        
        time.sleep(5)
        await call("tmux_get_output", {"session_name": "mcp_test1","clear_after":False})
        await call("tmux_list_session", {})
        # await call("tmux_kill_session", {"session_name": "mcp_test"})

        # 2c. Invalid path - outside allowed directories
        # This should fail if path is not in allowed directories
        await call(
            "execute_command",
            {"command": "ls /", "shell": "bash", "cwd": "/"},
            expect_error=True,
        )

        # 2d. Path traversal attempt
        await call(
            "execute_command",
            {"command": "ls ../", "shell": "bash", "cwd": "."},
            expect_error=True,
        )

        # ═══════════════════════════════════════════════════════════
        # 3. SHELL VALIDATION TESTS
        # ═══════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("  SECTION 3: Shell Validation")
        print("=" * 60)

        # 3a. Valid shell - bash
        await call(
            "execute_command", {"command": "echo $SHELL", "shell": "bash", "cwd": "."}
        )

        # 3b. Valid shell - wsl
        await call(
            "execute_command", {"command": "echo $SHELL", "shell": "wsl", "cwd": "."}
        )

        # 3c. Invalid shell (should be rejected by config)
        await call(
            "execute_command",
            {"command": "echo test", "shell": "invalid_shell", "cwd": "."},
            expect_error=True,
        )

        # ═══════════════════════════════════════════════════════════
        # 4. PROCESS MANAGEMENT TESTS
        # ═══════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("  SECTION 4: Process Management")
        print("=" * 60)

        # 4a. List processes (should be empty initially)
        await call("list_processes", {})

        # 4b. Start a long-running process and get its PID
        print("\n  Starting long-running process...")
        result = await call(
            "execute_command",
            {
                "command": "for i in {1..5}; do echo 'Processing $i'; sleep 1; done",
                "shell": "bash",
                "cwd": ".",
            },
        )

        # 4c. List processes (should show running process)
        await call("list_processes", {})

        # 4d. Try to terminate non-existent process
        await call("terminate_process", {"pid": 99999})

        # 4e. Terminate all processes
        await call("terminate_all_processes", {})

        # 4f. List processes again (should be empty)
        await call("list_processes", {})

        # ═══════════════════════════════════════════════════════════
        # 5. TIMEOUT TESTS
        # ═══════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("  SECTION 5: Timeout Tests")
        print("=" * 60)

        # 5a. Command that should timeout (5 second timeout default)
        print("\n  Testing timeout (command takes 10s, timeout is 5s)...")
        await call(
            "execute_command",
            {
                "command": "for i in {1..10}; do echo 'Wait $i'; sleep 1; done",
                "shell": "bash",
                "cwd": ".",
            },
        )

        # ═══════════════════════════════════════════════════════════
        # 6. ERROR HANDLING TESTS
        # ═══════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("  SECTION 6: Error Handling")
        print("=" * 60)

        # 6a. Non-existent command
        await call(
            "execute_command",
            {
                "command": "this_command_does_not_exist_12345",
                "shell": "bash",
                "cwd": ".",
            },
            expect_error=True,
        )

        # 6b. Command with syntax error
        await call(
            "execute_command",
            {
                "command": "if then else fi",  # syntax error
                "shell": "bash",
                "cwd": ".",
            },
            expect_error=True,
        )

        # 6c. Exit code handling
        await call(
            "execute_command", {"command": "exit 42", "shell": "bash", "cwd": "."}
        )

        # ═══════════════════════════════════════════════════════════
        # 7. STREAMING TESTS
        # ═══════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("  SECTION 7: Streaming Tests")
        print("=" * 60)

        # 7a. Large output (should stream)
        await call(
            "execute_command",
            {
                "command": "for i in {1..50}; do echo 'Line $i: This is a test line with some content'; done",
                "shell": "bash",
                "cwd": ".",
            },
        )

        # 7b. stderr output
        await call(
            "execute_command",
            {
                "command": "echo 'stdout' && echo 'stderr' >&2 && echo 'more stdout'",
                "shell": "bash",
                "cwd": ".",
            },
        )

        # ═══════════════════════════════════════════════════════════
        # 8. SPECIAL CHARACTERS TESTS
        # ═══════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("  SECTION 8: Special Characters")
        print("=" * 60)

        # 8a. Unicode characters
        await call(
            "execute_command",
            {
                "command": "echo 'Hello 世界 🌍 🎉' && echo '日本語テスト'",
                "shell": "bash",
                "cwd": ".",
            },
        )

        # 8b. Special shell characters
        await call(
            "execute_command",
            {
                "command": "echo 'Special: $HOME && || ;; << >> | &'",
                "shell": "bash",
                "cwd": ".",
            },
        )

        # 8c. Command with quotes
        await call(
            "execute_command",
            {
                "command": "echo \"She said: 'Hello World'\" && echo 'He said: \"Hi\"'",
                "shell": "bash",
                "cwd": ".",
            },
        )

        # ═══════════════════════════════════════════════════════════
        # 9. CONCURRENT EXECUTION TEST
        # ═══════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("  SECTION 9: Concurrent Execution")
        print("=" * 60)

        print("\n  Running 3 commands concurrently...")

        async def run_concurrent(name, delay):
            return await call(
                "execute_command",
                {
                    "command": f"echo 'Task {name} started' && sleep {delay} && echo 'Task {name} done'",
                    "shell": "bash",
                    "cwd": ".",
                },
            )

        # Run 3 commands concurrently
        results = await asyncio.gather(
            run_concurrent("A", 2),
            run_concurrent("B", 3),
            run_concurrent("C", 1),
        )

        print("\n  All concurrent tasks completed!")
        await call("terminate_all_processes", {})

        # ═══════════════════════════════════════════════════════════
        # 10. TMUX TESTS
        # Commands run in tmux persist after client disconnect
        # ═══════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("  SECTION 10: Tmux Tests")
        print("=" * 60)

        # 10a. List tmux sessions (should be empty)
        await call("tmux_list", {})

        # 10b. Start a long-running command in tmux
        print("\n  Starting long command in tmux session...")
        result = await call(
            "tmux_execute",
            {
                "command": "for i in {1..5}; do echo 'Tmux processing $i'; sleep 1; done",
                "cwd": ".",
                "session_name": "mcp_test",
            },
        )

        # 10c. List tmux sessions (should show our session)
        await call("tmux_list", {})

        # 10d. Get output from tmux session
        for i in range(5):
            await call("tmux_get_output", {"session_name": "mcp_test","clear_after":False})
            time.sleep(1)
        # 10e. Send input to tmux session
        await call(
            "tmux_send_input",
            {"session_name": "mcp_test", "input_text": "echo 'Hello from tmux'"},
        )

        # 10f. Get output again
        await call("tmux_get_output", {"session_name": "mcp_test","clear_after":False})

        # 10g. Kill tmux session
        await call("tmux_kill_session", {"session_name": "mcp_test"})

        # 10h. List tmux sessions (should be empty again)
        await call("tmux_list_session", {})

        # ═══════════════════════════════════════════════════════════
        # SUMMARY
        # ═══════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("  ALL TESTS COMPLETED!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
