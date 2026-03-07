"""POSIX command adapter."""

from __future__ import annotations

import base64
import shlex


def build_posix_shell_command(
    shell_path: str,
    command: str,
    cwd: str,
    trusted: bool = False,
    work_dir: str | None = None,
    host_root: str | None = None,
) -> list[str]:
    """Build a POSIX shell invocation argument list."""
    if cwd in {"", "."}:
        wrapped_command = command
    else:
        wrapped_command = f"cd {shlex.quote(cwd)} && {command}"
    
    if not trusted:
        encoded_command = base64.b64encode(wrapped_command.encode("utf-8")).decode("ascii")
        safe_runner = f"echo {encoded_command} | base64 -d | bash"
        return [shell_path, "-c", f"source ~/.bashrc && export DOCKER_SANDBOX_HOST_ROOT_OVERRIDE={host_root} && export DOCKER_SANDBOX_WORKDIR_OVERRIDE={work_dir} && drun '{safe_runner}'"]

    return [shell_path, "-c", wrapped_command]
