"""Integration test runner for shell-mcp-server tools.

Usage:
  python ./test.py
  python ./test.py --transport http --url http://localhost:8000/mcp
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastmcp import Client

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@dataclass
class Scenario:
    tool: str
    args: dict[str, Any]
    expect_error: bool = False
    must_contain: str | None = None
    callback : Any | None = None


@dataclass
class ScenarioResult:
    scenario: Scenario
    passed: bool
    output: str = ""
    error: str = ""
    detail: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Shell MCP Server integration tester")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Client transport target",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000/mcp",
        help="HTTP MCP endpoint when --transport=http",
    )
    parser.add_argument(
        "--cwd",
        default=".",
        help="Working directory for execute_command scenarios",
    )
    parser.add_argument(
        "--shell",
        default="bash",
        help="Shell name for execute_command scenarios",
    )
    parser.add_argument(
        "--report",
        default="report.txt",
        help="Output report path",
    )
    return parser.parse_args()


def build_client(args) -> Client:

    transport = args.transport
    url = args.url


    from shell_mcp_server.server import build_server
    from shell_mcp_server.mcp_utils import  parse_args
    from shell_mcp_server import config


    old_argv = sys.argv[:]
    try:
        sys.argv = [sys.argv[0]]
        # server = build_server()
        args, shells, shells_from_cli = parse_args()

        config.SETTINGS = config.Settings.from_runtime(args, shells, shells_from_cli)

        server = build_server(config.SETTINGS)
    finally:
        sys.argv = old_argv
    return Client(server)


def extract_text(result: Any) -> str:
    parts: list[str] = []
    for content in getattr(result, "content", []):
        text = getattr(content, "text", "")
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _truncate(value: str, limit: int = 72) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _scenario_label(scenario: Scenario) -> str:
    command = scenario.args.get("command")
    if isinstance(command, str) and command:
        return _truncate(_one_line(command))
    return "-"


def _looks_like_error_output(output: str) -> bool:
    text = output.strip()
    if text.startswith("Execution failed:"):
        return True
    if "[timed out after " in text:
        return True
    if "[client disconnected]" in text:
        return True
    if "[exit code:" in text:
        tail = text.rsplit("[exit code:", maxsplit=1)[-1]
        code_text = tail.split("]", maxsplit=1)[0].strip()
        try:
            return int(code_text) != 0
        except ValueError:
            return False
    return False


def _row(columns: list[tuple[str, int]]) -> str:
    parts: list[str] = []
    for text, width in columns:
        parts.append(text.ljust(width)[:width])
    return " | ".join(parts)


async def call_tool(client: Client, scenario: Scenario) -> ScenarioResult:
    label = f"{scenario.tool}({json.dumps(scenario.args, ensure_ascii=False)})"
    print(f"\n=== {label}")

    try:
        result = await client.call_tool(scenario.tool, scenario.args)
        output = extract_text(result)
        print(f"OUTPUT>>>>>\n{output}\n>>>>",)

        if scenario.callback:
            scenario.callback(result)

        if scenario.expect_error:
            if _looks_like_error_output(output):
                print(f"EXPECTED ERROR: {output}")
                return ScenarioResult(
                    scenario=scenario,
                    passed=True,
                    output=output,
                    detail="expected error matched tool error output",
                )
            print("FAILED: expected an error but call succeeded")
            print("OUTPUT> ",output)
            return ScenarioResult(
                scenario=scenario,
                passed=False,
                output=output,
                detail="expected error but call succeeded",
            )

        if scenario.must_contain and scenario.must_contain not in output:
            print(f"FAILED: expected output to contain: {scenario.must_contain!r}")
            print("OUTPUT> ",output or "<empty>")
            return ScenarioResult(
                scenario=scenario,
                passed=False,
                output=output,
                detail=f"missing expected substring: {scenario.must_contain!r}",
            )

        if "No such file or directory" in output:
            print("FAILED: unexpected path resolution error")
            print("OUTPUT> ",output)
            return ScenarioResult(
                scenario=scenario,
                passed=False,
                output=output,
                detail="unexpected path resolution error",
            )

        print("OUTPUT> ",output or "<empty>")
        return ScenarioResult(scenario=scenario, passed=True, output=output)
    except Exception as exc:  # noqa: BLE001
        if scenario.expect_error:
            print(f"EXPECTED ERROR: {exc}")
            return ScenarioResult(
                scenario=scenario,
                passed=True,
                error=str(exc),
                detail="expected exception raised",
            )
        print(f"FAILED: {exc}")
        return ScenarioResult(
            scenario=scenario,
            passed=False,
            error=str(exc),
            detail="unexpected exception",
        )


def write_report(
    report_path: Path,
    args: argparse.Namespace,
    results: list[ScenarioResult],
) -> None:
    passed = sum(1 for item in results if item.passed)
    total = len(results)
    failed = [item for item in results if not item.passed]

    lines: list[str] = []
    lines.append("Shell MCP Server Test Report")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Host OS: {platform.platform()}")
    lines.append(f"Host System: {platform.system()} {platform.release()}")
    lines.append(f"Host Machine: {platform.machine()}")
    lines.append(f"Host CPU: {platform.processor() or 'unknown'}")
    lines.append(f"CPU Cores (logical): {os.cpu_count()}")
    lines.append(f"Memory Total: {_get_memory_total_human()}")
    lines.append(f"Python: {platform.python_version()}")
    lines.append(f"Transport: {args.transport}")
    lines.append(f"CWD arg: {args.cwd}")
    lines.append(f"Shell arg: {args.shell}")
    lines.append(f"Summary: {passed}/{total} scenarios passed")
    lines.append("")

    lines.append("Result Table")
    lines.append("=" * 78)
    lines.append(
        _row(
            [
                ("#", 3),
                ("Status", 6),
                ("Tool", 18),
                ("Check", 24),
                ("Case", 22),
            ]
        )
    )
    lines.append("-" * 78)
    for idx, item in enumerate(results, start=1):
        scenario = item.scenario
        if scenario.expect_error:
            check = "expect error"
        elif scenario.must_contain:
            check = _truncate(f"contains: {scenario.must_contain}", 24)
        else:
            check = "normal"
        lines.append(
            _row(
                [
                    (str(idx), 3),
                    ("PASS" if item.passed else "FAIL", 6),
                    (scenario.tool, 18),
                    (check, 24),
                    (_scenario_label(scenario), 22),
                ]
            )
        )
    lines.append("=" * 78)
    lines.append("")

    lines.append(f"Failed Scenarios: {len(failed)}")
    if failed:
        lines.append("-" * 78)
        for item in failed:
            scenario = item.scenario
            lines.append(f"Tool: {scenario.tool}")
            lines.append(f"Args: {json.dumps(scenario.args, ensure_ascii=False)}")
            if scenario.must_contain:
                lines.append(f"Expected contain: {scenario.must_contain}")
            if scenario.expect_error:
                lines.append("Expected error: True")
            if item.detail:
                lines.append(f"Detail: {item.detail}")
            if item.error:
                lines.append(f"Error: {item.error}")
            if item.output:
                lines.append("Actual output:")
                lines.append(item.output)
            lines.append("-" * 78)
    lines.append("")

    lines.append("Detailed Results")
    lines.append("=" * 78)

    for idx, item in enumerate(results, start=1):
        scenario = item.scenario
        status = "PASS" if item.passed else "FAIL"
        lines.append(f"[{idx}] {status} {scenario.tool}")
        lines.append(f"Args: {json.dumps(scenario.args, ensure_ascii=False)}")
        lines.append(f"Expect error: {scenario.expect_error}")
        if scenario.must_contain:
            lines.append(f"Must contain: {scenario.must_contain}")
        if item.detail:
            lines.append(f"Detail: {item.detail}")
        if item.error:
            lines.append(f"Error: {item.error}")
        if item.output:
            lines.append("Output:")
            lines.append(item.output)
        lines.append("-" * 78)

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _get_memory_total_human() -> str:
    """Best-effort total memory detection with stdlib fallbacks."""
    # Linux / WSL
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        try:
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    # Format: MemTotal:  32895332 kB
                    kb = int(line.split()[1])
                    return _format_bytes(kb * 1024)
        except Exception:  # noqa: BLE001
            pass

    # Optional psutil fallback if available in environment.
    try:
        import psutil  # type: ignore

        return _format_bytes(int(psutil.virtual_memory().total))
    except Exception:  # noqa: BLE001
        return "unknown"


def _format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{value} B"


def _is_wsl_runtime() -> bool:
    if platform.system().lower() != "linux":
        return False
    release = platform.release().lower()
    version = platform.version().lower()
    return "microsoft" in release or "microsoft" in version


def _expected_sandbox_base() -> str:
    if platform.system().lower().startswith("win"):
        return "/app"
    if _is_wsl_runtime():
        return str(PROJECT_ROOT)
    return "/workspace"


# Keep this as a raw multiline bash script, then normalize to LF for Windows drun.
human_like_python_project_cmd = r"""
set -e
proj=".mcp_human_py"

