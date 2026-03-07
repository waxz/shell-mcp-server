"""Execution policy and command resolution."""

from __future__ import annotations

import logging
import re
import platform
from pathlib import Path
from pathlib import PurePosixPath
from pathlib import PureWindowsPath

from . import config
from .models import ExecutionRequest

logger = logging.getLogger(__name__)

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


def _coerce_platform_path(path_text: str, settings: config.Settings,is_trusted:bool) -> str:
    logger.debug(
        "run _coerce_platform_path, is_trusted:%s path_text:%s",
        is_trusted,
        path_text,
    )
    if not is_trusted:
        if  _is_windows_style_path(path_text):
            raise ValueError(f"Invalid path {path_text} in is_trusted:{is_trusted} env")
        else:
            path = PurePosixPath(path_text)
            if path.is_absolute():
                resolved = PurePosixPath(path_text)
                logger.debug("1 _coerce_platform_path %s", resolved)
                return str(resolved)
            else:
                host_dir = PurePosixPath(settings.DOCKER_SANDBOX_WORKDIR)
                resolved = PurePosixPath(host_dir, path)
                logger.debug("host_dir:%s", host_dir)
                logger.debug("path:%s", path)
                logger.debug("2 _coerce_platform_path %s", resolved)

                return str(resolved)

    else:
        if settings.PLATFORM == "windows":
            windows_path = PureWindowsPath(path_text)
            if windows_path.is_absolute():
                resolved = Path(str(windows_path))
                logger.debug("3 _coerce_platform_path %s", resolved)

                return str(resolved)
            else:
                resolved = Path(settings.DOCKER_SANDBOX_HOST_ROOT, *windows_path.parts[1:])
                logger.debug("4 _coerce_platform_path %s", resolved)

                return str(resolved)
        else:
            path = Path(path_text)
            if path.is_absolute():
                resolved = Path(path_text)
                logger.debug("5 _coerce_platform_path %s", resolved)
                return str(resolved)

            else:
                host_dir = Path(settings.DOCKER_SANDBOX_HOST_ROOT)
                resolved = Path(host_dir, path)
                logger.debug("6 _coerce_platform_path %s", resolved)

                return str(resolved)



def _is_absolute_for_platform(path_text: str, settings: config.Settings,is_trusted:bool) -> bool:
    if not is_trusted:
        if  _is_windows_style_path(path_text):
            raise ValueError(f"_is_absolute_for_platform Invalid path {path_text} in is_trusted:{is_trusted} env")
        else:
            return Path(path_text).is_absolute()
    else:
        if settings.PLATFORM == "windows":
            return PureWindowsPath(path_text).is_absolute()
        else:
            return Path(path_text).is_absolute()

def _allowed_directories(settings: config.Settings, is_trusted: bool) -> list[str]:
    logger.debug("run _allowed_directories is_trusted:%s", is_trusted)
    logger.debug(
        "run _allowed_directories settings.ALLOWED_DIRECTORIES_HOST:%s",
        settings.ALLOWED_DIRECTORIES_HOST,
    )
    logger.debug(
        "run _allowed_directories settings.ALLOWED_DIRECTORIES_DOCKER:%s",
        settings.ALLOWED_DIRECTORIES_DOCKER,
    )
    if is_trusted:
        return settings.ALLOWED_DIRECTORIES_HOST
    return settings.ALLOWED_DIRECTORIES_DOCKER


def _is_allowed_path(path: str, settings: config.Settings, is_trusted: bool) -> bool:
    if not is_trusted:
        resolved = PurePosixPath(path)
        for allowed in _allowed_directories(settings, is_trusted):
            logger.debug("run _is_allowed_path allowed:%s", allowed)
            allowed_path = _coerce_platform_path(allowed, settings, is_trusted)
            allowed_path = PurePosixPath(allowed_path)
            logger.debug("run _is_allowed_path allowed_path:%s", allowed_path)
            if resolved == allowed_path or allowed_path in resolved.parents:
                return True
    else:
        resolved = Path(path).resolve()
        for allowed in _allowed_directories(settings, is_trusted):
            logger.debug("run _is_allowed_path allowed:%s", allowed)
            allowed_path = _coerce_platform_path(allowed, settings, is_trusted)
            allowed_path = Path(allowed_path).resolve()
            logger.debug("run _is_allowed_path allowed_path:%s", allowed_path)
            if resolved == allowed_path or allowed_path in resolved.parents:
                return True
    return False


def _resolve_absolute_cwd(cwd: str, settings: config.Settings,is_trusted:bool) -> str:
    logger.debug("run _resolve_absolute_cwd _coerce_platform_path cwd:%s", cwd)
    logger.debug("run _resolve_absolute_cwd _coerce_platform_path settings:%s", settings)
    logger.debug("run _resolve_absolute_cwd _coerce_platform_path is_trusted:%s", is_trusted)
    resolved = _coerce_platform_path(cwd, settings,is_trusted)
    logger.debug("run _resolve_absolute_cwd _coerce_platform_path resolved:%s", resolved)

    if not _is_allowed_path(resolved, settings,is_trusted):
        raise ValueError("Directory not allowed")
    return str(resolved)



def resolve_request(command: str, cwd: str, shell: str = "bash") -> ExecutionRequest:
    """Resolve trusted command mapping and validate path/shell policy."""
    settings = config.SETTINGS
    if settings is None:
        raise RuntimeError("Server settings are not initialized")

    logger.debug("run resolve_request command:%s", command)
    logger.debug("run resolve_request cwd:%s", cwd)
    logger.debug("run resolve_request shell:%s", shell)

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
    logger.debug(
        "try _resolve_absolute_cwd:%s settings:%s is_trusted:%s",
        resolved_cwd,
        settings,
        is_trusted,
    )

    absolute_cwd = _resolve_absolute_cwd(
        cwd=resolved_cwd,
        settings=settings,
        is_trusted=is_trusted
    )

    logger.debug("absolute_cwd:%s", absolute_cwd)

    return ExecutionRequest(
        command=resolved_command,
        cwd=absolute_cwd,
        shell=resolved_shell,
        trusted=is_trusted,
    )
