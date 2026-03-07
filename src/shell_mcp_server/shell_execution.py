"""Backward-compatible shell execution exports.

This module is kept as a compatibility shim while execution logic lives in
`executor.py` and policy logic lives in `execution_policy.py`.
"""

from .executor import (
    list_running_process_records,
    run_shell_command,
    running_processes,
    terminate_all_processes,
    terminate_process_by_pid,
)

__all__ = [
    "run_shell_command",
    "running_processes",
    "list_running_process_records",
    "terminate_process_by_pid",
    "terminate_all_processes",
]
