# Zread — GitHub Docs & Code for Your Terminal and AI Agents

[中文](README.zh.md) | English

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Protocol-green)](https://modelcontextprotocol.io/)
[![CLI](https://img.shields.io/badge/Interface-CLI-2E8B57)](https://pypi.org/project/zread/)
[![Transport](https://img.shields.io/badge/Transport-stdio%20%7C%20http%20%7C%20sse-6A5ACD)](https://github.com/valeriikot/zread)
[![I18N](https://img.shields.io/badge/I18N-zh%20%7C%20en-FF8C00)](https://github.com/valeriikot/zread)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Read any GitHub repository's docs and source — from your terminal or from an AI coding agent — **straight from GitHub**. No account, no API key, no external service to sign up for. Everything is backed by the public GitHub API and `raw.githubusercontent.com`; an optional `GITHUB_TOKEN` just raises rate limits and unlocks private repos.

> This is a **standalone fork** of [ejfkdev/zread](https://github.com/ejfkdev/zread). The original connects to the zread.ai SaaS for AI-generated wikis and Q&A; this fork removes that dependency entirely and serves everything directly from GitHub, so you can self-host it with zero third-party accounts.

**Two roles**:

- 🖥️ **CLI tool** — run directly in your terminal with minimal setup
- 🔌 **MCP server** — integrate with AI coding agents such as Claude Code, Codex, Hermes Agent, and Cline

**Highlights**:

- 🔒 No account, no token, no SaaS — data comes straight from GitHub
- 📖 Read a repo's docs (README, `docs/`, …) and any source file, with line ranges
- 🔍 Search a repo's docs, and search / discover repositories via the GitHub API
- 🛠️ One-command setup for Claude Code, Codex, and Hermes Agent (`zread install`)
- 🏢 Self-host one shared Dockerized MCP server for your whole team
- 🌐 Multiple transports: stdio, HTTP, and SSE

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start) — [CLI](#cli-tool) · [from source](#install-from-source) · [MCP server](#mcp-server)
- [CLI Commands](#cli-commands) — [global options](#global-options) · [examples](#examples)
- [MCP Client Configuration](#mcp-client-configuration) — [Claude Code](#claude-code) · [Codex](#codex) · [Hermes Agent](#hermes-agent)
- [Self-hosted Deployment (Docker)](#self-hosted-deployment-docker)
- [MCP Tools](#mcp-tools)
- [GitHub Token (optional)](#github-token-optional)
- [Environment Variables](#environment-variables)
- [Configuration File](#configuration-file)

## Features

- 📖 **Read docs** — browse a repository's own Markdown docs (README, `docs/`, …) in the terminal
- 🔍 **Search docs** — keyword search across a repository's Markdown files
- 🌟 **Discover repos** — trending and recommended repositories via GitHub search
- 📄 **Read source files** — inspect any file's contents, optionally by line range
- 📥 **Export docs** — export a repo's docs locally and generate `llms.txt` / `llms-full.txt` (CLI only)
- 🔌 **MCP integration** — connect AI coding agents in one command (`zread install claude-code|codex|hermes`)
- 🏢 **Docker deployment** — self-host one shared MCP server for your whole organization

## Quick Start

### CLI Tool

```bash
# Run with uvx
uvx zread

# Or with pipx
pipx run zread
```

### Install from Source

```bash
# Clone the repository
git clone https://github.com/valeriikot/zread.git
cd zread

# Option 1: run in the project environment with uv
uv sync
uv run zread -h

# Option 2: install as a global tool
uv tool install .          # or: pipx install .

# Option 3: install into the current Python environment
pip install .
```

You can also run it straight from a Git URL without cloning:

```bash
uvx --from git+https://github.com/valeriikot/zread.git zread -h
```

The whole CLI lives in a single file with inline script metadata ([PEP 723](https://peps.python.org/pep-0723/)), so running the file directly also works: `uv run zread/__init__.py`.

### MCP Server

```bash
# stdio mode (for a local agent)
uvx zread mcp

# HTTP mode (for a shared/self-hosted server)
uvx zread mcp http
```

No token or account is required — the server exposes all tools immediately.

## CLI Commands

```bash
# Start the MCP server
zread mcp [stdio|http|sse] [address] [-l zh|en]

# List a repository's docs (its own Markdown files)
zread ls <repo> [-l zh|en] [-j] [-p]

# Read a doc or a source file
zread cat <repo> [path] [-l zh|en] [-j] [-p]
#
# Automatic argument detection:
# - `zread cat owner/repo` reads the README
# - `zread cat owner/repo docs/guide.md` reads that file
# - github.com/owner/repo/README.md#L1-10 and owner/repo/README.md#L1-10 also work

# Search
zread find <query>                        # Search GitHub repositories
zread find <repo> <query>                 # Search within a repository's docs

# Discover repositories
zread rand [topic] [-l zh|en] [-j] [-p]

# Show trending repositories
zread top [weeks] [-l zh|en] [-j] [-p]

# Show repository information
zread stat <repo> [-l zh|en] [-j] [-p]

# Export a repo's docs locally and generate llms.txt / llms-full.txt
zread cp <repo> [output_dir] [-l zh|en] [-c concurrency]

# Configure the zread MCP server for an AI coding agent
# (local stdio by default; -u points the agent at a shared HTTP server)
zread install <claude-code|codex|hermes> [-u url] [-p]
```

### Global Options

The CLI supports plain text and JSON output and works well in pipelines:

| Option               | Description                                                            |
| -------------------- | ---------------------------------------------------------------------- |
| `-l, --lang {zh,en}` | Language priority: `--lang` > `ZREAD_LANG` > system locale, default `en` |
| `-j, --json`         | Output as JSON                                                         |
| `-p, --plain`        | Output plain text                                                      |
| `-h, --help`         | Show help                                                              |
| `-v, --version`      | Show version                                                           |

### Examples

```bash
# MCP server
uvx zread mcp                          # stdio mode (default)
uvx zread mcp http                     # HTTP mode
uvx zread mcp http :8080               # Custom port
uvx zread mcp http 0.0.0.0:3000/custom # Custom address and path

# Docs & source
uvx zread ls golang/go
uvx zread cat vuejs/vue                 # README
uvx zread cat golang/go README.md
uvx zread cat golang/go docs/README.md
uvx zread cat python/cpython Lib/http/client.py
uvx zread cat github.com/facebook/react/README.md#L1-10
uvx zread cat facebook/react README.md 5 10
uvx zread cat facebook/react README.md 5-10
uvx zread find golang/go goroutine      # grep the repo's Markdown docs

# Discovery
uvx zread top
uvx zread top 4
uvx zread rand python
uvx zread rand awesome-list
uvx zread stat torvalds/linux

# Export docs
uvx zread cp golang/go
uvx zread cp python/cpython -l zh
uvx zread cp vuejs/vue -c 20

# Configure AI coding agents
uvx zread install claude-code
uvx zread install codex
uvx zread install hermes --print
uvx zread install claude-code --url http://zread.internal:8708/mcp
```

## MCP Client Configuration

### One-command setup

The `install` command configures the zread MCP server for popular AI coding agents:

```bash
uvx zread install claude-code   # Claude Code (runs `claude mcp add`)
uvx zread install codex         # OpenAI Codex CLI (prints the config.toml snippet)
uvx zread install hermes        # Hermes Agent (writes ~/.hermes/config.yaml)
```

Add `-p` / `--print` to only print the configuration instead of applying it, and `-u <url>` to point the agent at a shared HTTP server (see [Self-hosted Deployment](#self-hosted-deployment-docker)).

### Claude Code

```bash
claude mcp add --scope user zread -- uvx zread mcp
```

Or add to `~/.claude.json` (user scope) / `.mcp.json` (project scope):

```json
{
  "mcpServers": {
    "zread": {
      "command": "uvx",
      "args": ["zread", "mcp"]
    }
  }
}
```

### Codex

```bash
codex mcp add zread -- uvx zread mcp
```

Or add to `~/.codex/config.toml`:

```toml
[mcp_servers.zread]
command = "uvx"
args = ["zread", "mcp"]
```

### Hermes Agent

Add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  zread:
    command: "uvx"
    args: ["zread", "mcp"]
```

### Other MCP clients

Add the following to any MCP-compatible client:

```json
{
  "mcpServers": {
    "zread": {
      "command": "uvx",
      "args": ["zread", "mcp"]
    }
  }
}
```

## Self-hosted Deployment (Docker)

Instead of every engineer running a local `uvx zread mcp` process, you can run **one shared zread MCP service** for the whole team and point every AI agent at it. There is no SaaS to depend on and nothing to authenticate against upstream — the container just talks to GitHub.

### Run the server

```bash
# One-off
docker build -t zread-mcp .
docker run -d --name zread-mcp -p 8708:8708 zread-mcp
#   optional: -e GITHUB_TOKEN=... for higher API limits / private repos

# Or with compose (recommended): copy .env.example to .env, edit, then
docker compose up -d
```

The shared MCP endpoint is `http://<your-host>:8708/mcp` (streamable HTTP).

Server-side environment variables (see `.env.example`): `GITHUB_TOKEN` (optional — higher rate limits, private repos) and `ZREAD_LANG`.

### Connect your agents

Each engineer runs one command, pointing at the shared server instead of a local process:

```bash
uvx zread install claude-code --url http://zread.internal:8708/mcp
uvx zread install hermes      --url http://zread.internal:8708/mcp
uvx zread install codex       --url http://zread.internal:8708/mcp   # prints the config.toml snippet
```

Equivalent manual configs:

```bash
# Claude Code
claude mcp add --scope user --transport http zread http://zread.internal:8708/mcp
```

```toml
# Codex (~/.codex/config.toml)
[mcp_servers.zread]
url = "http://zread.internal:8708/mcp"
```

```yaml
# Hermes Agent (~/.hermes/config.yaml)
mcp_servers:
  zread:
    url: "http://zread.internal:8708/mcp"
```

### CLI inside the container

The image ships the full CLI, so the same deployment doubles as a shared toolbox:

```bash
docker exec zread-mcp zread ls golang/go -p
docker run --rm zread-mcp top -p
```

> Note: the MCP endpoint has no built-in authentication — deploy it on your internal network or behind a reverse proxy that handles auth/TLS. For a corporate TLS-inspecting proxy, pass its CA at build time: `docker build --build-arg EXTRA_CA_CERT="$(cat ca.pem)" -t zread-mcp .`

## MCP Tools

All tools are backed by GitHub and need no account or token:

| Tool               | Description                                          | Backed by |
| ------------------ | ---------------------------------------------------- | --------- |
| `read_doc`         | Read a documentation page (a repo Markdown file)     | raw.githubusercontent |
| `search_wiki`      | Keyword-search a repository's Markdown docs          | GitHub tree + raw |
| `get_doc_outline`  | List a repository's Markdown docs                    | GitHub tree API |
| `discover_repo`    | Discover a recommended repository                    | GitHub search |
| `get_trending`     | Trending repositories                                | GitHub search |
| `get_repo_info`    | Repository information                               | GitHub repos API |
| `read_source_file` | Read a source file's contents (optional line range)  | raw.githubusercontent |

## GitHub Token (optional)

Everything works anonymously on public repositories. The unauthenticated GitHub API allows ~60 requests/hour; reading file contents (`cat`, `read_doc`, `read_source_file`) goes through `raw.githubusercontent.com` and does not consume that quota.

Set a token to raise the API limit to 5,000 requests/hour and to read private repositories:

```bash
export GITHUB_TOKEN=ghp_your_token   # or ZREAD_GITHUB_TOKEN
```

A [fine-grained or classic PAT](https://github.com/settings/tokens) with read access is enough. The token is only ever sent to `api.github.com` (and to `raw.githubusercontent.com` on a 404 retry, for private repos) — never anywhere else.

## Environment Variables

| Variable              | Description                                                                 |
| --------------------- | --------------------------------------------------------------------------- |
| `GITHUB_TOKEN`        | Optional GitHub token — higher API rate limits and private repos. `ZREAD_GITHUB_TOKEN` takes precedence. |
| `ZREAD_LANG`          | Default language (`zh` / `en`), lower priority than `--lang` and higher than system locale |

## Configuration File

You can also configure zread using a config file. The priority is: **CLI arguments > Environment variables > Config file**.

**Config file locations:**
- macOS: `~/.config/zread/zread.toml`
- Linux: `$XDG_CONFIG_HOME/zread/zread.toml` (if set) or `~/.config/zread/zread.toml`
- Windows: `%APPDATA%\zread\zread.toml`

**Config file format (TOML):**

```toml
[zread]
lang = "en"          # optional, defaults to "en"
github_token = ""    # optional, GitHub token for higher limits / private repos
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

MIT License. See [LICENSE](LICENSE) for details.
