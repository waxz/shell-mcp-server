"""Tests for shared path normalization helpers."""

from __future__ import annotations

from shell_mcp_server.path_utils import (
    normalize_directory_value,
    normalize_posix_path,
    normalize_windows_path_text,
)


def test_normalize_posix_path_collapses_repeated_separators_and_parent_segments():
    assert str(normalize_posix_path("/tmp///a/../b")) == "/tmp/b"


def test_normalize_windows_path_text_handles_unc_and_casefold():
    upper = normalize_windows_path_text(r"\\SERVER\Share\Folder\\")
    lower = normalize_windows_path_text(r"\\server\share\folder")
    assert upper == lower


def test_normalize_directory_value_keeps_windows_drive_format():
    assert normalize_directory_value(r"C:/Users/axdev/dev//") == r"C:\Users\axdev\dev"


def test_normalize_directory_value_handles_repeated_posix_separators():
    assert normalize_directory_value("/tmp///a//") == "/tmp/a"
