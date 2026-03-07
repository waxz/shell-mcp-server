"""Tests for execution behavior and policy enforcement."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from shell_mcp_server.executor import run_shell_command, running_processes
from shell_mcp_server.execution_policy import validate_tmux_session_name




@pytest.mark.asyncio
async def test_run_shell_command_invalid_directory(runtime_settings):
    with pytest.raises(ValueError, match="Directory not allowed"):
        await run_shell_command("echo hello", cwd="/")








def test_validate_tmux_session_name():
    assert validate_tmux_session_name("mcp_1") == "mcp_1"
    with pytest.raises(ValueError):
        validate_tmux_session_name("bad session name;")


