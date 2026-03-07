"""Security tests for string-injection protection."""

from __future__ import annotations

import base64
import re
import shlex

from shell_mcp_server.platform_adapters.windows import build_windows_shell_command
from shell_mcp_server.tmux_commands import (
    build_tmux_bootstrap_command,
    build_tmux_send_keys_command,
)




def test_tmux_command_is_single_token_after_escaping():
    payload = "echo ok; touch /tmp/pwned"
    command = build_tmux_send_keys_command("mcp_test", payload)
    tokens = shlex.split(command)

    assert tokens[:4] == ["tmux", "send-keys", "-t", "mcp_test"]
    assert tokens[4] == payload
    assert tokens[5] == "Enter"


def test_tmux_bootstrap_path_escaped_as_single_token():
    command = build_tmux_bootstrap_command("mcp_test")

    right_side = command.split("||", maxsplit=1)[1].strip()
    tokens = shlex.split(right_side)
    assert tokens[:3] == ["tmux", "new-session", "-s"]
    assert "mcp_test" in tokens


def test_windows_bash_adapter_escapes_single_quotes():
    cmd = "echo 'hi'; whoami"
    built = build_windows_shell_command(
        shell="bash",
        shell_path="powershell.exe",
        command=cmd,
        cwd="C:/tmp",
    )

    assert built[0] == "powershell.exe"
    match = re.search(r'drun "echo ([A-Za-z0-9+/=]+) \| base64 -d \| bash"', built[-1])
    assert match is not None
    decoded = base64.b64decode(match.group(1)).decode("utf-8")
    assert "echo 'hi'; whoami" in decoded
