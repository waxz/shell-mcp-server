# 🖥️ Shell MCP Server

[![PyPI version](https://badge.fury.io/py/shell-mcp-server.svg)](https://badge.fury.io/py/shell-mcp-server)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> 🚀 Add secure shell command execution capabilities to your AI applications with the Shell MCP Server! Built for the Model Context Protocol.
> 🌍 Support `stdio` and `http` protocol.

<a href="https://glama.ai/mcp/servers/@blazickjp/shell-mcp-server">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@blazickjp/shell-mcp-server/badge" alt="Shell Server MCP server" />
</a>

## ✨ Features

- 🔒 **Secure Execution** - Commands run only in specified directories
- 🐚 **Multiple Shells** - Support for bash, sh, cmd, powershell
- ⏱️ **Timeout Control** - Automatic termination of long-running commands
- 🌍 **Cross-Platform** - Works on both Unix and Windows systems
- 🛡️ **Safe by Default** - Built-in directory and shell validation

## 🚀 Quick Start

### create docker sanbox on windows
https://github.com/waxz/docker-files




### Compile
```bash
uv pip install . 
uv build --wheel

uv pip uninstall shell-mcp-server

uv pip install dist\shell_mcp_server-0.1.3-py3-none-any.whl
```

### Run
```bash

# windows
$ENV:API_KEYS = "sk_qqqq"

# linux
API_KEYS = "sk_qqqq"
shell-mcp-server -d . -t http -c ./config.toml -P 8002 -p /shell
``` 

### tunnel

```
# win11
New-NetFirewallRule -DisplayName "Allow Cloudflared Outbound" -Direction Outbound -Program "C:\Users\axdev\.local\bin\cloudflared.exe" -Action Allow

```

```
cloudflared tunnel --url http://localhost:8000
```

### Run Caddy

Caddyfile
```
:8000 {
	# Match /shell and everything after it
	handle /shell* {
		# Upstream must ONLY be the address, no path or trailing slash
		reverse_proxy localhost:8002
	}
	# Match /fs and everything after it
	handle /fs* {
		# Upstream must ONLY be the address, no path or trailing slash
		reverse_proxy localhost:8001
	}
	#
	handle /hello* {
		# Upstream must ONLY be the address, no path or trailing slash
		#reverse_proxy localhost:6274
		respond "Caddy is receiving tunnel traffic on port 8000."
	}
	handle {
		reverse_proxy localhost:6274
	}
}


```
run Caddy
```
caddy run --config Caddyfile
```


### Inspector
```bash

# winodws
$ENV:DANGEROUSLY_OMIT_AUTH="true"
$ENV:HOST = "0.0.0.0"
#or linux
DANGEROUSLY_OMIT_AUTH="true"
HOST = "0.0.0.0"

npm install -g @modelcontextprotocol/inspector

DANGEROUSLY_OMIT_AUTH="true" HOST="0.0.0.0" mcp-inspector

```

### OpenCode
https://opencode.ai/docs/zh-cn/mcp-servers/#oauth
```
MCPAPI="sk-123456" 

 cat  /home/ubuntu/.config/opencode/opencode.json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "fs": {
      "type": "remote",
      "url": "https://prev-third-columnists-cet.trycloudflare.com/fs",
      "oauth": false,
      "headers": {
        "Authorization": "Bearer {env:MCPAPI}",
        "X-Api-Key": "{env:MCPAPI}"
      }
    },
    "shell": {
      "type": "remote",
      "url": "https://prev-third-columnists-cet.trycloudflare.com/shell",
      "oauth": false,
      "headers": {
        "Authorization": "Bearer {env:MCPAPI}",
        "X-Api-Key": "{env:MCPAPI}"
      }
    }
  }
}
```

### Docker
- https://hub.docker.com/r/microsoft/windows-nanoserver

```bash
docker build -f Dockerfile.linux -t mcp-sandbox-linux .
docker build -f Dockerfile.windows -t mcp-sandbox-windows .
```

### Installation

```bash
# Using pip
pip install shell-mcp-server

# Using uv (recommended)
uv pip install shell-mcp-server
```

### 🔌 Claude Desktop Integration

Add this to your Claude Desktop config to enable shell command execution:

<details>
<summary>📝 Click to view configuration</summary>

```json
{
    "mcpServers": {
        "shell-mcp-server": {
            "command": "uv",
            "args": [
                "--directory",
                "/path/to/shell-mcp-server",
                "run",
                "shell-mcp-server",
                "/path/to/allowed/dir1",
                "/path/to/allowed/dir2",
                "--shell", "bash", "/bin/bash",
                "--shell", "zsh", "/bin/zsh"
            ]
        }
    }
}
```
</details>

## 🎮 Usage Examples

### Basic File Operations
```python
# List directory contents
result = execute_command(
    command="ls -la",
    shell="bash",
    cwd="/path/to/project"
)

# Find files by pattern
result = execute_command(
    command="find . -name '*.py'",
    shell="bash",
    cwd="/path/to/project"
)
```

### Project Management
```python
# Git operations
result = execute_command(
    command="git status && git diff",
    shell="bash",
    cwd="/path/to/repo"
)

# Package management
result = execute_command(
    command="pip list --outdated",
    shell="bash",
    cwd="/path/to/python/project"
)
```

### System Information
```python
# Resource usage
result = execute_command(
    command="df -h && free -h",
    shell="bash",
    cwd="/path/to/dir"
)

# Process monitoring
result = execute_command(
    command="ps aux | grep python",
    shell="bash",
    cwd="/path/to/dir"
)
```

### File Processing
```python
# Search file content
result = execute_command(
    command="grep -r 'TODO' .",
    shell="bash",
    cwd="/path/to/project"
)

# File manipulation
result = execute_command(
    command="awk '{print $1}' data.csv | sort | uniq -c",
    shell="bash",
    cwd="/path/to/data"
)
```

### Windows-Specific Examples
```python
# List processes
result = execute_command(
    command="Get-Process | Where-Object {$_.CPU -gt 10}",
    shell="powershell",
    cwd="C:\\path\\to\\dir"
)

# System information
result = execute_command(
    command="systeminfo | findstr /B /C:'OS'",
    shell="cmd",
    cwd="C:\\path\\to\\dir"
)
```

## ⚙️ Configuration

Configure behavior with command-line arguments:

| Argument | Description |
|----------|-------------|
| `directories` | 📁 List of allowed directories |
| `--shell name path` | 🐚 Shell specifications (name and path) |

Environment variables:
- `COMMAND_TIMEOUT`: ⏱️ Max execution time in seconds (default: 30)

## 🛡️ Security Features

- 🔐 **Directory Isolation**: Commands can only execute in specified directories
- 🔒 **Shell Control**: Only configured shells are allowed
- ⏰ **Timeout Protection**: All commands have a configurable timeout
- 🛑 **Path Validation**: Working directory validation prevents traversal attacks
- 👤 **Permission Isolation**: Commands run with the same permissions as the server process

## 🛠️ Development

Set up your development environment:

```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install development dependencies
uv pip install -e ".[test]"

# Run tests
python -m pytest

# Run tests with coverage
python -m pytest --cov=shell_mcp_server
```

## 🤝 Contributing

Contributions are welcome! Feel free to:

- 🐛 Report bugs
- 💡 Suggest features
- 🔧 Submit pull requests
- 📚 Improve documentation

## 📜 License

MIT License - see [LICENSE](LICENSE) for details.

---

<div align="center">

### 🌟 Enhance Your AI with Secure Shell Access! 🌟

Built for the [Model Context Protocol](https://github.com/anthropics/anthropic-tools) | Made with ❤️ by the MCP Community

<details>
<summary>🎉 Star us on GitHub!</summary>
<br>
If you find this tool useful, consider giving it a star! It helps others discover the project.
</details>

</div>