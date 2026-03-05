import os
import sys
import signal
import asyncio
import subprocess as _subprocess
from contextlib import suppress
from typing import Optional, Callable, Awaitable, Dict, Any, List

import mcp.types as types
from fastmcp import Context

from . import config

# ── Module-level process tracking (for server-shutdown cleanup) ──
running_processes: Dict[int, asyncio.subprocess.Process] = {}


def is_subpath(path, allowed_dirs):
    real = os.path.realpath(path)
    for allowed in allowed_dirs:
        allowed_real = os.path.realpath(allowed)
        if os.path.commonpath([real, allowed_real]) == allowed_real:
            return True
    return False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Cross-platform process-tree killer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


try:
    from anyio import ClosedResourceError, BrokenResourceError
except ImportError:
    # Fallback if anyio isn't directly importable
    ClosedResourceError = OSError
    BrokenResourceError = OSError

# ── Exceptions that mean "client is gone" ─────────────────
_DISCONNECTED_ERRORS = (
    ClosedResourceError,
    BrokenResourceError,
    ConnectionError,
    BrokenPipeError,
    EOFError,
)






# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Cross-platform process-tree killer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _terminate_process(proc: asyncio.subprocess.Process):
    """Kill a process and all its descendants."""
    if proc.returncode is not None:
        return

    pid = proc.pid
    try:
        if config.SETTINGS.PLATFORM == "windows":
            k = await asyncio.create_subprocess_exec(
                "taskkill", "/F", "/T", "/PID", str(pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(k.wait(), timeout=5.0)
        else:
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

            try:
                await asyncio.wait_for(proc.wait(), timeout=3.0)
                return
            except asyncio.TimeoutError:
                pass

            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    except (ProcessLookupError, PermissionError):
        pass
    except Exception:
        with suppress(ProcessLookupError):
            proc.kill()

    with suppress(Exception):
        await asyncio.wait_for(proc.wait(), timeout=2.0)



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Main runner
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_shell_command(
    command: str,
    cwd: str,
    shell: str = "bash",
    on_stdout: Optional[Callable[[str], Awaitable[None]]] = None,
    on_stderr: Optional[Callable[[str], Awaitable[None]]] = None,
) -> Dict[str, Any]:
    """Execute a shell command, streaming output via callbacks."""

    absolute_cwd = os.path.realpath(os.path.abspath(cwd))

    if not is_subpath(absolute_cwd, config.SETTINGS.ALLOWED_DIRECTORIES):
        raise ValueError("Directory not allowed")

    if shell not in config.SETTINGS.ALLOWED_SHELLS:
        raise ValueError(
            f"Shell '{shell}' is not allowed. "
            f"Available: {list(config.SETTINGS.ALLOWED_SHELLS.keys())}"
        )

    # force bash in safety mode,
    # this is to prevent running commands in the shell
    # on windows , shell default runs in docker bash
    # only trusted shell can run in powershell
    # on linux and macos, shell runs in bash
    if config.SETTINGS.SAFETY_MODE == "strict":
        shell = "bash"

    if command in config.SETTINGS.TRUSTED_COMMANDS:
        cmd_cfg = config.SETTINGS.TRUSTED_COMMANDS[command]
        command = cmd_cfg.get("command", False)
        cwd = cmd_cfg.get("cwd", False)
        shell = cmd_cfg.get("shell", False)
        if not (command and cwd and shell):
            raise ValueError(f"Incomplete config for '{command}'")

    shell_path = config.SETTINGS.ALLOWED_SHELLS[shell]

    # ── Build shell invocation ────────────────────────────────
    if config.SETTINGS.PLATFORM == "windows":
        if shell in ("wsl"):
            shell_cmd = [
                shell_path, "--cd", absolute_cwd,
                "bash", "-c", command,
            ]
        
        elif shell_path.endswith("powershell.exe") or shell in ("bash","powershell"):
            
            # run shell in docker container
            if shell == "bash":
                # command = f'. $PROFILE; drun "{command}"'
                command = f'drun "{command}"'

            ps = (
                "$FormatEnumerationLimit=-1; "
                "[Console]::OutputEncoding="
                "[System.Text.Encoding]::UTF8; "
                f"& {{ {command} }} | Out-String -Stream -Width 4096 | "
                "ForEach-Object { $_.TrimEnd() } | "
                "Where-Object { $_ -ne '' }"
            )

            shell_cmd = [
                shell_path, #"-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-Command", ps,
            ]
        elif shell == "cmd":
            shell_cmd = [shell_path, "/c", command]
        else:
            shell_cmd = [shell_path, "-Command", command]
    elif config.SETTINGS.PLATFORM == "linux":
        shell_cmd = [shell_path, "-c", command]
    elif config.SETTINGS.PLATFORM == "macos":
        shell_cmd = [shell_path, "-c", command]
            

    # ── Spawn with own process group ──────────────────────────
    spawn_kw: Dict[str, Any] = dict(
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=absolute_cwd,
    )
    if config.SETTINGS.PLATFORM == "windows":
        spawn_kw["creationflags"] = _subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        spawn_kw["start_new_session"] = True

    process: Optional[asyncio.subprocess.Process] = None
    try:
        process = await asyncio.create_subprocess_exec(
            *shell_cmd, **spawn_kw,
        )
    except Exception as e:
        return dict(
            stdout="", stderr=f"Failed to start: {e}",
            exit_code=-1, command=command, shell=shell,
            cwd=absolute_cwd, timed_out=False,
            cancelled=False, pid=None,
        )

    running_processes[process.pid] = process

    cancel = asyncio.Event()
    stdout_lines: List[str] = []
    stderr_lines: List[str] = []
    timed_out = False
    client_disconnected = False

    # ── FIX 1: Callback wrapper that detects disconnect ───────
    #
    #    ctx.info() may succeed even after DELETE because of
    #    buffering.  We catch the SPECIFIC anyio errors that
    #    mean "the other end is gone", plus we test the stream
    #    with a secondary probe.

    async def _safe_callback(
        cb: Optional[Callable[[str], Awaitable[None]]],
        line: str,
    ) -> bool:
        """
        Call `cb(line)`.  Returns True if delivered, False if
        client is gone (sets cancel + client_disconnected).
        """
        nonlocal client_disconnected
        if cb is None:
            return True
        try:
            await cb(line)
            return True
        except _DISCONNECTED_ERRORS:
            client_disconnected = True
            cancel.set()
            return False
        except asyncio.CancelledError:
            client_disconnected = True
            cancel.set()
            raise
        except Exception:
            # Unknown error — treat as disconnect to be safe
            client_disconnected = True
            cancel.set()
            return False

    # ── Stream reader ─────────────────────────────────────────
    async def _read(
        stream: asyncio.StreamReader,
        buf: List[str],
        cb: Optional[Callable[[str], Awaitable[None]]],
    ):
        partial = ""
        while not cancel.is_set():
            chunk = await stream.read(8192)
            if not chunk:
                if partial:
                    buf.append(partial)
                    await _safe_callback(cb, partial)
                break

            text = partial + chunk.decode("utf-8", errors="replace")
            *lines, partial = text.split("\n")

            for line in lines:
                if cancel.is_set():
                    return
                cleaned = line.rstrip("\r")
                buf.append(cleaned)
                if not await _safe_callback(cb, cleaned):
                    return                     # client gone → stop reading

    # ── Background killer ─────────────────────────────────────
    async def _auto_kill():
        await cancel.wait()
        await _terminate_process(process)

    kill_task = asyncio.create_task(_auto_kill())

    # ── Run readers under timeout ─────────────────────────────
    try:
        await asyncio.wait_for(
            asyncio.gather(
                _read(process.stdout, stdout_lines, on_stdout),
                _read(process.stderr, stderr_lines, on_stderr),
            ),
            timeout=config.SETTINGS.COMMAND_TIMEOUT,
        )
    except asyncio.TimeoutError:
        timed_out = True
        cancel.set()
    except asyncio.CancelledError:
        cancel.set()
        with suppress(Exception):
            await asyncio.wait_for(kill_task, timeout=10.0)
        running_processes.pop(process.pid, None)
        raise
    except Exception:
        cancel.set()
    finally:
        cancel.set()
        try:
            await asyncio.wait_for(kill_task, timeout=10.0)
        except asyncio.TimeoutError:
            kill_task.cancel()
            with suppress(asyncio.CancelledError):
                await kill_task
            with suppress(Exception):
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=2.0)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    with suppress(Exception):
        await asyncio.wait_for(process.wait(), timeout=2.0)

    running_processes.pop(process.pid, None)

    stderr_text = "\n".join(stderr_lines)
    if timed_out:
        stderr_text = (
            f"{stderr_text}\n"
            f"[Timed out after {config.SETTINGS.COMMAND_TIMEOUT}s]"
        ).strip()
    if client_disconnected:
        stderr_text = (
            f"{stderr_text}\n"
            f"[Client disconnected — process killed]"
        ).strip()

    return dict(
        stdout="\n".join(stdout_lines),
        stderr=stderr_text,
        exit_code=(
            process.returncode
            if process.returncode is not None
            else -1
        ),
        command=command,
        shell=shell,
        cwd=absolute_cwd,
        timed_out=timed_out,
        cancelled=client_disconnected,
        pid=process.pid,
    )