# Zread - AI Repository Reading Assistant

[中文](README.zh.md) | English

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Version](https://img.shields.io/badge/Version-2.0.3-0A7B83)](https://pypi.org/project/zread/)
[![zread](https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTQuOTYxNTYgMS42MDAxSDIuMjQxNTZDMS44ODgxIDEuNjAwMSAxLjYwMTU2IDEuODg2NjQgMS42MDE1NiAyLjI0MDFWNC45NjAxQzEuNjAxNTYgNS4zMTM1NiAxLjg4ODEgNS42MDAxIDIuMjQxNTYgNS42MDAxSDQuOTYxNTZDNS4zMTUwMiA1LjYwMDEgNS42MDE1NiA1LjMxMzU2IDUuNjAxNTYgNC45NjAxVjIuMjQwMUM1LjYwMTU2IDEuODg2NjQgNS4zMTUwMiAxLjYwMDEgNC45NjE1NiAxLjYwMDFaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00Ljk2MTU2IDEwLjM5OTlIMi4yNDE1NkMxLjg4ODEgMTAuMzk5OSAxLjYwMTU2IDEwLjY4NjQgMS42MDE1NiAxMS4wMzk5VjEzLjc1OTlDMS42MDE1NiAxNC4xMTM0IDEuODg4MSAxNC4zOTk5IDIuMjQxNTYgMTQuMzk5OUg0Ljk2MTU2QzUuMzE1MDIgMTQuMzk5OSA1LjYwMTU2IDE0LjExMzQgNS42MDE1NiAxMy43NTk5VjExLjAzOTlDNS42MDE1NiAxMC42ODY0IDUuMzE1MDIgMTAuMzk5OSA0Ljk2MTU2IDEwLjM5OTlaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik0xMy43NTg0IDEuNjAwMUgxMS4wMzg0QzEwLjY4NSAxLjYwMDEgMTAuMzk4NCAxLjg4NjY0IDEwLjM5ODQgMi4yNDAxVjQuOTYwMUMxMC4zOTg0IDUuMzEzNTYgMTAuNjg1IDUuNjAwMSAxMS4wMzg0IDUuNjAwMUgxMy43NTg0QzE0LjExMTkgNS42MDAxIDE0LjM5ODQgNS42MDE1NiAxNC4zOTg0IDQuOTYwMVYyLjI0MDFDMTQuMzk4NCAxLjg4NjY0IDE0LjExMTkgMS42MDAxIDEzLjc1ODQgMS42MDAxWiIgZmlsbD0iI2ZmZiIvPgo8cGF0aCBkPSJNNCAxMkwxMiA0TDQgMTJaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00IDEyTDEyIDQiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgo8L3N2Zz4K&logoColor=ffffff)](https://zread.ai/ejfkdev/zread)
[![MCP](https://img.shields.io/badge/MCP-Protocol-green)](https://modelcontextprotocol.io/)
[![CLI](https://img.shields.io/badge/Interface-CLI-2E8B57)](https://pypi.org/project/zread/)
[![Transport](https://img.shields.io/badge/Transport-stdio%20%7C%20http%20%7C%20sse-6A5ACD)](https://github.com/ejfkdev/zread)
[![I18N](https://img.shields.io/badge/I18N-zh%20%7C%20en-FF8C00)](https://github.com/ejfkdev/zread)
[![PyPI](https://img.shields.io/badge/PyPI-zread-blue)](https://pypi.org/project/zread/)
[![Downloads](https://img.shields.io/pypi/dm/zread)](https://pypi.org/project/zread/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Zread helps you and your AI understand codebases faster. Skip the manual source dive and ask directly. It connects to [Zread.ai](https://zread.ai), an AI-powered GitHub project documentation service.

**Two roles**:

- 🖥️ **CLI tool** - run directly in your terminal with minimal setup
- 🔌 **MCP server** - integrate with AI assistants such as Claude and Cline

**Highlights**:

- 🔍 Browse docs, search code, and discover repositories without a token
- 🤖 AI Q&A powered by repository documentation
- 🌐 Multiple transports: stdio, HTTP, and SSE
- ⚡ One command to run, zero-friction startup

## Features

- 📖 **Read docs** - browse GitHub repository docs directly in the terminal
- 🔍 **Search docs** - search keywords across repository documentation
- 🌟 **Discover repos** - browse trending rankings and recommended projects
- 📥 **Export docs** - export repository docs locally and generate `llms.txt` and `llms-full.txt` (CLI only)
- 🤖 **AI Q&A** - ask the repository AI assistant questions (requires a free account token)
- 📄 **Read source files** - inspect source file contents directly
- 🔌 **MCP integration** - connect seamlessly with AI assistants

## Screenshots

<table>
  <tr>
    <td align="center">
      <strong>Help</strong><br>
      <code>zread -h</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/main/image/help.png" alt="zread help" width="100%">
    </td>
    <td align="center">
      <strong>Documentation Outline</strong><br>
      <code>zread ls openclaw/openclaw</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/main/image/ls.png" alt="zread ls" width="100%">
    </td>
    <td align="center">
      <strong>Read a Doc Page</strong><br>
      <code>zread cat openclaw/openclaw</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/main/image/cat-wiki.png" alt="zread cat wiki" width="100%">
    </td>
    <td align="center">
      <strong>Read a GitHub File</strong><br>
      <code>zread cat facebook/react README.md</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/main/image/cat-github.png" alt="zread cat github" width="100%">
    </td>
  </tr>
  <tr>
    <td align="center">
      <strong>Search Repositories</strong><br>
      <code>zread find ai sandbox</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/main/image/find-repo.png" alt="zread find repo" width="100%">
    </td>
    <td align="center">
      <strong>Search Documentation</strong><br>
      <code>zread find openclaw/openclaw gateway</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/main/image/find-wiki.png" alt="zread find wiki" width="100%">
    </td>
    <td align="center">
      <strong>Trending Repos</strong><br>
      <code>zread top</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/main/image/top.png" alt="zread top" width="100%">
    </td>
    <td align="center">
      <strong>Random Recommendation</strong><br>
      <code>zread rand agent-skills</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/main/image/rand.png" alt="zread rand" width="100%">
    </td>
  </tr>
  <tr>
    <td align="center">
      <strong>Single-turn AI Q&A</strong><br>
      <code>zread ai openclaw/openclaw "introduce this project briefly"</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/main/image/ai-ask.png" alt="zread ai ask" width="100%">
    </td>
    <td align="center">
      <strong>Interactive AI Chat</strong><br>
      <code>zread ai openclaw/openclaw</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/main/image/ai-chat.png" alt="zread ai chat" width="100%">
    </td>
    <td align="center">
      <strong>Export Repository Docs</strong><br>
      <code>zread cp openclaw/openclaw</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/main/image/cp.png" alt="zread cp" width="100%">
    </td>
    <td align="center">
      <strong>MCP HTTP Service</strong><br>
      <code>zread mcp http :8080</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/main/image/mcp-http.png" alt="zread mcp http" width="100%">
    </td>
  </tr>
</table>

## Quick Start

### CLI Tool

```bash
# Run with uvx
uvx zread

# Or with pipx
pipx run zread
```

### MCP Server

```bash
# stdio mode
uvx zread mcp

# HTTP mode
uvx zread mcp http
```

### AI Q&A

AI Q&A requires a free token from your [Zread.ai](https://zread.ai) account.

**Set your token:**

```bash
export ZREAD_TOKEN=your-token
```

**Usage:**

```bash
# Interactive multi-turn chat
zread ai openclaw/openclaw

# Single question
zread ai facebook/react "How is this project structured?"
```

## CLI Commands

```bash
# Start the MCP server
zread mcp [stdio|http|sse] [address] [options]

# Show the documentation outline
zread ls <repo> [-l zh|en] [-j] [-p]

# Read a documentation page or a source file
zread cat <repo> [slug_or_path] [-l zh|en] [-j] [-p]
#
# Automatic argument detection:
# - If the first argument is only repo and the second is a slug/index (for example 1-overview, 1), it reads a zread doc page
# - Other forms (for example README.md, owner/repo/README.md#L1-10, github.com/owner/repo/README.md#L1-10) read a GitHub file

# Search
zread find <query>                        # Search GitHub repositories
zread find <repo> <query>                 # Search within a repository's docs

# Discover recommended repositories
zread rand [topic] [-l zh|en] [-j] [-p]

# Show trending repositories
zread top [weeks] [-l zh|en] [-j] [-p]

# Show repository status and metadata
zread stat <repo> [-l zh|en] [-j] [-p]

# Ask the repository AI (requires a free account token)
zread ai <repo> [question] [-l zh|en] [-t token] [-p] [-j] [-m model]

# Export repository docs locally and generate llms.txt / llms-full.txt
zread cp <repo> [output_dir] [-l zh|en] [-c concurrency]
```

### Global Options

The CLI supports plain text and JSON output and works well in pipelines:

| Option               | Description                                                            |
| -------------------- | ---------------------------------------------------------------------- |
| `-l, --lang {zh,en}` | Language priority: `--lang` > `ZREAD_LANG` > system locale, default `en`. |
| `-j, --json`         | Output as JSON                                                         |
| `-p, --plain`        | Output plain text                                                      |
| `-t, --token`        | ZREAD_TOKEN                                                            |
| `-h, --help`         | Show help                                                              |
| `-v, --version`      | Show version                                                           |

### Examples

```bash
# MCP server
uvx zread mcp                          # stdio mode (default)
uvx zread mcp http                     # HTTP mode
uvx zread mcp http :8080               # Custom port
uvx zread mcp http 0.0.0.0:3000/custom # Custom address and path

# Docs
uvx zread ls golang/go
uvx zread cat vuejs/vue
uvx zread cat vuejs/vue 1
uvx zread cat vuejs/vue 1-overview
uvx zread cat golang/go README.md
uvx zread cat python/cpython Lib/http/client.py
uvx zread cat github.com/facebook/react/README.md#L1-10
uvx zread cat facebook/react/README.md#L1-10
uvx zread cat facebook/react README.md 5 10
uvx zread cat facebook/react README.md 5-10
uvx zread cat facebook/react README.md 5~
uvx zread cat facebook/react/README.md 5:
uvx zread find facebook/react hooks

# Discovery
uvx zread top
uvx zread top 4
uvx zread rand python
uvx zread rand awesome-list

# Repository info
uvx zread stat torvalds/linux

# AI Q&A
uvx zread ai golang/go "How do I choose between channels and mutexes?" -t your-token
uvx zread ai python/cpython --model claude-sonnet-4.5 -t your-token
uvx zread ai rust-lang/rust

# Export docs
uvx zread cp golang/go
uvx zread cp python/cpython -l zh
uvx zread cp vuejs/vue -c 20
```

## MCP Client Configuration

Add the following configuration to any MCP-compatible client:

```json
{
  "mcpServers": {
    "zread": {
      "command": "uvx",
      "args": ["--env", "ZREAD_TOKEN=your-token", "zread", "mcp"]
    }
  }
}
```

## MCP Tools

| Tool           | Description                                                                 |
| -------------- | --------------------------------------------------------------------------- |
| `read_page`    | Get the content of a specific documentation page                            |
| `search_docs`  | Search keywords in repository documentation                                 |
| `read_outline` | Get the repository documentation outline                                    |
| `discover`     | Discover a recommended repository at random                                 |
| `trending`     | Get trending repository rankings                                            |
| `info`         | Get repository information and indexing status                              |
| `read_file`    | Read source code file contents                                              |
| `ask`          | Ask the repository AI a question (token required), supports `glm-4.7` and `claude-sonnet-4.5` |

## Get a Token

AI Q&A requires a free JWT token from your Zread.ai account:

1. Visit https://zread.ai and sign in
2. Press F12 to open the browser console
3. Run:
   ```javascript
   prompt(
     "copy token",
     JSON.parse(localStorage.getItem("CGX_AUTH_STORAGE")).state.token,
   );
   ```
4. Copy the token from the popup dialog

## Environment Variables

| Variable       | Description                                                        |
| -------------- | ------------------------------------------------------------------ |
| `ZREAD_TOKEN`  | Free JWT token from your zread.ai account, only required for AI Q&A |
| `ZREAD_LANG`   | Default language (`zh` / `en`), lower priority than `--lang` and higher than system locale |

## Configuration File

You can also configure zread using a config file. The priority is: **CLI arguments > Environment variables > Config file**.

**Config file locations:**
- macOS: `~/.zread/zread.toml`
- Linux: `~/.config/zread/zread.toml` (or `$XDG_CONFIG_HOME/zread/zread.toml`)
- Windows: `%APPDATA%\zread\zread.toml`

**Config file format (TOML):**

```toml
[zread]
token = "your-token-here"
lang = "zh"  # optional, defaults to "zh"
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

MIT License. See [LICENSE](LICENSE) for details.
