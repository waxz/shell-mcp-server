"""Configuration loading and validation for shell MCP server."""

from __future__ import annotations

import os
import platform
from argparse import Namespace
from pathlib import Path
from typing import Any,Dict

import toml
from pydantic import ConfigDict, field_validator
from pydantic_settings import BaseSettings


def _default_shells(system_name: str) -> dict[str, str]:
    if system_name == "windows":
        return {
            "bash": "powershell.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "wsl": "wsl.exe",
        }
    return {"bash": "/bin/bash", "sh": "/bin/sh"}


def _is_wsl() -> bool:
    release = platform.release().lower()
    version = platform.version().lower()
    return "microsoft" in release or "microsoft" in version


class Settings(BaseSettings):
    """Application runtime settings."""

    APP_NAME: str = "shell-mcp-server"
    APP_VERSION: str = "0.1.3"
    COMMAND_TIMEOUT: int = 30
    ALLOWED_DIRECTORIES: list[str] = []
    TRUSTED_COMMANDS: dict[str, dict[str, str]] = {}
    ALLOWED_SHELLS: dict[str, str] = {}
    SAFETY_MODE: str = "strict"
    TRANSPORT: str = "stdio"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    PATH: str = "/mcp"
    PLATFORM: str = "linux"

    ALLOWED_DIRECTORIES_HOST: list[str]| None = None
    ALLOWED_DIRECTORIES_DOCKER: list[str] | None = None


    DOCKER_CONFIG:Dict[str, Any] = {}
    DOCKER_SHELL_COMPOSE_FILE: str | None = None
    DOCKER_SHELL_SERVICE: str | None =None
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

    @field_validator("TRANSPORT")
    @classmethod
    def _validate_transport(cls, value: str) -> str:
        if value not in {"stdio", "http"}:
            raise ValueError("TRANSPORT must be 'stdio' or 'http'")
        return value

    @field_validator("ALLOWED_DIRECTORIES")
    @classmethod
    def _normalize_allowed_dirs(cls, value: list[str]) -> list[str]:
        return [str(Path(path).resolve()) for path in value]

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
            "DOCKER_SHELL_COMPOSE_FILE" : None,
        }

        config_path = Path(getattr(args, "config", "config.toml") or "config.toml")
        if config_path.exists():
            file_config = toml.load(config_path)
            merged.update(file_config)

        if shells_from_cli:
            merged["ALLOWED_SHELLS"] = parsed_shells
        elif not merged.get("ALLOWED_SHELLS"):
            merged["ALLOWED_SHELLS"] = parsed_shells

        if getattr(args, "directories", None):
            merged["ALLOWED_DIRECTORIES"] = [
                str(Path(path).resolve()) for path in args.directories
            ]

        if getattr(args, "transport", None):
            merged["TRANSPORT"] = args.transport
        if getattr(args, "host", None):
            merged["HOST"] = args.host
        if getattr(args, "port", None):
            merged["PORT"] = args.port
        if args.path:
            merged["PATH"] = args.path
        
        print("merged", merged)
        print("args", args)


        if not merged.get("ALLOWED_DIRECTORIES"):
            merged["ALLOWED_DIRECTORIES"] = [str(Path(".").resolve())]

        merged["DOCKER_SHELL_COMPOSE_FILE"] = merged.get("DOCKER_CONFIG", {}).get("config_file")
        merged["DOCKER_SHELL_SERVICE"] = merged.get("DOCKER_CONFIG", {}).get("service")
        merged["DOCKER_SHELL_ENV_FILE"] = merged.get("DOCKER_CONFIG", {}).get("env_file")

        if platform_name == "linux":
            merged["DOCKER_SANDBOX_HOST_ROOT"] = merged["DOCKER_CONFIG"].get("linux",{}).get("host_root", None)
            merged["DOCKER_SANDBOX_WORKDIR"] =  merged["DOCKER_CONFIG"].get("linux",{}).get("work_dir", None)
            merged["ALLOWED_DIRECTORIES_HOST"] =  merged["DOCKER_CONFIG"].get("linux",{}).get("allow_direcotories_host", None)
            merged["ALLOWED_DIRECTORIES_DOCKER"] =  merged["DOCKER_CONFIG"].get("linux",{}).get("allow_direcotories_docker", None)
            
            
        elif platform_name == "windows":
            merged["DOCKER_SANDBOX_HOST_ROOT"] = merged["DOCKER_CONFIG"].get("windows",{}).get("host_root", None)
            merged["DOCKER_SANDBOX_WORKDIR"] = merged["DOCKER_CONFIG"].get("windows",{}).get("work_dir", None)
            merged["ALLOWED_DIRECTORIES_HOST"] =  merged["DOCKER_CONFIG"].get("windows",{}).get("allow_direcotories_host", None)
            merged["ALLOWED_DIRECTORIES_DOCKER"] =  merged["DOCKER_CONFIG"].get("windows",{}).get("allow_direcotories_docker", None)
            
        print("final merged", merged)
        
        settings = cls(**merged)
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
