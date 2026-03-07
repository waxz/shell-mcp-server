"""Test fixtures for shell-mcp-server."""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture
def runtime_settings(tmp_path: Path):
    """Initialize global runtime settings for execution tests."""
    from shell_mcp_server import config

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    args = Namespace(
        directories=[str(project_dir)],
        shell=None,
        transport=None,
        host=None,
        port=None,
        path=None,
        config=str(tmp_path / "missing-config.toml"),
    )

    settings = config.Settings.from_runtime(
        args=args,
        parsed_shells={"bash": "/bin/bash", "sh": "/bin/sh"},
        shells_from_cli=True,
    )
    settings.UNTRUSTED_USE_DOCKER_SANDBOX = False
    config.SETTINGS = settings

    yield settings

    config.SETTINGS = None
