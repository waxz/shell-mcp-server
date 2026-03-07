"""Windows command adapter with strict argument escaping."""

from __future__ import annotations

import base64
from pathlib import PurePosixPath
from pathlib import PureWindowsPath


def _ps_single_quoted(value: str) -> str:
    """Escape a string for PowerShell single-quoted literal context."""
    return value.replace("'", "''")


def _map_host_cwd_to_sandbox(
    cwd: str,
    host_root: str | None,
    work_dir: str | None,
) -> str:
    """Map a Windows host cwd into the Linux sandbox path space."""
    if not work_dir:
        return cwd or "."
    return str(PurePosixPath(work_dir))


def build_windows_shell_command(
    shell: str,
    shell_path: str,
    command: str,
    cwd: str,
    trusted: bool = False,
    work_dir: str | None = None,
    host_root: str | None = None,
) -> list[str]:
    """Build a Windows shell invocation argument list."""
    if shell == "wsl":
        return [shell_path, "--cd", cwd, "bash", "-c", command]

    if shell == "cmd":
        return [shell_path, "/c", command]

    if shell == "bash" and not trusted:
        sandbox_cwd = _map_host_cwd_to_sandbox(cwd=cwd, host_root=host_root, work_dir=work_dir)
        if cwd in {"", "."}:
            wrapped_command = command
        else:
            wrapped_command = f"cd '{_ps_single_quoted(sandbox_cwd)}' && {command}"
        encoded_command = base64.b64encode(wrapped_command.encode("utf-8")).decode("ascii")
        safe_runner = f"echo {encoded_command} | base64 -d | bash"
        host_root = _ps_single_quoted(host_root or cwd)
        work_dir = _ps_single_quoted(work_dir or cwd)
        return [
            "powershell.exe",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"""
                $ENV:DOCKER_SANDBOX_HOST_ROOT_OVERRIDE="{host_root}";
                $ENV:DOCKER_SANDBOX_WORKDIR_OVERRIDE="{work_dir}";
                drun "{safe_runner}"
                """
        ]

    return [shell_path, "-ExecutionPolicy", "Bypass", "-Command", command]
