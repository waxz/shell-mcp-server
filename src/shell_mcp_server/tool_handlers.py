"""MCP tool handlers for shell execution and process management."""

from __future__ import annotations

import logging
import uuid
import json
import mcp.types as types
from anyio import ClosedResourceError
from fastmcp import Context, FastMCP
from typing import Dict, List,Any

from fastmcp.server.tasks import TaskConfig

from . import config
from .executor import (
    list_running_process_records,
    run_shell_command,
    terminate_all_processes,
    terminate_process_by_pid,
)
from .models import (
    ExecuteCommandInput,
    NameInput,
    PidInput,
    TmuxExecuteInput,
    TmuxGetOutputInput,
    TmuxListInput,
    TmuxSessionInput,
)
from .tmux_commands import (
    build_tmux_bootstrap_command,
    build_tmux_capture_command,
    build_tmux_clear_command,
    build_tmux_kill_command,
    build_tmux_reset_pane_command,
    build_tmux_send_keys_command,
)

logger = logging.getLogger(__name__)


def register_tools(server: FastMCP) -> None:
    """Register MCP tools."""

    async def _execute_with_stream(
        command: str,
        cwd: str,
        ctx: Context,
        shell: str,
        persistent_sandbox: bool = False,
    ) -> list[types.TextContent]:
        async def _on_stdout(line: str) -> None:
            try:
                await ctx.info(line)
            except ClosedResourceError:
                pass

        async def _on_stderr(line: str) -> None:
            try:
                await ctx.warning(line)
            except ClosedResourceError:
                pass

        try:
            result = await run_shell_command(
                command=command,
                cwd=cwd,
                shell=shell,
                on_stdout=_on_stdout,
                on_stderr=_on_stderr
            )
        except ClosedResourceError:
            return [types.TextContent(type="text", text="[client disconnected]")]


        if result.cancelled:
            return [types.TextContent(type="text", text="[client disconnected]")]

        parts: list[str] = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            parts.append(f"[stderr]\n{result.stderr}")
        parts.append(f"[exit code: {result.exit_code}]")
        if result.timed_out and config.SETTINGS is not None:
            parts.append(f"[timed out after {config.SETTINGS.COMMAND_TIMEOUT}s]")
        return [types.TextContent(type="text", text="\n\n".join(parts))]

    @server.tool(task=TaskConfig(mode="optional"))
    async def execute_command(
        command: str,
        cwd: str,
        ctx: Context,
        shell: str = "bash",
    ) -> list[types.TextContent]:
        """Run a shell command and stream output; returns `Execution failed: ...` on errors."""
        try:
            logger.debug(
                "Receive command: command=%s, cwd=%s, shell=%s",
                command,
                cwd,
                shell,
            )
            req = ExecuteCommandInput(command=command, cwd=cwd, shell=shell)
            logger.debug(
                "Request command: command=%s, cwd=%s, shell=%s",
                req.command,
                req.cwd,
                req.shell,
            )

            return await _execute_with_stream(
                command=req.command,
                cwd=req.cwd,
                ctx=ctx,
                shell=req.shell,
            )
        except Exception as exc:
            raise exc
            # return [types.TextContent(type="text", text=f"Execution failed: {exc}")]


    @server.tool(task=TaskConfig(mode="optional"))
    async def list_processes() -> list[dict[str, Any]] | None:
        """List tracked child processes."""
        records = list_running_process_records()
        if not records:
            return None
            # return [types.TextContent(type="text", text="No running processes")]

        # lines = ["Running processes:"]
        pid_info_list = []
        for record in records:
            # lines.append(
            #     f"  PID {record.pid}: shell={record.shell} cwd={record.cwd} command={record.command}"
            # )
            pid_info_list.append(
                {
                    "PID": record.pid,
                    "shell" : record.shell,
                    "cwd" : record.cwd ,
                    "command"  :  record.command,
                }
            )

        resp = json.dumps(pid_info_list)
        logging.info(f"resp:{resp}")
        return pid_info_list
        # return [types.TextContent(type="text", text="\n".join(lines))]

    @server.tool(task=TaskConfig(mode="optional"))
    async def terminate_process(pid: int) -> list[types.TextContent]:
        """Terminate one tracked PID; returns not found when missing."""
        req = PidInput(pid=pid)
        terminated = await terminate_process_by_pid(req.pid)
        if not terminated:
            return [types.TextContent(type="text", text=f"Process {req.pid} not found")]
        return [types.TextContent(type="text", text=f"Process {req.pid} terminated")]

    @server.tool(task=TaskConfig(mode="optional"))
    async def terminate_all_processes() -> list[types.TextContent]:
        """Terminate all tracked processes."""
        count = await terminate_all_processes()
        return [types.TextContent(type="text", text=f"Terminated {count} processes")]


    @server.tool(task=TaskConfig(mode="optional"))
    async def tmux_execute(
        command: str,
        cwd: str,
        ctx: Context,
        session_name: str = "",
        shell: str = "bash",
    ) -> list[types.TextContent]:
        """Run a command in tmux; validates `session_name`."""
        req = TmuxExecuteInput(
            command=command,
            cwd=cwd,
            session_name=session_name,
            shell=shell,
        )
        if not req.session_name:
            req.session_name = f"mcp_{uuid.uuid4().hex[:8]}"
        await _execute_with_stream(
            command=build_tmux_bootstrap_command(session_name=req.session_name),
            cwd=req.cwd,
            ctx=ctx,
            shell=req.shell,
            persistent_sandbox=True,
        )
        await _execute_with_stream(
            command=build_tmux_reset_pane_command(session_name=req.session_name),
            cwd=req.cwd,
            ctx=ctx,
            shell=req.shell,
            persistent_sandbox=True,
        )
        await _execute_with_stream(
            command=build_tmux_send_keys_command(
                session_name=req.session_name,
                command=req.command,
            ),
            cwd=req.cwd,
            ctx=ctx,
            shell=req.shell,
            persistent_sandbox=True,
        )
        return await _execute_with_stream(
            command=build_tmux_capture_command(session_name=req.session_name),
            cwd=req.cwd,
            ctx=ctx,
            shell=req.shell,
            persistent_sandbox=True,
        )

    @server.tool(task=TaskConfig(mode="optional"))
    async def tmux_get_output(
        session_name: str,
        ctx: Context,
        cwd: str = ".",
        clear_after: bool = False,
        shell: str = "bash",
    ) -> list[types.TextContent]:
        """Capture tmux pane output; optionally clear after reading."""
        req = TmuxGetOutputInput(
            session_name=session_name,
            cwd=cwd,
            clear_after=clear_after,
            shell=shell,
        )
        result = await _execute_with_stream(
            command=build_tmux_capture_command(session_name=req.session_name),
            cwd=req.cwd,
            ctx=ctx,
            shell=req.shell,
            persistent_sandbox=True,
        )
        if req.clear_after:
            await _execute_with_stream(
                command=build_tmux_clear_command(session_name=req.session_name),
                cwd=req.cwd,
                ctx=ctx,
                shell=req.shell,
                persistent_sandbox=True,
            )
        return result

    @server.tool(task=TaskConfig(mode="optional"))
    async def tmux_list_session(
        ctx: Context,
        cwd: str = ".",
        shell: str = "bash",
    ) -> list[types.TextContent]:
        """List active tmux sessions."""
        req = TmuxListInput(cwd=cwd, shell=shell)
        return await _execute_with_stream(
            command="tmux ls",
            cwd=req.cwd,
            ctx=ctx,
            shell=req.shell,
            persistent_sandbox=True,
        )

    @server.tool(task=TaskConfig(mode="optional"))
    async def tmux_kill_session(
        session_name: str,
        ctx: Context,
        cwd: str = ".",
        shell: str = "bash",
    ) -> list[types.TextContent]:
        """Kill a tmux session by validated name."""
        req = TmuxSessionInput(session_name=session_name, cwd=cwd, shell=shell)
        return await _execute_with_stream(
            command=build_tmux_kill_command(session_name=req.session_name),
            cwd=req.cwd,
            ctx=ctx,
            shell=req.shell,
            persistent_sandbox=True,
        )
