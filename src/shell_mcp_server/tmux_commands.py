"""Safe tmux command builders."""

from __future__ import annotations

import shlex

from .execution_policy import validate_tmux_session_name


def _sanitize_value(value: str, field_name: str) -> str:
    if "\x00" in value:
        raise ValueError(f"Invalid {field_name}: null byte is not allowed")
    # if "\n" in value or "\r" in value:
    #     raise ValueError(f"Invalid {field_name}: multiline input is not allowed")
    return value


def build_tmux_bootstrap_command(session_name: str) -> str:
    session = shlex.quote(validate_tmux_session_name(session_name))
    return f"tmux new-session -s {session} -d"
    # return (
    #     f"tmux has-session -t {session} 2>/dev/null || "
    #     f"tmux new-session -s {session} -d bash"
    # )


def build_tmux_send_keys_command(session_name: str, command: str) -> str:
    session = shlex.quote(validate_tmux_session_name(session_name))
    safe_command = shlex.quote(_sanitize_value(command, "command"))
    return f"tmux send-keys -t {session} {safe_command} Enter"


def build_tmux_reset_pane_command(session_name: str) -> [str]:
    """Reset pane state so captures do not include stale buffered output."""
    session = shlex.quote(validate_tmux_session_name(session_name))
    return [
        f"tmux send-keys -t {session} C-c Enter",
        f"tmux send-keys -t {session} clear Enter",
        f"tmux clear-history -t {session}"
    ]


def build_tmux_capture_command(session_name: str) -> str:
    session = shlex.quote(validate_tmux_session_name(session_name))
    return f"tmux capture-pane -t {session} -p"


def build_tmux_clear_command(session_name: str) -> str:
    session = shlex.quote(validate_tmux_session_name(session_name))
    return f"tmux send-keys -t {session} clear Enter"


def build_tmux_kill_command(session_name: str) -> str:
    session = shlex.quote(validate_tmux_session_name(session_name))
    return f"tmux kill-session -t {session}"
