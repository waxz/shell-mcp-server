"""
Shell MCP Server
==============

This module implements an MCP server that provides secure shell command execution
within specified working directories using specified shells.

Key Features:
- Safe command execution in specified directories
- Supports multiple shell types (bash, sh, cmd, powershell)
- Command timeout handling
- Cross-platform support
- Robust error handling
"""

import asyncio
import os
import sys
import argparse
from typing import Dict, Any, List, Optional, Callable, Awaitable
import toml
import mcp
import mcp.types as types
from mcp.server import Server, InitializationOptions, NotificationOptions

from fastmcp import FastMCP, Context

from . import config
from . import utils


# Parse command line arguments for directories and shells
def parse_args() -> tuple[List[str], Dict[str, str]]:
    """Parse command line arguments for directories and shells."""
    parser = argparse.ArgumentParser(description="Shell MCP Server")
    parser.add_argument(
        "-d",
        "--directories",
        nargs="+",
        help="Allowed directories for command execution",
    )
    parser.add_argument(
        "--shell",
        action="append",
        nargs=2,
        metavar=("name", "path"),
        help="Shell specification in format: name path",
    )

    parser.add_argument(
        "-t", "--transport", type=str, default="stdio", choices=["stdio", "http"]
    )
    parser.add_argument("-H", "--host", type=str, default="0.0.0.0")
    parser.add_argument("-P", "--port", type=int, default=8000)
    parser.add_argument("-p", "--path", type=str, default="/mcp")
    parser.add_argument("-c", "--config", type=str, default="config.toml")

    args = parser.parse_args()

    # Convert shell arguments to dictionary
    shells = {}
    if args.shell:
        shells = {name: path for name, path in args.shell}

    # Default to system shell if none specified
    if not shells:
        if sys.platform == "win32":
            shells = {
                "bash": "wsl.exe",
                "cmd": "cmd.exe",
                "powershell": "powershell.exe",
                "wsl": "wsl.exe",
            }
        else:
            shells = {"bash": "/bin/bash", "sh": "/bin/sh"}

    return args, shells


# Initialize server settings and create server instance - skip arg parsing for tests
if "pytest" not in sys.modules:
    args, shells = parse_args()
    config.SETTINGS = config.Settings(args, shells=shells)
else:
    args = {"directories": ["/tmp"]}
    config.SETTINGS = config.Settings(args, shells={"bash": "/bin/bash"})

# server = Server(settings.APP_NAME)
# app_http: FastMCP = FastMCP(settings.APP_NAME)
server: FastMCP = FastMCP(config.SETTINGS.APP_NAME)

# Global process registry: pid -> (process, shell_name)
# running_processes: Dict[int, tuple[asyncio.subprocess.Process, str]] = {}
from .utils import run_shell_command, running_processes


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MCP tool
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@server.tool()
async def execute_command(
    command: str,
    cwd: str,
    ctx: Context,
    shell: str = "bash",
) -> List[types.TextContent]:
    """Execute a shell command with real-time streaming output."""

    async def _on_stdout(line: str):
        await ctx.info(line)

    async def _on_stderr(line: str):
        await ctx.warning(line)

    try:
        result = await utils.run_shell_command(
            command,
            cwd,
            shell,
            on_stdout=_on_stdout,
            on_stderr=_on_stderr,
        )

        if result.get("cancelled"):
            return [types.TextContent(type="text", text="[client disconnected]")]

        parts: List[str] = []
        if result["stdout"]:
            parts.append(result["stdout"])
        if result["stderr"]:
            parts.append(f"[stderr]\n{result['stderr']}")
        parts.append(f"[exit code: {result['exit_code']}]")
        if result["timed_out"]:
            parts.append(f"[timed out after {config.SETTINGS.COMMAND_TIMEOUT}s]")

        return [types.TextContent(type="text", text="\n\n".join(parts))]

    except Exception:
        # Catch all exceptions to prevent server crash from client disconnect
        return []


# Greeting tools
@server.tool()
async def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


@server.tool()
async def bye(name: str) -> str:
    """Say goodbye to someone."""
    return f"Goodbye, {name}!"


@server.tool()
async def list_processes() -> List[types.TextContent]:
    """List all running processes started by this server."""
    if not running_processes:
        return [types.TextContent(type="text", text="No running processes")]

    lines = ["Running processes:"]
    for pid, (proc, shell) in running_processes.items():
        lines.append(f"  PID {pid}: shell={shell}")
    return [types.TextContent(type="text", text="\n".join(lines))]


