"""Server bootstrap and MCP tool registration."""

from __future__ import annotations

import argparse
import logging
import sys
from fastmcp import FastMCP

from . import config
from .tool_handlers import register_tools


def parse_args() -> tuple[argparse.Namespace, dict[str, str], bool]:
    """Parse CLI args and optional shell overrides."""
    parser = argparse.ArgumentParser(description="Shell MCP Server")
    parser.add_argument("-d", "--directories", nargs="+", help="Allowed directories")
    parser.add_argument(
        "--shell",
        action="append",
        nargs=2,
        metavar=("name", "path"),
        help="Shell mapping (name path)",
    )

    parser.add_argument(
        "-t",
        "--transport",
        type=str,
        choices=["stdio", "http"],
        default=None,
        help="Server transport override",
    )
    parser.add_argument("-H", "--host", type=str, default="0.0.0.0")
    parser.add_argument("-P", "--port", type=int, default="8000")
    parser.add_argument("-p", "--path", type=str, default="/mcp")
    parser.add_argument("-c", "--config", type=str, default="config.toml")

    args = parser.parse_args()
    shells_from_cli = bool(args.shell)
    shells = {name: path for name, path in (args.shell or [])}
    return args, shells, shells_from_cli


def build_server() -> FastMCP:
    """Initialize runtime settings and return configured FastMCP server."""
    args, shells, shells_from_cli = parse_args()
    config.SETTINGS = config.Settings.from_runtime(args, shells, shells_from_cli)

    app = FastMCP(config.SETTINGS.APP_NAME)
    register_tools(app)
    return app


def main() -> None:
    """Main entry point for running server with selected transport."""
    logging.getLogger("mcp.server.streamable_http_manager").setLevel(logging.INFO)
    logging.getLogger("mcp").setLevel(logging.INFO)
    logging.getLogger("fastmcp").setLevel(logging.INFO)
    logging.info("Starting server...")
    app = build_server()
    print(f"Settings: {config.SETTINGS}")    

    assert config.SETTINGS is not None

    # Suppress ClosedResourceError that happens when clients disconnect
    logging.getLogger("fastmcp").setLevel(logging.INFO)
    logging.getLogger("anyio").setLevel(logging.INFO)

    # Custom exception handler to suppress client disconnect errors
    old_excepthook = sys.excepthook

    def new_excepthook(exc_type, exc_value, exc_traceback):
        # Suppress ClosedResourceError from crashing the server
        if exc_type.__name__ == "ClosedResourceError":
            print(
                f"INFO: Client disconnected (ClosedResourceError suppressed)",
                file=sys.stderr,
            )
            return
        # Also suppress ExceptionGroup containing ClosedResourceError
        if exc_type.__name__ == "BaseExceptionGroup":
            if "unhandled errors" in str(exc_value):
                # Check if it's just ClosedResourceError
                for cause in exc_value.exceptions or []:
                    if "ClosedResourceError" in str(type(cause).__name__):
                        print(
                            f"INFO: Client disconnected (ExceptionGroup suppressed)",
                            file=sys.stderr,
                        )
                        return
        old_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = new_excepthook


    if config.SETTINGS.TRANSPORT == "http":
        app.run(
            transport="http",
            port=config.SETTINGS.PORT,
            host=config.SETTINGS.HOST,
            path=config.SETTINGS.PATH,
        )
        return

    app.run()


if __name__ == "__main__":
    main()
