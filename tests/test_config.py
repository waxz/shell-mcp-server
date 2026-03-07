"""Tests for settings merge and validation contract."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

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
    settings = Settings.from_runtime(args=args, parsed_shells={}, shells_from_cli=False)
    assert isinstance(settings.ALLOWED_DIRECTORIES, list)
    assert len(settings.ALLOWED_DIRECTORIES) == 1


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
