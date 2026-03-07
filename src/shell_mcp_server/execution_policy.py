"""Execution policy and command resolution."""

from __future__ import annotations

import re
import platform
from pathlib import Path
from pathlib import PurePosixPath
from pathlib import PureWindowsPath

from . import config
from .models import ExecutionRequest

_SESSION_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def validate_tmux_session_name(session_name: str) -> str:
    """Validate tmux session name against a strict allowlist."""
    if not _SESSION_NAME_RE.fullmatch(session_name):
        raise ValueError("Invalid tmux session name")
    return session_name


def _validate_string_input(value: str, field_name: str) -> str:
    if "\x00" in value:
        raise ValueError(f"Invalid {field_name}: null byte is not allowed")
    if "\r" in value:
        raise ValueError(f"Invalid {field_name}: carriage return is not allowed")
    return value


def _validate_string_cwd(value: str, field_name: str) -> str:
    if "\x00" in value:
        raise ValueError(f"Invalid {field_name}: null byte is not allowed")
    if "\n" in value or "\r" in value:
        raise ValueError(f"Invalid {field_name}: multiline input is not allowed")
    return value

def _is_windows_style_path(path_text: str) -> bool:
    return "\\" in path_text or bool(PureWindowsPath(path_text).drive)


def _can_map_windows_drive_to_mnt() -> bool:
    return platform.system().lower() != "windows" and Path("/mnt").exists()


def _coerce_platform_path(path_text: str, settings: config.Settings) -> Path:
    if settings.PLATFORM != "windows" or not _is_windows_style_path(path_text):
        return Path(path_text)

    windows_path = PureWindowsPath(path_text)
    if windows_path.is_absolute():
        drive = windows_path.drive.rstrip(":").lower()
        if _can_map_windows_drive_to_mnt() and drive and len(drive) == 1 and drive.isalpha():
            mapped = Path("/mnt", drive, *windows_path.parts[1:])
            return mapped
        return Path(str(windows_path))

    if platform.system().lower() == "windows":
        return Path(str(windows_path))
    return Path(*windows_path.parts)


def _is_absolute_for_platform(path_text: str, settings: config.Settings) -> bool:
    if settings.PLATFORM == "windows":
        return PureWindowsPath(path_text).is_absolute()
    return Path(path_text).is_absolute()


def _is_allowed_path(path: Path, settings: config.Settings) -> bool:
    resolved = path.resolve()
    for allowed in settings.ALLOWED_DIRECTORIES:
        allowed_path = _coerce_platform_path(allowed, settings).resolve()
        if resolved == allowed_path or allowed_path in resolved.parents:
            return True
    return False


def _resolve_absolute_cwd(cwd: str, settings: config.Settings) -> str:
    if _is_absolute_for_platform(cwd, settings):
        resolved = _coerce_platform_path(cwd, settings).resolve()
    else:
        base = _coerce_platform_path(settings.ALLOWED_DIRECTORIES[0], settings).resolve()
        relative = _coerce_platform_path(cwd, settings)
        resolved = (base / relative).resolve()

    if not _is_allowed_path(resolved, settings):
        raise ValueError("Directory not allowed")
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError("Directory does not exist")
    return str(resolved)


def _resolve_sandbox_cwd(host_cwd: str, settings: config.Settings) -> str:
    sandbox_root = PurePosixPath(settings.DOCKER_SANDBOX_WORKDIR)
    host_root = _coerce_platform_path(settings.DOCKER_SANDBOX_HOST_ROOT, settings).resolve()
    host_path = _coerce_platform_path(host_cwd, settings).resolve()

    try:
        relative = host_path.relative_to(host_root)
    except ValueError:
        if getattr(settings, "DOCKER_SANDBOX_ENFORCE_CWD_MAP", False):
            raise ValueError("Directory cannot be mapped into sandbox") from None
        if settings.PLATFORM == "windows":
            return "."
        return str(sandbox_root)

    if settings.PLATFORM == "windows":
        relative_text = relative.as_posix().lstrip("/")
        if not relative_text:
            return "."
        # Windows drun often mounts project/docker/app to /app.
        if relative_text == "docker/app":
            return "."
        if relative_text.startswith("docker/app/"):
            return relative_text[len("docker/app/") :]
        return relative_text

    relative_posix = PurePosixPath(relative.as_posix())
    return str(sandbox_root / relative_posix)


def resolve_request(command: str, cwd: str, shell: str = "bash") -> ExecutionRequest:
    """Resolve trusted command mapping and validate path/shell policy."""
    settings = config.SETTINGS
    if settings is None:
        raise RuntimeError("Server settings are not initialized")

    _validate_string_input(command, "command")
    _validate_string_cwd(cwd, "cwd")

    is_trusted = command in settings.TRUSTED_COMMANDS
    resolved_command = command
    resolved_cwd = cwd
    resolved_shell = shell

    if is_trusted:
        command_cfg = settings.TRUSTED_COMMANDS[command]
        resolved_command = command_cfg.get("command", "")
        resolved_cwd = command_cfg.get("cwd", "")
        resolved_shell = command_cfg.get("shell", "")
        if not (resolved_command and resolved_cwd and resolved_shell):
            raise ValueError(f"Incomplete trusted command config: {command}")



    if settings.SAFETY_MODE == "strict" and not is_trusted:
        resolved_shell = "bash"

    if resolved_shell not in settings.ALLOWED_SHELLS:
        available_shells = ", ".join(sorted(settings.ALLOWED_SHELLS.keys()))
        raise ValueError(
            f"Shell '{resolved_shell}' is not allowed. Available: {available_shells}"
        )

    absolute_cwd = _resolve_absolute_cwd(
        cwd=resolved_cwd,
        settings=settings,
    )

    return ExecutionRequest(
        command=resolved_command,
        cwd=absolute_cwd,
        shell=resolved_shell,
        trusted=is_trusted,
    )
