"""Tests for settings merge and validation contract."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from shell_mcp_server.config import Settings


def test_settings_cli_shells_override_config(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "COMMAND_TIMEOUT = 60",
                "[ALLOWED_SHELLS]",
                'bash = "/bin/false"',
            ]
        ),
        encoding="utf-8",
    )

    args = Namespace(
        directories=[str(tmp_path)],
        shell=[("bash", "/bin/bash")],
        transport=None,
        host=None,
        port=None,
        path=None,
        config=str(config_path),
    )

    settings = Settings.from_runtime(
        args=args,
        parsed_shells={"bash": "/bin/bash"},
        shells_from_cli=True,
    )

    assert settings.ALLOWED_SHELLS["bash"] == "/bin/bash"
    assert settings.COMMAND_TIMEOUT == 60


def test_settings_uses_config_shells_when_cli_not_set(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "COMMAND_TIMEOUT = 25",
                "[ALLOWED_SHELLS]",
                'bash = "/bin/sh"',
            ]
        ),
        encoding="utf-8",
    )

    args = Namespace(
        directories=[str(tmp_path)],
        shell=None,
        transport=None,
        host=None,
        port=None,
        path=None,
        config=str(config_path),
    )

    settings = Settings.from_runtime(
        args=args,
        parsed_shells={},
        shells_from_cli=False,
    )

    assert settings.ALLOWED_SHELLS["bash"] == "/bin/sh"
    assert settings.COMMAND_TIMEOUT == 25


def test_settings_default_allowed_directory_when_not_provided(tmp_path: Path):
    args = Namespace(
        directories=None,
        shell=None,
        transport=None,
        host=None,
        port=None,
        path=None,
        config=str(tmp_path / "missing.toml"),
    )
    Settings.from_runtime(args=args, parsed_shells={}, shells_from_cli=False)


def test_settings_rejects_trusted_command_with_invalid_shell(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[TRUSTED_COMMANDS.bad_cmd]",
                'command = "echo bad"',
                'shell = "powershell"',
                f'cwd = "{tmp_path.as_posix()}"',
            ]
        ),
        encoding="utf-8",
    )

    args = Namespace(
        directories=[str(tmp_path)],
        shell=None,
        transport=None,
        host=None,
        port=None,
        path=None,
        config=str(config_path),
    )

    try:
        Settings.from_runtime(args=args, parsed_shells={}, shells_from_cli=False)
    except ValueError as exc:
        assert "Trusted command 'bad_cmd' uses invalid shell" in str(exc)
    else:
        raise AssertionError("Expected trusted command shell validation to fail")


def test_settings_rejects_invalid_port():
    with pytest.raises(ValueError, match="PORT must be in range 1..65535"):
        Settings(PORT=70000)


def test_settings_rejects_invalid_http_path():
    with pytest.raises(ValueError, match="PATH must start with '/'"):
        Settings(PATH="mcp")


def test_settings_rejects_missing_docker_settings_when_enabled():
    with pytest.raises(ValueError, match="DOCKER_SHELL_COMPOSE_FILE is required"):
        Settings(
            UNTRUSTED_USE_DOCKER_SANDBOX=True,
            DOCKER_SHELL_COMPOSE_FILE=None,
            DOCKER_SHELL_SERVICE=None,
            DOCKER_SANDBOX_WORKDIR=None,
        )


def test_settings_rejects_posix_platform_with_windows_shell_in_trusted_command():
    with pytest.raises(ValueError, match="not POSIX-compatible"):
        Settings(
            PLATFORM="linux",
            ALLOWED_SHELLS={"pwsh": "powershell.exe"},
            TRUSTED_COMMANDS={
                "bad": {"command": "echo bad", "cwd": ".", "shell": "pwsh"},
            },
        )


def test_settings_rejects_windows_platform_with_posix_shell_in_trusted_command():
    with pytest.raises(ValueError, match="not Windows-compatible"):
        Settings(
            PLATFORM="windows",
            ALLOWED_SHELLS={"bash": "/bin/bash"},
            TRUSTED_COMMANDS={
                "bad": {"command": "echo bad", "cwd": ".", "shell": "bash"},
            },
        )
