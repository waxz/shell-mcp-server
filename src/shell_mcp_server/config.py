"""Configuration loading and validation for shell MCP server."""

from __future__ import annotations

import logging
import platform
import shutil
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict

import toml
from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings

from .path_utils import is_windows_style_path, normalize_directory_value


def _default_shells(system_name: str) -> dict[str, str]:
    if system_name == "windows":
        return {
            "bash": "powershell.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "wsl": "wsl.exe",
        }
    return {"bash": "/bin/bash", "sh": "/bin/sh"}


logger = logging.getLogger(__name__)


def _normalize_directory_list(value: list[str] | None) -> list[str]:
    if not value:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = normalize_directory_value(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _check_docker_installed():
    # Checks for the 'docker' executable
    docker_path = shutil.which('docker')

    if docker_path:
        print(f"Docker is installed at: {docker_path}")
        return True

    else:
        print("Docker is not installed or not in PATH.")
        return False

class Settings(BaseSettings):
    """Application runtime settings."""

    APP_NAME: str = "shell-mcp-server"
    APP_VERSION: str = "0.1.3"
    COMMAND_TIMEOUT: int = 30
    TRUSTED_COMMANDS: dict[str, dict[str, str]] = {}
    ALLOWED_SHELLS: dict[str, str] = {}
    SAFETY_MODE: str = "strict"
    TRANSPORT: str = "stdio"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    PATH: str = "/mcp"
    PLATFORM: str = "linux"
    IS_IN_DOCKER : bool = False

    ALLOWED_DIRECTORIES_HOST: list[str] = Field(default_factory=list)
    ALLOWED_DIRECTORIES_DOCKER: list[str] = Field(default_factory=list)

    DOCKER_CONFIG: Dict[str, Any] = {}
    DOCKER_SHELL_COMPOSE_FILE: str | None = None
    DOCKER_SHELL_SERVICE: str | None = None
    DOCKER_SHELL_ENV_FILE: str | None = None
    DOCKER_SANDBOX_WORKDIR: str | None = None
    DOCKER_SANDBOX_HOST_ROOT: str | None = None
    DOCKER_SANDBOX_CPUS: str | None = None
    DOCKER_SANDBOX_MEMORY: str | None = None
    DOCKER_SANDBOX_NETWORK: str | None = None
    DOCKER_SANDBOX_ENFORCE_CWD_MAP: bool = False
    UNTRUSTED_USE_DOCKER_SANDBOX: bool = False
    DOCKER_USE_DRUN_ON_LINUX: bool = True

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("COMMAND_TIMEOUT")
    @classmethod
    def _validate_timeout(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("COMMAND_TIMEOUT must be positive")
        return value

    @field_validator("SAFETY_MODE")
    @classmethod
    def _validate_safety_mode(cls, value: str) -> str:
        if value not in {"strict", "relax"}:
            raise ValueError("SAFETY_MODE must be 'strict' or 'relax'")
        return value

    @field_validator("IS_IN_DOCKER")
    @classmethod
    def _validate_is_in_docker(cls, value: str) -> str:
        docker_installed = _check_docker_installed()
        system_name = platform.system().lower()
        if value:
            if docker_installed:
                raise ValueError(f"Enable IS_IN_DOCKER, docker_installed[{docker_installed}] must be [False]")
            if not (system_name == "linux"):
                raise ValueError(f"Enable IS_IN_DOCKER, PLATFORM[{system_name}] must be [linux]")
        return value


    @field_validator("TRANSPORT")
    @classmethod
    def _validate_transport(cls, value: str) -> str:
        if value not in {"stdio", "http"}:
            raise ValueError("TRANSPORT must be 'stdio' or 'http'")
        return value

    @field_validator("ALLOWED_DIRECTORIES_DOCKER")
    @classmethod
    def _normalize_allowed_dirs_docker(cls, value: list[str] | None) -> list[str]:
        return _normalize_directory_list(value)

    @field_validator("ALLOWED_DIRECTORIES_HOST")
    @classmethod
    def _normalize_allowed_dirs_host(cls, value: list[str] | None) -> list[str]:
        return _normalize_directory_list(value)

    @field_validator("DOCKER_SHELL_COMPOSE_FILE")
    @classmethod
    def _normalize_docker_shell_compose_file(cls, value: str | None) -> str | None:
        if not value:
            return None
        path = Path(value).resolve()
        # Check if path exists AND is a file
        if not path.is_file():
            raise ValueError(f"Compose file not found or is not a file: {path}")
        return str(path)

    @field_validator("DOCKER_SHELL_SERVICE")
    @classmethod
    def _normalize_docker_shell_service(cls, value: str | None) -> str | None:
        return value

    @field_validator("DOCKER_SANDBOX_HOST_ROOT")
    @classmethod
    def _normalize_docker_sandbox_host_root(cls, value: str | None) -> str | None:
        if not value:
            return None
        path = Path(value).resolve()
        # Check if path exists AND is a directory
        if not path.is_dir():
            raise ValueError(f"Host root directory does not exist: {path}")
        return str(path)
    @field_validator("DOCKER_SANDBOX_WORKDIR")
    @classmethod
    def _normalize_docker_sandbox_workdir(cls, value: str | None) -> str | None:
        return value

    @field_validator("DOCKER_SANDBOX_CPUS")
    @classmethod
    def _normalize_docker_sandbox_cpus(cls, value: str | None) -> str | None:
        return value

    @field_validator("DOCKER_SANDBOX_MEMORY")
    @classmethod
    def _normalize_docker_sandbox_memory(cls, value: str | None) -> str | None:
        return value

    @field_validator("DOCKER_SANDBOX_NETWORK")
    @classmethod
    def _normalize_docker_sandbox_network(cls, value: str | None) -> str | None:
        return value

    @field_validator("PORT")
    @classmethod
    def _validate_port(cls, value: int) -> int:
        if not (1 <= value <= 65535):
            raise ValueError("PORT must be in range 1..65535")
        return value

    @field_validator("PATH")
    @classmethod
    def _validate_http_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("PATH must start with '/'")
        if any(ch in value for ch in ("\n", "\r", "\x00")):
            raise ValueError("PATH contains invalid control characters")
        return value

    @model_validator(mode="after")
    def _validate_runtime_contract(self) -> "Settings":
        if self.TRANSPORT == "http" and not self.PATH:
            raise ValueError("PATH is required when TRANSPORT is 'http'")

        if self.UNTRUSTED_USE_DOCKER_SANDBOX:
            if not self.DOCKER_SHELL_COMPOSE_FILE:
                raise ValueError(
                    "DOCKER_SHELL_COMPOSE_FILE is required when UNTRUSTED_USE_DOCKER_SANDBOX is true"
                )
            if not self.DOCKER_SHELL_SERVICE:
                raise ValueError(
                    "DOCKER_SHELL_SERVICE is required when UNTRUSTED_USE_DOCKER_SANDBOX is true"
                )
            if not self.DOCKER_SANDBOX_WORKDIR:
                raise ValueError(
                    "DOCKER_SANDBOX_WORKDIR is required when UNTRUSTED_USE_DOCKER_SANDBOX is true"
                )

        self._validate_allowed_shell_paths()
        self._validate_trusted_shell_platform_compatibility()
        return self

    def _validate_allowed_shell_paths(self) -> None:
        virtual_aliases = {
            "bash",
            "sh",
            "cmd",
            "cmd.exe",
            "powershell",
            "powershell.exe",
            "pwsh",
            "pwsh.exe",
            "wsl",
            "wsl.exe",
        }
        for shell_name, shell_path in self.ALLOWED_SHELLS.items():
            if not shell_path:
                raise ValueError(f"Shell '{shell_name}' has empty path")
            if is_windows_style_path(shell_path) or "/" in shell_path:
                if Path(shell_path).exists():
                    continue
                raise ValueError(
                    f"Shell '{shell_name}' path does not exist: {shell_path}"
                )
            if shell_path in virtual_aliases or shutil.which(shell_path):
                continue
            raise ValueError(f"Shell '{shell_name}' executable not found: {shell_path}")

    def _validate_trusted_shell_platform_compatibility(self) -> None:
        for name, spec in self.TRUSTED_COMMANDS.items():
            shell_name = spec.get("shell")
            if not shell_name:
                continue
            shell_path = self.ALLOWED_SHELLS.get(shell_name, "")
            if self.PLATFORM == "windows" and shell_path.startswith("/"):
                raise ValueError(
                    f"Trusted command '{name}' shell '{shell_name}' is not Windows-compatible: {shell_path}"
                )
            if self.PLATFORM != "windows" and (
                shell_path.lower().endswith(".exe") or "\\" in shell_path
            ):
                raise ValueError(
                    f"Trusted command '{name}' shell '{shell_name}' is not POSIX-compatible: {shell_path}"
                )

    @classmethod
    def from_runtime(
        cls,
        args: Namespace,
        parsed_shells: dict[str, str],
        shells_from_cli: bool,
    ) -> "Settings":
        """Load settings with precedence: defaults -> config.toml -> CLI."""
        system_name = platform.system().lower()
        if system_name.startswith("win"):
            platform_name = "windows"
        elif system_name == "darwin":
            platform_name = "macos"
        else:
            platform_name = "linux"

        merged: dict[str, Any] = {
            "PLATFORM": platform_name,
            "ALLOWED_SHELLS": _default_shells(platform_name),
            "DOCKER_CONFIG": {},
            "DOCKER_SHELL_COMPOSE_FILE": None,
        }

        config_path = Path(getattr(args, "config", "config.toml") or "config.toml")
        if config_path.exists():
            file_config = toml.load(config_path)
            merged.update(file_config)

        if shells_from_cli:
            merged["ALLOWED_SHELLS"] = parsed_shells
        elif not merged.get("ALLOWED_SHELLS"):
            merged["ALLOWED_SHELLS"] = parsed_shells

        if getattr(args, "transport", None):
            merged["TRANSPORT"] = args.transport
        if getattr(args, "host", None):
            merged["HOST"] = args.host
        if getattr(args, "port", None):
            merged["PORT"] = args.port
        if args.path:
            merged["PATH"] = args.path
        if getattr(args, "directories", None):
            merged["ALLOWED_DIRECTORIES_HOST"] = list(args.directories)

        merged["DOCKER_SHELL_COMPOSE_FILE"] = merged.get("DOCKER_CONFIG", {}).get(
            "config_file"
        )
        merged["DOCKER_SHELL_SERVICE"] = merged.get("DOCKER_CONFIG", {}).get("service")
        merged["DOCKER_SHELL_ENV_FILE"] = merged.get("DOCKER_CONFIG", {}).get("env_file")

        config_os = merged["DOCKER_CONFIG"].get(platform_name, {})
        merged["DOCKER_SANDBOX_HOST_ROOT"] = config_os.get("host_root")
        merged["DOCKER_SANDBOX_WORKDIR"] = config_os.get("work_dir")
        if "ALLOWED_DIRECTORIES_HOST" not in merged:
            host_dirs = config_os.get(
                "allow_direcotories_host",
                config_os.get("allow_directories_host"),
            )
            merged["ALLOWED_DIRECTORIES_HOST"] = host_dirs or []
        if "ALLOWED_DIRECTORIES_DOCKER" not in merged:
            docker_dirs = config_os.get(
                "allow_direcotories_docker",
                config_os.get("allow_directories_docker"),
            )
            merged["ALLOWED_DIRECTORIES_DOCKER"] = docker_dirs or []

        host_root = merged["DOCKER_SANDBOX_HOST_ROOT"]
        work_dir = merged["DOCKER_SANDBOX_WORKDIR"]
        if merged.get("ALLOWED_DIRECTORIES_HOST") is None and host_root:
            merged["ALLOWED_DIRECTORIES_HOST"] = [host_root]
        elif host_root and host_root not in merged.get("ALLOWED_DIRECTORIES_HOST", []):
            merged["ALLOWED_DIRECTORIES_HOST"] = merged.get("ALLOWED_DIRECTORIES_HOST", []) + [
                host_root
            ]
        if merged.get("ALLOWED_DIRECTORIES_DOCKER") is None and work_dir:
            merged["ALLOWED_DIRECTORIES_DOCKER"] = [work_dir]
        elif work_dir and work_dir not in merged.get("ALLOWED_DIRECTORIES_DOCKER", []):
            merged["ALLOWED_DIRECTORIES_DOCKER"] = merged.get("ALLOWED_DIRECTORIES_DOCKER", []) + [
                work_dir
            ]
        settings = cls(**merged)
        cls._validate_trusted_commands_against_shells(settings)
        return settings

    @staticmethod
    def _validate_trusted_commands_against_shells(settings: "Settings") -> None:
        for name, spec in settings.TRUSTED_COMMANDS.items():
            shell_name = spec.get("shell")
            if not shell_name or shell_name not in settings.ALLOWED_SHELLS:
                allowed = ", ".join(sorted(settings.ALLOWED_SHELLS.keys()))
                raise ValueError(
                    f"Trusted command '{name}' uses invalid shell '{shell_name}'. "
                    f"Allowed shells: {allowed}"
                )


SETTINGS: Settings | None = None
