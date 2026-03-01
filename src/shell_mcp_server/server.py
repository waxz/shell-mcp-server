"""
Shell MCP Server
==============

This module implements an MCP server that provides secure shell command execution
within specified working directories using specified shells.

Key Features:
- Safe command execution in specified directories
- Supports multiple shell types (bash, sh, cmd, powershell)
- Command timeout handling
- Cross-platform support
- Robust error handling
"""

import asyncio
import os
import sys
import argparse
from typing import Dict, Any, List
import mcp
import mcp.types as types
from mcp.server import Server, InitializationOptions, NotificationOptions

from fastmcp import FastMCP

from .config import Settings


# Parse command line arguments for directories and shells
def parse_args() -> tuple[List[str], Dict[str, str]]:
    """Parse command line arguments for directories and shells."""
    parser = argparse.ArgumentParser(description="Shell MCP Server")
    parser.add_argument('-d','--directories', nargs='+', help='Allowed directories for command execution')
    parser.add_argument('--shell', action='append', nargs=2, metavar=('name', 'path'),
                       help='Shell specification in format: name path')

    parser.add_argument('-t','--transport', type=str, default='stdio', choices=['stdio', 'http'])
    parser.add_argument('-H','--host', type=str, default='0.0.0.0')
    parser.add_argument('-P','--port', type=int, default=8000)
    parser.add_argument('-p','--path', type=str, default='/mcp')
    
    args = parser.parse_args()
    
    # Convert shell arguments to dictionary
    shells = {}
    if args.shell:
        shells = {name: path for name, path in args.shell}
    
    # Default to system shell if none specified
    if not shells:
        if sys.platform == 'win32':
            shells = {'bash': 'powershell.exe', 'cmd': 'cmd.exe', 'powershell': 'powershell.exe'}
        else:
            shells = {'bash': '/bin/bash', 'sh': '/bin/sh'}
    
    return args, shells


# Initialize server settings and create server instance - skip arg parsing for tests
if 'pytest' not in sys.modules:
    args, shells = parse_args()
    settings = Settings(args, shells=shells)
else:
    args = { 
        "directories": ['/tmp']
    }
    settings = Settings(args, shells={'bash': '/bin/bash'})

server = Server(settings.APP_NAME)
app_http: FastMCP = FastMCP(settings.APP_NAME)

async def run_shell_command( command: str, cwd: str,shell: str = "bash") -> Dict[str, Any]:
    """
    Execute a shell command safely and return its output.
    
    Args:
        shell (str): Name of the shell to use
        command (str): The command to execute
        cwd (str): Working directory for command execution
        
    Returns:
        Dict[str, Any]: Command execution results including stdout, stderr, and exit code
    """
    if not settings.is_path_allowed(cwd):
        raise ValueError(f"Directory '{cwd}' is not in the allowed directories list")
    
    if shell not in settings.ALLOWED_SHELLS:
        raise ValueError(f"Shell '{shell}' is not allowed. Available shells: {list(settings.ALLOWED_SHELLS.keys())}")
    
    shell_path = settings.ALLOWED_SHELLS[shell]
    
    try:
        if sys.platform == 'win32':
            shell_cmd = [shell_path, '/c', command] if shell == 'cmd' else [shell_path, '-Command', command]
        else:
            shell_cmd = [shell_path, '-c', command]

        process = await asyncio.create_subprocess_exec(
            *shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=settings.COMMAND_TIMEOUT
            )
            
            return {
                "stdout": stdout.decode() if stdout else "",
                "stderr": stderr.decode() if stderr else "",
                "exit_code": process.returncode,
                "command": command,
                "shell": shell,
                "cwd": cwd
            }

        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
            raise TimeoutError(f"Command execution timed out after {settings.COMMAND_TIMEOUT} seconds")

    except TimeoutError:
        raise
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "command": command,
            "shell": shell,
            "cwd": cwd
        }


@server.list_tools()
async def list_tools() -> List[types.Tool]:
    """List available shell tools."""
    return [
        types.Tool(
            name="execute_command",
            description="Execute a shell command in a specified directory using a specified shell",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute",
                    },
                    "shell": {
                        "type": "string",
                        "description": f"Shell to use for execution. Available: {list(settings.ALLOWED_SHELLS.keys())}",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory for command execution",
                    },
                },
                "required": ["command", "shell", "cwd"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
    """
    Handle tool calls for shell command execution.
    
    Args:
        name (str): The name of the tool to call (must be 'execute_command')
        arguments (Dict[str, Any]): Tool arguments including 'command', 'shell', and 'cwd'
        
    Returns:
        List[types.TextContent]: The command execution results or error message
    """
    if name != "execute_command":
        return [types.TextContent(type="text", text=f"Error: Unknown tool {name}")]

    command = arguments["command"]
    shell = arguments.get("shell","bash")
    cwd = arguments["cwd"]

    try:
        result = await run_shell_command( command, cwd,shell)
        return [types.TextContent(type="text", text=str(result))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]

# Define your tool (same logic as before!)
@app_http.tool()
def get_weather(location: str) -> str:
    """Get weather for a location."""
    logger.info(f"Starting get_weather arguments:{location}")
    return f"Weather in {location}: Sunny, 72°F"

@app_http.tool()
async def execute_command(command:str, cwd:str, shell:str = "bash") -> List[types.TextContent]:
    """Execute a shell command"""
    try:
        result = await run_shell_command( command, cwd,shell)
        return [types.TextContent(type="text", text=str(result))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]




def main_http():
    app_http.run(
        transport="http", 
        host=settings.HOST, 
        port=settings.PORT,
        path=settings.PATH
    )

async def main_stdio():
    """Main entry point for the shell MCP server."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=settings.APP_NAME,
                server_version=settings.APP_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

def main():
    if settings.TRANSPORT == "stdio":
        asyncio.run(main_stdio())
    elif settings.TRANSPORT== "http":
        main_http()