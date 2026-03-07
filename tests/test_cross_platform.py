"""Cross-platform edge case tests for path, command, and encoding behavior."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from shell_mcp_server.execution_policy import resolve_request
from shell_mcp_server import execution_policy
from shell_mcp_server.executor import _build_shell_command, run_shell_command
from shell_mcp_server.platform_adapters.windows import build_windows_shell_command
 
def test_windows_path_mapping_uses_mnt_on_wsl(runtime_settings):
    runtime_settings.PLATFORM = "windows"
    mapped = execution_policy._coerce_platform_path(r"C:\Users\axdev", runtime_settings)
    assert str(mapped).startswith("/mnt/c/")


def test_windows_path_mapping_not_forced_without_mnt(runtime_settings, monkeypatch):
    runtime_settings.PLATFORM = "windows"
    monkeypatch.setattr(execution_policy.platform, "system", lambda: "Windows")
    mapped = execution_policy._coerce_platform_path(r"C:\Users\axdev", runtime_settings)
    assert not str(mapped).startswith("/mnt/")






def test_windows_adapter_untrusted_bash_uses_drun():
    built = build_windows_shell_command(
        shell="bash",
        shell_path="powershell.exe",
        command="echo ok",
        cwd="C:/tmp",
        trusted=False,
    )
    assert built[0] == "powershell.exe"
    assert "drun '" in built[-1]


def test_windows_adapter_untrusted_maps_host_cwd_to_sandbox_path():
    built = build_windows_shell_command(
        shell="bash",
        shell_path="powershell.exe",
        command="pwd",
        cwd=r"C:\Users\axdev\dev\repo\proj",
        trusted=False,
        host_root=r"C:\Users\axdev\dev\repo",
        work_dir="/app/repo",
    )
    encoded = built[-1].split("drun 'echo ", maxsplit=1)[1].split(" | base64 -d | bash'", maxsplit=1)[0]
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert "cd '/app/repo' && pwd" in decoded


def test_windows_adapter_untrusted_falls_back_to_workdir_when_outside_root():
    built = build_windows_shell_command(
        shell="bash",
        shell_path="powershell.exe",
        command="pwd",
        cwd=r"C:\Users\axdev\dev\shell-mcp-server",
        trusted=False,
        host_root=r"C:\Users\axdev\dev\repo",
        work_dir="/app/repo",
    )
    encoded = built[-1].split("drun 'echo ", maxsplit=1)[1].split(" | base64 -d | bash'", maxsplit=1)[0]
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert "cd '/app/repo' && pwd" in decoded


def test_windows_adapter_trusted_bash_is_native():
    built = build_windows_shell_command(
        shell="bash",
        shell_path="powershell.exe",
        command="echo ok",
        cwd="C:/tmp",
        trusted=True,
    )
    assert built[0] == "powershell.exe"
    assert built[-1] == "echo ok"





def test_docker_compose_has_sandbox_limits():
    compose = Path("docker/docker-compose.yml").read_text(encoding="utf-8")
    assert "network_mode: \"none\"" in compose
    assert "mem_limit: 512m" in compose
    assert "cpus: 0.5" in compose