@server.tool()
async def terminate_process(pid: int) -> List[types.TextContent]:
    """
    Terminate a running process by PID.

    Args:
        pid: Process ID to terminate

    Returns:
        Success or failure message
    """
    if pid not in running_processes:
        return [types.TextContent(type="text", text=f"Process {pid} not found")]

    proc, shell = running_processes[pid]
    try:
        proc.kill()
        await proc.wait()
        del running_processes[pid]
        return [types.TextContent(type="text", text=f"Process {pid} terminated")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Failed to terminate {pid}: {e}")]


@server.tool()
async def terminate_all_processes() -> List[types.TextContent]:
    """
    Terminate all running processes started by this server.

    Returns:
        Summary of terminated processes
    """
    count = 0
    for pid, (proc, shell) in list(running_processes.items()):
        try:
            proc.kill()
            await proc.wait()
            count += 1
        except Exception:
            pass
    running_processes.clear()
    return [types.TextContent(type="text", text=f"Terminated {count} processes")]


# ═══════════════════════════════════════════════════════════════════════
# TMUX-BASED COMMAND EXECUTION
# Commands run in tmux sessions persist even after client disconnect
# ═══════════════════════════════════════════════════════════════════════


@server.tool()
async def tmux_execute(
    command: str,
    cwd: str,
    session_name: str = None,
) -> List[types.TextContent]:
    """
    Execute a command in a new tmux session.
    The command continues running even if the MCP client disconnects.

    Args:
        command: Shell command to execute
        cwd: Working directory
        session_name: Optional name for the tmux session (auto-generated if not provided)

    Returns:
        Session ID and initial output
    """
    import uuid
    import subprocess

    # Validate cwd
    if not utils.is_subpath(
        os.path.realpath(os.path.abspath(cwd)), config.SETTINGS.ALLOWED_DIRECTORIES
    ):
        return [
            types.TextContent(type="text", text=f"Error: Directory not allowed: {cwd}")
        ]

    # Generate session name if not provided
    if not session_name:
        session_name = f"mcp_{uuid.uuid4().hex[:8]}"

    # Escape command for tmux - wrap in bash -c
    escaped_command = "bash -c '" + command.replace("'", "'\\''") + "'"

    # Create tmux session and run command
    # Using -d to detach, -s for session name, -c for working directory
    try:
        # First, create a detached session with bash as the default command
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name, "-c", cwd, "bash"],
            capture_output=True,
            check=True,
        )

        # Send the command to the session (use C-m for Enter)
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, command, "Enter"],
            capture_output=True,
            check=True,
        )

        # Wait a moment for initial output
        await asyncio.sleep(0.5)

        # Capture initial output
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p"],
            capture_output=True,
            text=True,
        )

        output = result.stdout or "(Command started in tmux session)"

        return [
            types.TextContent(
                type="text",
                text=f"""
Tmux Session Started
====================
Session: {session_name}
Command: {command}
Working Directory: {cwd}

Initial Output:
{output}

To attach to this session:
  tmux attach-session -t {session_name}

To kill this session:
  tmux kill-session -t {session_name}

Or use the tmux_get_output tool to get more output.
""",
            )
        ]

    except subprocess.CalledProcessError as e:
        return [
            types.TextContent(
                type="text", text=f"Error creating tmux session: {e.stderr}"
            )
        ]
    except FileNotFoundError:
        return [
            types.TextContent(
                type="text", text="Error: tmux not found. Please install tmux."
            )
        ]


@server.tool()
async def tmux_get_output(
    session_name: str,
    clear_after: bool = False,
) -> List[types.TextContent]:
    """
    Get output from a tmux session.

    Args:
        session_name: Name of the tmux session
        clear_after: Clear the pane after capturing (default: False)

    Returns:
        Current output from the session
    """
    import subprocess

    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p"],
            capture_output=True,
            text=True,
        )

        output = result.stdout or "(No output)"

        if clear_after:
            subprocess.run(
                ["tmux", "send-keys", "-t", session_name, "C-c"],
                capture_output=True,
            )

        return [
            types.TextContent(
                type="text",
                text=f"""
Session: {session_name}
========================
{output.strip()}
""",
            )
        ]

    except subprocess.CalledProcessError as e:
        return [types.TextContent(type="text", text=f"Error: {e.stderr}")]
    except FileNotFoundError:
        return [types.TextContent(type="text", text="Error: tmux not found.")]


