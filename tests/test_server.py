"""Tests for execution behavior and policy enforcement."""

from __future__ import annotations

import pytest

from shell_mcp_server.executor import run_shell_command
from shell_mcp_server.execution_policy import resolve_request, validate_tmux_session_name




@pytest.mark.asyncio
async def test_run_shell_command_invalid_directory(runtime_settings):
    with pytest.raises(ValueError, match="Directory not allowed"):
        await run_shell_command("echo hello", cwd="/")








def test_validate_tmux_session_name():
    assert validate_tmux_session_name("mcp_1") == "mcp_1"
    with pytest.raises(ValueError):
        validate_tmux_session_name("bad session name;")


def test_resolve_request_untrusted_current_dir_allowed(runtime_settings):
    runtime_settings.DOCKER_SANDBOX_WORKDIR = "/app/dev/repo2"
    runtime_settings.ALLOWED_DIRECTORIES_DOCKER = ["/app/dev/repo2", "/tmp"]

    request = resolve_request(command="echo ok", cwd=".", shell="bash")
    assert request.cwd == "/app/dev/repo2"
    assert request.trusted is False


def test_resolve_request_untrusted_parent_traversal_blocked(runtime_settings):
    runtime_settings.DOCKER_SANDBOX_WORKDIR = "/app/dev/repo2"
    runtime_settings.ALLOWED_DIRECTORIES_DOCKER = ["/app/dev/repo2", "/tmp"]

    with pytest.raises(ValueError, match="Directory not allowed"):
        resolve_request(command="echo traversal", cwd="../", shell="bash")


def test_resolve_request_rejects_shell_injection_chars(runtime_settings):
    with pytest.raises(ValueError, match="Invalid shell"):
        resolve_request(command="echo invalid-shell", cwd=".", shell="bash;whoami")
