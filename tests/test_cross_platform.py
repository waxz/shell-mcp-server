"""Cross-platform edge case tests for path, command, and encoding behavior."""

from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest

from shell_mcp_server import execution_policy
from shell_mcp_server.platform_adapters import windows as windows_adapter
from shell_mcp_server.platform_adapters.posix import build_posix_shell_command
from shell_mcp_server.platform_adapters.windows import build_windows_shell_command


def _extract_encoded_runner(command_text: str) -> str:
    match = re.search(r'drun "echo ([A-Za-z0-9+/=]+) \| base64 -d \| bash"', command_text)
    assert match is not None
    return match.group(1)


def test_windows_path_mapping_keeps_windows_absolute(runtime_settings):
    runtime_settings.PLATFORM = "windows"
    mapped = execution_policy._coerce_platform_path(r"C:\Users\axdev", runtime_settings)
    assert str(mapped) == r"C:\Users\axdev"


def test_untrusted_rejects_windows_style_path(runtime_settings):
    with pytest.raises(ValueError):
        execution_policy._coerce_platform_path(r"C:\Users\axdev", runtime_settings, is_trusted=False)


def test_windows_adapter_untrusted_bash_uses_drun():
    built = build_windows_shell_command(
        shell="bash",
        shell_path="powershell.exe",
        command="echo ok",
        cwd=".",
        trusted=False,
    )
    assert built[0] == "powershell.exe"
    assert 'drun "echo ' in built[-1]


def test_windows_adapter_untrusted_maps_host_cwd_to_sandbox_path(monkeypatch):
    monkeypatch.setattr(windows_adapter, "_validate_cwd_exists", lambda _cwd: None)
    built = build_windows_shell_command(
        shell="bash",
        shell_path="powershell.exe",
        command="pwd",
        cwd=r"C:\Users\axdev\dev\repo\proj",
        trusted=False,
        host_root=r"C:\Users\axdev\dev\repo",
        work_dir="/app/repo",
    )
    encoded = _extract_encoded_runner(built[-1])
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert "cd '/app/repo/proj' && pwd;" in decoded


def test_windows_adapter_untrusted_falls_back_to_workdir_when_outside_root(monkeypatch):
    monkeypatch.setattr(windows_adapter, "_validate_cwd_exists", lambda _cwd: None)
    built = build_windows_shell_command(
        shell="bash",
        shell_path="powershell.exe",
        command="pwd",
        cwd=r"C:\Users\axdev\dev\shell-mcp-server",
        trusted=False,
        host_root=r"C:\Users\axdev\dev\repo",
        work_dir="/app/repo",
    )
    encoded = _extract_encoded_runner(built[-1])
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert "cd '/app/repo' && pwd;" in decoded


def test_windows_adapter_trusted_bash_is_native():
    built = build_windows_shell_command(
        shell="bash",
        shell_path="powershell.exe",
        command="echo ok",
        cwd=".",
        trusted=True,
    )
    assert built[0] == "powershell.exe"
    assert built[-1] == "echo ok"


def test_posix_adapter_raises_on_missing_cwd(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="Directory does not exist"):
        build_posix_shell_command(
            shell_path="bash",
            command="echo ok",
            cwd=str(missing),
        )


def test_windows_adapter_raises_on_missing_cwd(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="Directory does not exist"):
        build_windows_shell_command(
            shell="bash",
            shell_path="powershell.exe",
            command="echo ok",
            cwd=str(missing),
            trusted=True,
        )


def test_docker_compose_has_sandbox_limits():
    compose = Path("docker/docker-compose.yml").read_text(encoding="utf-8")
    assert "mem_limit: 512m" in compose
    assert "cpus: 0.5" in compose
