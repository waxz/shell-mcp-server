"""Tests for execution behavior and policy enforcement."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from shell_mcp_server.executor import run_shell_command, running_processes
from shell_mcp_server.execution_policy import validate_tmux_session_name


@pytest.mark.asyncio
async def test_run_shell_command_success(runtime_settings):
    result = await run_shell_command("echo hello", cwd=runtime_settings.ALLOWED_DIRECTORIES[0])
    assert result.exit_code == 0
    assert "hello" in result.stdout


@pytest.mark.asyncio
async def test_run_shell_command_invalid_directory(runtime_settings):
    with pytest.raises(ValueError, match="Directory not allowed"):
        await run_shell_command("echo hello", cwd="/")


@pytest.mark.asyncio
async def test_run_shell_command_invalid_shell(runtime_settings):
    runtime_settings.SAFETY_MODE = "relax"
    with pytest.raises(ValueError, match="not allowed"):
        await run_shell_command(
            "echo hello",
            cwd=runtime_settings.ALLOWED_DIRECTORIES[0],
            shell="invalid",
        )


@pytest.mark.asyncio
async def test_run_shell_command_timeout(runtime_settings):
    runtime_settings.COMMAND_TIMEOUT = 1
    result = await run_shell_command("sleep 2", cwd=runtime_settings.ALLOWED_DIRECTORIES[0])
    assert result.timed_out is True
    assert "Timed out" in result.stderr


@pytest.mark.asyncio
async def test_trusted_command_override(runtime_settings):
    runtime_settings.TRUSTED_COMMANDS = {
        "trusted_echo": {
            "command": "echo trusted",
            "cwd": runtime_settings.ALLOWED_DIRECTORIES[0],
            "shell": "sh",
        }
    }
    result = await run_shell_command("trusted_echo", cwd="/", shell="bash")
    assert result.exit_code == 0
    assert "trusted" in result.stdout
    assert result.shell == "sh"


def test_validate_tmux_session_name():
    assert validate_tmux_session_name("mcp_1") == "mcp_1"
    with pytest.raises(ValueError):
        validate_tmux_session_name("bad session name;")


@pytest.mark.asyncio
async def test_timeout_kills_long_running_background_command(runtime_settings):
    runtime_settings.COMMAND_TIMEOUT = 1
    marker = Path(runtime_settings.ALLOWED_DIRECTORIES[0]) / "background_leak.txt"
    command = (
        f"(sleep 2; echo leaked > {marker.as_posix()}) & "
        "sleep 10"
    )

    result = await run_shell_command(command, cwd=runtime_settings.ALLOWED_DIRECTORIES[0])
    assert result.timed_out is True

    await asyncio.sleep(2.5)
    assert not marker.exists()
    assert len(running_processes) == 0


@pytest.mark.asyncio
async def test_client_disconnect_callback_cancels_process(runtime_settings):
    async def disconnect_on_first_line(_: str) -> None:
        raise BrokenPipeError("simulated client disconnect")

    result = await run_shell_command(
        command="for i in 1 2 3; do echo line$i; sleep 1; done",
        cwd=runtime_settings.ALLOWED_DIRECTORIES[0],
        on_stdout=disconnect_on_first_line,
    )
    assert result.cancelled is True
    assert "Client disconnected" in result.stderr
    assert len(running_processes) == 0