rm -rf "$proj" && mkdir -p "$proj"

# Avoid single quotes in payload to keep PowerShell -> drun -> bash quoting stable.
echo "import toml,time" > "$proj/main.py"

echo "data={\"status\": \"success\", \"msg\": \"hello from app\"}" >> "$proj/main.py"
echo "print(f'data: {data}')" >> "$proj/main.py"
echo "print(toml.dumps(data))" >> "$proj/main.py"

echo "print('sleep 2')" >> "$proj/main.py"

echo "time.sleep(2)" >> "$proj/main.py"


echo "print('sleep 3')" >> "$proj/main.py"

echo "time.sleep(3)" >> "$proj/main.py"


echo "print('sleep 1')" >> "$proj/main.py"

echo "time.sleep(1)" >> "$proj/main.py"


echo "print('sleep 2')" >> "$proj/main.py"

echo "time.sleep(2)" >> "$proj/main.py"

echo "toml" > "$proj/requirements.txt"

uv pip install -r "$proj/requirements.txt"
python3 "$proj/main.py"
""".replace("\r\n", "\n").strip()

tmux_session = {}


async def run_scenarios(args: argparse.Namespace) -> int:
    client = build_client(args)
    # f = lambda x : print(f"callback: >>>>\n {x} \n>>>> done")
    scenarios = [
        
        Scenario(
            "execute_command",
            {
                "command": "pwd",
                "cwd": ".",
                "shell": args.shell,
            },
            # callback = f
        ),
        Scenario(
            "execute_command",
            {
                "command": "pwd",
                "cwd": "./data",
                "shell": args.shell,
            },
            
            must_contain="data",
        ),
        Scenario(
            "execute_command",
            {
                "command": "trusted_pwd",
                "cwd": ".",
                "shell": args.shell,
            },
        ),
        
        Scenario(
            "execute_command",
            {
                "command": "echo hello-from-test",
                "cwd": args.cwd,
                "shell": args.shell,
            },
        ),
        
        Scenario(
            "execute_command",
            {
                "command": "not_exist_cmd build",
                "cwd": args.cwd,
                "shell": args.shell,
            },
        ),
        
        Scenario(
            "execute_command",
            {
                "command": "echo very_long_sleep && sleep 25 && echo very_long_sleep_done",
                "cwd": args.cwd,
                "shell": args.shell,
            },
            must_contain="very_long_sleep_done",
        ),
        Scenario(
            "execute_command",
            {
                "command": "echo very_long_sleep && sleep 35 && echo very_long_sleep_done",
                "cwd": args.cwd,
                "shell": args.shell,
            },
            expect_error=True,
        ),        
        Scenario(
            "execute_command",
            {
                "command": "echo Hello 世界 ✓",
                "cwd": args.cwd,
                "shell": args.shell,
            },
            must_contain="Hello 世界 ✓",
        ),
        Scenario(
            "execute_command",
            {
                "command": "echo a\\&b\\|c\\;d",
                "cwd": args.cwd,
                "shell": args.shell,
            },
            must_contain="a&b|c;d",
        ),
        Scenario(
            "execute_command",
            {
                "command": human_like_python_project_cmd,
                "cwd": args.cwd,
                "shell": args.shell,
            },
            must_contain="hello from app",
        ),
        Scenario(
            "execute_command",
            {
                "command": "pwd",
                "cwd": args.cwd,
                "shell": args.shell,
            },
        ),
        Scenario(
            "execute_command",
            {
                "command": "trusted_pwd",
                "cwd": args.cwd,
                "shell": args.shell,
            }
        ),
        Scenario("list_processes", {}),
        Scenario("terminate_all_processes", {}),
        Scenario(
            "execute_command",
            {
                "command": "echo should-fail",
                "cwd": "/",
                "shell": args.shell,
            },
            expect_error=True,
        ),
        Scenario(
            "execute_command",
            {
                "command": "echo should-fail-etc",
                "cwd": "/etc",
                "shell": args.shell,
            },
            expect_error=True,
        ),
        Scenario(
            "execute_command",
            {
                "command": "echo traversal",
                "cwd": "../",
                "shell": args.shell,
            },
            expect_error=True,
        ),
        Scenario(
            "execute_command",
            {
                "command": "echo deep-traversal",
                "cwd": "../../../../",
                "shell": args.shell,
            },
            expect_error=True,
        ),
        Scenario(
            "execute_command",
            {
                "command": "echo multiline-path",
                "cwd": "./\n/tmp",
                "shell": args.shell,
            },
            expect_error=True,
        ),
        Scenario(
            "execute_command",
            {
                "command": "echo null-byte-path",
                "cwd": "./\x00/tmp",
                "shell": args.shell,
            },
            expect_error=True,
        ),
        Scenario(
            "execute_command",
            {
                "command": "echo carriage-return-cmd\rwhoami",
                "cwd": args.cwd,
                "shell": args.shell,
            },
            expect_error=True,
        ),
        Scenario(
            "execute_command",
            {
                "command": "echo invalid-shell",
                "cwd": args.cwd,
                "shell": "bash;whoami",
            },
            expect_error=True,
        ),
    ]

    if platform.system().lower().startswith("win"):
        scenarios.append(
            Scenario(
                "execute_command",
                {
                    "command": "echo windows-backslash-traversal",
                    "cwd": ".\\..\\",
                    "shell": args.shell,
                },
                expect_error=True,
            )
        )
        scenarios.append(
            Scenario(
                "execute_command",
                {
                    "command": "echo windows-abs-path",
                    "cwd": r"C:\Windows\System32",
                    "shell": args.shell,
                },
                expect_error=True,
            )
        )

    results: list[ScenarioResult] = []
    async with client:
        tmux_available = True
        # try:
        #     probe = await client.call_tool(
        #         "execute_command",
        #         {"command": "tmux -V >/dev/null 2>&1; echo $?", "cwd": args.cwd, "shell": args.shell},
        #     )
        #     probe_text = extract_text(probe)
        #     tmux_available = "\n0\n" in f"\n{probe_text}\n"
        # except Exception:
        #     tmux_available = False

        if tmux_available:
            session_name = "mcp_test"
            def get_session_name(x):
                # global tmux_session
                tmux_session["session_name"] = json.loads(getattr(getattr(x,"content")[0], "text"))["session_name"] 
                print("tmux_session:",tmux_session)
            scenarios.extend(
                [
                    Scenario(
                        "tmux_execute",
                        {
                            "command": "pwd && echo tmux at 1 2 3 > log.txt && cat log.txt",
                            "shell": args.shell,
                        "session_name": session_name,

                        },

                        callback = get_session_name
                    ),
                    Scenario(
                        "tmux_get_output",
                        {
                            "session_name": session_name,
                            "shell": args.shell,
                        },
                    ),
                    Scenario(
                        "tmux_list_session",
                        {"shell": args.shell},
                    ),
                    Scenario(
                        "tmux_kill_session",
                        {
                            "session_name": session_name,
                            "shell": args.shell,
                        },
                    ),
                    Scenario(
                        "tmux_kill_session",
                        {
                            "session_name": "mcp_bad;rm-rf",
                            "shell": args.shell,
                        },
                        expect_error=True,
                    ),
                    Scenario(
                        "tmux_list_session",
                        {"shell": args.shell},
                    ),

                ]
            )
        else:
            print("\n[INFO] tmux not usable in current environment; skipping tmux tool scenarios")

        for scenario in scenarios:
            results.append(await call_tool(client, scenario))

    passed = sum(1 for item in results if item.passed)
    total = len(results)
    print(f"\nSummary: {passed}/{total} scenarios passed")
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = PROJECT_ROOT / report_path
    report_path = report_path.resolve()
    write_report(report_path=report_path, args=args, results=results)
    print(f"Report written: {report_path}")
    return 0 if passed == total else 1


def main() -> None:
    args = parse_args()
    exit_code = asyncio.run(run_scenarios(args))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