@server.tool()
async def tmux_send_input(
    session_name: str,
    input_text: str,
) -> List[types.TextContent]:
    """
    Send input to a running tmux session.

    Args:
        session_name: Name of the tmux session
        input_text: Text to send to the session

    Returns:
        Confirmation message
    """
    import subprocess

    escaped_input = input_text.replace("'", "'\\''")

    try:
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, escaped_input, "Enter"],
            capture_output=True,
            check=True,
        )

        return [
            types.TextContent(
                type="text", text=f"Sent to session {session_name}: {input_text}"
            )
        ]

    except subprocess.CalledProcessError as e:
        return [types.TextContent(type="text", text=f"Error: {e.stderr}")]
    except FileNotFoundError:
        return [types.TextContent(type="text", text="Error: tmux not found.")]


@server.tool()
async def tmux_list() -> List[types.TextContent]:
    """
    List all active tmux sessions.

    Returns:
        List of active sessions
    """
    import subprocess

    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
        )

        sessions = result.stdout.strip().split("\n") if result.stdout.strip() else []

        if not sessions or sessions == [""]:
            return [types.TextContent(type="text", text="No active tmux sessions")]

        lines = ["Active Tmux Sessions:", ""]
        for session in sessions:
            if session:
                lines.append(f"  - {session}")

        lines.append("")
        lines.append("To attach: tmux attach-session -t <name>")

        return [types.TextContent(type="text", text="\n".join(lines))]

    except subprocess.CalledProcessError:
        return [types.TextContent(type="text", text="No active tmux sessions")]
    except FileNotFoundError:
        return [types.TextContent(type="text", text="Error: tmux not found.")]


@server.tool()
async def tmux_kill(session_name: str) -> List[types.TextContent]:
    """
    Kill a tmux session.

    Args:
        session_name: Name of the tmux session to kill

    Returns:
        Confirmation message
    """
    import subprocess

    try:
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True,
            check=True,
        )

        return [
            types.TextContent(type="text", text=f"Killed tmux session: {session_name}")
        ]

    except subprocess.CalledProcessError as e:
        return [types.TextContent(type="text", text=f"Error: {e.stderr}")]
    except FileNotFoundError:
        return [types.TextContent(type="text", text="Error: tmux not found.")]


def main():
    """Main entry point for the MCP server."""
    import logging

    # Suppress ClosedResourceError logs that happen when clients disconnect
    # This is a known issue in FastMCP where disconnected clients cause TaskGroup crashes
    logging.getLogger("mcp.server.streamable_http_manager").setLevel(logging.CRITICAL)
    logging.getLogger("mcp").setLevel(logging.CRITICAL)
    logging.getLogger("fastmcp").setLevel(logging.CRITICAL)

    print(f"Starting MCP server with transport={config.SETTINGS.TRANSPORT}")

    if config.SETTINGS.TRANSPORT == "stdio":
        server.run()
    elif config.SETTINGS.TRANSPORT == "http":
        server.run(
            transport="http",
            port=config.SETTINGS.PORT,
            host=config.SETTINGS.HOST,
            path=config.SETTINGS.PATH,
        )


def _run_server():
    """Wrapper to run server with error suppression for client disconnects."""
    import logging
    import sys

    # Suppress ClosedResourceError that happens when clients disconnect
    logging.getLogger("mcp.server.streamable_http_manager").setLevel(logging.CRITICAL)
    logging.getLogger("mcp").setLevel(logging.CRITICAL)
    logging.getLogger("fastmcp").setLevel(logging.CRITICAL)
    logging.getLogger("anyio").setLevel(logging.CRITICAL)

    # Custom exception handler to suppress client disconnect errors
    old_excepthook = sys.excepthook

    def new_excepthook(exc_type, exc_value, exc_traceback):
        # Suppress ClosedResourceError from crashing the server
        if exc_type.__name__ == "ClosedResourceError":
            print(
                f"INFO: Client disconnected (ClosedResourceError suppressed)",
                file=sys.stderr,
            )
            return
        # Also suppress ExceptionGroup containing ClosedResourceError
        if exc_type.__name__ == "BaseExceptionGroup":
            if "unhandled errors" in str(exc_value):
                # Check if it's just ClosedResourceError
                for cause in exc_value.exceptions or []:
                    if "ClosedResourceError" in str(type(cause).__name__):
                        print(
                            f"INFO: Client disconnected (ExceptionGroup suppressed)",
                            file=sys.stderr,
                        )
                        return
        old_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = new_excepthook

    main()


if __name__ == "__main__":
    _run_server()
