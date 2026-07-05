# Zread - AI 代码仓库阅读助手

[中文](README.zh.md) | [English](README.md)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![zread](https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTQuOTYxNTYgMS42MDAxSDIuMjQxNTZDMS44ODgxIDEuNjAwMSAxLjYwMTU2IDEuODg2NjQgMS42MDE1NiAyLjI0MDFWNC45NjAxQzEuNjAxNTYgNS4zMTM1NiAxLjg4ODEgNS42MDAxIDIuMjQxNTYgNS42MDAxSDQuOTYxNTZDNS4zMTUwMiA1LjYwMDEgNS42MDE1NiA1LjMxMzU2IDUuNjAxNTYgNC45NjAxVjIuMjQwMUM1LjYwMTU2IDEuODg2NjQgNS4zMTUwMiAxLjYwMDEgNC45NjE1NiAxLjYwMDFaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00Ljk2MTU2IDEwLjM5OTlIMi4yNDE1NkMxLjg4ODEgMTAuMzk5OSAxLjYwMTU2IDEwLjY4NjQgMS42MDE1NiAxMS4wMzk5VjEzLjc1OTlDMS42MDE1NiAxNC4xMTM0IDEuODg4MSAxNC4zOTk5IDIuMjQxNTYgMTQuMzk5OUg0Ljk2MTU2QzUuMzE1MDIgMTQuMzk5OSA1LjYwMTU2IDE0LjExMzQgNS42MDE1NiAxMy43NTk5VjExLjAzOTlDNS42MDE1NiAxMC42ODY0IDUuMzE1MDIgMTAuMzk5OSA0Ljk2MTU2IDEwLjM5OTlaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik0xMy43NTg0IDEuNjAwMUgxMS4wMzg0QzEwLjY4NSAxLjYwMDEgMTAuMzk4NCAxLjg4NjY0IDEwLjM5ODQgMi4yNDAxVjQuOTYwMUMxMC4zOTg0IDUuMzEzNTYgMTAuNjg1IDUuNjAwMSAxMS4wMzg0IDUuNjAwMUgxMy43NTg0QzE0LjExMTkgNS42MDAxIDE0LjM5ODQgNS4zMTM1NiAxNC4zOTg0IDQuOTYwMVYyLjI0MDFDMTQuMzk4NCAxLjg4NjY0IDE0LjExMTkgMS42MDAxIDEzLjc1ODQgMS42MDAxWiIgZmlsbD0iI2ZmZiIvPgo8cGF0aCBkPSJNNCAxMkwxMiA0TDQgMTJaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00IDEyTDEyIDQiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgo8L3N2Zz4K&logoColor=ffffff)](https://zread.ai/valeriikot/zread)
[![MCP](https://img.shields.io/badge/MCP-Protocol-green)](https://modelcontextprotocol.io/)
[![CLI](https://img.shields.io/badge/Interface-CLI-2E8B57)](https://pypi.org/project/zread/)
[![Transport](https://img.shields.io/badge/Transport-stdio%20%7C%20http%20%7C%20sse-6A5ACD)](https://github.com/valeriikot/zread)
[![I18N](https://img.shields.io/badge/I18N-zh%20%7C%20en-FF8C00)](https://github.com/valeriikot/zread)
[![PyPI](https://img.shields.io/badge/PyPI-zread-blue)](https://pypi.org/project/zread/)
[![Downloads](https://img.shields.io/pypi/dm/zread)](https://pypi.org/project/zread/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Zread 让你和你的 AI 都更懂代码。代码不用看，直接问。连接 [Zread.ai](https://zread.ai)，AI 驱动的 GitHub 项目文档。

**双重身份**：

- 🖥️ **CLI 工具** - 直接在终端运行，无需配置
- 🔌 **MCP 服务器** - 与 Claude Code、Codex、Hermes Agent、Cline 等 AI 编码智能体集成

**核心特点**：

- 🔍 无需 Token 即可浏览文档、搜索代码、发现仓库
- 🤖 支持 AI 智能问答（基于仓库文档训练）
- 🔗 直连模式：完全不依赖 zread.ai，数据直接来自 GitHub
- 🛠️ 一条命令配置 Claude Code、Codex、Hermes Agent（`zread install`）
- 🏢 公司级部署：一个 Docker 化的共享 MCP 服务供全团队使用
- 🌐 支持多种传输协议：stdio、HTTP、SSE
- ⚡ 一行命令即可运行，零配置上手

## 目录

- [功能](#功能)
- [运行示例](#运行示例)
- [快速启动](#快速启动) — [命令行工具](#命令行工具) · [从源码安装](#从源码安装) · [MCP 服务器](#mcp-服务器) · [AI 问答](#ai-问答)
- [CLI 命令](#cli-命令) — [全局选项](#全局选项) · [命令示例](#命令示例)
- [MCP 客户端配置](#mcp-客户端配置) — [Claude Code](#claude-code) · [Codex](#codex) · [Hermes Agent](#hermes-agent)
- [公司级部署（Docker）](#公司级部署docker)
- [MCP 工具](#mcp-工具)
- [无需 Zread.ai 账号使用](#无需-zreadai-账号使用) — [直连模式](#直连模式完全不连接-zreadai)
- [获取 Token](#获取-token)
- [环境变量](#环境变量)
- [配置文件](#配置文件)

## 功能

- 📖 **阅读文档** - 直接在终端浏览 GitHub 仓库文档
- 🔍 **搜索代码** - 在仓库文档中搜索关键词
- 🌟 **发现仓库** - 浏览热门榜单、搜索优质项目
- 📥 **导出文档** - 批量导出仓库文档到本地，生成 llms.txt 和 llms-full.txt（CLI 专属）
- 🤖 **AI 问答** - 向仓库 AI 助手提问（需登录账号的免费 Token）
- 📄 **查看源码** - 读取源代码文件内容
- 🔌 **MCP 集成** - 与 AI 编码智能体无缝集成（`zread install claude-code|codex|hermes`）
- 🔗 **直连模式** - 除 AI 问答外的全部功能可直接基于 GitHub 运行，完全不访问 zread.ai（`--direct`）
- 🏢 **Docker 部署** - 为整个组织部署一个共享 MCP 服务

## 运行示例

<table>
  <tr>
    <td align="center">
      <strong>帮助信息</strong><br>
      <code>zread -h</code><br><br>
      <img src="https://raw.githubusercontent.com/valeriikot/zread/refs/heads/main/image/help.png" alt="zread help" width="100%">
    </td>
    <td align="center">
      <strong>文档目录</strong><br>
      <code>zread ls openclaw/openclaw</code><br><br>
      <img src="https://raw.githubusercontent.com/valeriikot/zread/refs/heads/main/image/ls.png" alt="zread ls" width="100%">
    </td>
    <td align="center">
      <strong>查看文档页</strong><br>
      <code>zread cat openclaw/openclaw</code><br><br>
      <img src="https://raw.githubusercontent.com/valeriikot/zread/refs/heads/main/image/cat-wiki.png" alt="zread cat wiki" width="100%">
    </td>
    <td align="center">
      <strong>查看 GitHub 文件</strong><br>
      <code>zread cat facebook/react README.md</code><br><br>
      <img src="https://raw.githubusercontent.com/valeriikot/zread/refs/heads/main/image/cat-github.png" alt="zread cat github" width="100%">
    </td>
  </tr>
  <tr>
    <td align="center">
      <strong>搜索仓库</strong><br>
      <code>zread find ai sandbox</code><br><br>
      <img src="https://raw.githubusercontent.com/valeriikot/zread/refs/heads/main/image/find-repo.png" alt="zread find repo" width="100%">
    </td>
    <td align="center">
      <strong>搜索文档</strong><br>
      <code>zread find openclaw/openclaw gateway</code><br><br>
      <img src="https://raw.githubusercontent.com/valeriikot/zread/refs/heads/main/image/find-wiki.png" alt="zread find wiki" width="100%">
    </td>
    <td align="center">
      <strong>热门仓库</strong><br>
      <code>zread top</code><br><br>
      <img src="https://raw.githubusercontent.com/valeriikot/zread/refs/heads/main/image/top.png" alt="zread top" width="100%">
    </td>
    <td align="center">
      <strong>随机推荐</strong><br>
      <code>zread rand agent-skills</code><br><br>
      <img src="https://raw.githubusercontent.com/valeriikot/zread/refs/heads/main/image/rand.png" alt="zread rand" width="100%">
    </td>
  </tr>
  <tr>
    <td align="center">
      <strong>单轮 AI 提问</strong><br>
      <code>zread ai openclaw/openclaw 介绍这个库 简单讲讲</code><br><br>
      <img src="https://raw.githubusercontent.com/valeriikot/zread/refs/heads/main/image/ai-ask.png" alt="zread ai ask" width="100%">
    </td>
    <td align="center">
      <strong>交互式 AI 对话</strong><br>
      <code>zread ai openclaw/openclaw</code><br><br>
      <img src="https://raw.githubusercontent.com/valeriikot/zread/refs/heads/main/image/ai-chat.png" alt="zread ai chat" width="100%">
    </td>
    <td align="center">
      <strong>导出仓库文档</strong><br>
      <code>zread cp openclaw/openclaw</code><br><br>
      <img src="https://raw.githubusercontent.com/valeriikot/zread/refs/heads/main/image/cp.png" alt="zread cp" width="100%">
    </td>
    <td align="center">
      <strong>MCP HTTP 服务</strong><br>
      <code>zread mcp http :8080</code><br><br>
      <img src="https://raw.githubusercontent.com/valeriikot/zread/refs/heads/main/image/mcp-http.png" alt="zread mcp http" width="100%">
    </td>
  </tr>
</table>

## 快速启动

### 命令行工具

```bash
# 使用 uvx 运行
uvx zread

# 或使用 pipx
pipx run zread
```

### 从源码安装

```bash
# 克隆仓库
git clone https://github.com/valeriikot/zread.git
cd zread

# 方式一：使用 uv 在项目环境中运行
uv sync
uv run zread -h

# 方式二：安装为全局工具
uv tool install .          # 或：pipx install .

# 方式三：安装到当前 Python 环境
pip install .
```

也可以不克隆仓库，直接从 Git URL 运行：

```bash
uvx --from git+https://github.com/valeriikot/zread.git zread -h
```

整个 CLI 在单个文件中实现，并带有内联脚本元数据（[PEP 723](https://peps.python.org/pep-0723/)），因此直接运行该文件也可以：`uv run zread/__init__.py`。

### MCP 服务器

```bash
# stdio 模式
uvx zread mcp

# HTTP 模式
uvx zread mcp http
```

### AI 问答

AI 问答功能需要登录 [Zread.ai](https://zread.ai) 账号获取免费 Token。

**配置 Token：**

```bash
# 设置环境变量
export ZREAD_TOKEN=your-token
```

**用法：**

```bash
# 连续问答：进入交互模式，随时追问
zread ai openclaw/openclaw

# 单次对话：直接提问
zread ai facebook/react "这个项目的代码结构是怎样的"
```

## CLI 命令

```bash
# 启动 MCP 服务器
zread mcp [stdio|http|sse] [address] [-t token] [-l zh|en] [-d]

# 获取仓库文档目录结构
zread ls <repo> [-l zh|en] [-j] [-p] [-d]

# 获取指定页面内容或源代码文件
zread cat <repo> [slug_or_path] [-l zh|en] [-j] [-p] [-d]
#
# 自动识别参数类型：
# - 第一个参数只有 repo，第二个参数是 slug/序号(如: 1-overview, 1): 读取 zread 文档页面
# - 其他格式(如: README.md, owner/repo/README.md#L1-10, github.com/owner/repo/README.md#L1-10): 读取 GitHub 文件内容

# 搜索
zread find <query>                        # 搜索 GitHub 仓库
zread find <repo> <query>                 # 在仓库文档内搜索

# 发现推荐仓库
zread rand [topic] [-l zh|en] [-j] [-p] [-d]

# 获取热门仓库榜单
zread top [weeks] [-l zh|en] [-j] [-p] [-d]

# 获取仓库信息（会静默提交未收录的仓库、刷新过期文档）
zread stat <repo> [-l zh|en] [-j] [-p] [-d]

# 向仓库 AI 提问（需要登录账号的免费 Token；直连模式下不可用）
zread ai <repo> [question] [-l zh|en] [-t token] [-p] [-j] [-m model]

# 导出仓库文档到本地（CLI 专属，生成 llms.txt 和 llms-full.txt）
zread cp <repo> [output_dir] [-l zh|en] [-c concurrency] [-d]

# 为 AI 编码智能体配置 zread MCP 服务
# （默认配置本地 stdio 服务；-u 可指向共享 HTTP 服务）
zread install <claude-code|codex|hermes> [-t token] [-u url] [-p]
```

### 全局选项

命令行支持纯文本与 JSON 输出，兼容管道工具流：

| 选项                 | 说明                                                           |
| -------------------- | -------------------------------------------------------------- |
| `-l, --lang {zh,en}` | 语言（优先级：`--lang` > `ZREAD_LANG` > 系统locale，默认 `en`） |
| `-j, --json`         | JSON 格式输出                                                  |
| `-p, --plain`        | 纯文本输出                                                     |
| `-t, --token`        | ZREAD_TOKEN                                                    |
| `-d, --direct`       | 直连模式：数据仅来自 GitHub，完全不访问 zread.ai               |
| `-h, --help`         | 显示帮助                                                       |
| `-v, --version`      | 显示版本                                                       |

### 命令示例

```bash
# MCP 服务器
uvx zread mcp                          # stdio 模式（默认）
uvx zread mcp http                     # HTTP 模式
uvx zread mcp http :8080               # 指定端口
uvx zread mcp http 0.0.0.0:3000/custom # 自定义地址和路径

# 文档相关
uvx zread ls golang/go                 # 查看文档目录
uvx zread cat vuejs/vue                # 查看 zread 首页
uvx zread cat vuejs/vue 1              # zread 文档（使用序号）
uvx zread cat vuejs/vue 1-overview     # zread 文档（使用 slug）
uvx zread cat golang/go README.md      # 查看 GitHub 文件
uvx zread cat python/cpython Lib/http/client.py
uvx zread cat github.com/facebook/react/README.md#L1-10
uvx zread cat facebook/react/README.md#L1-10
uvx zread cat facebook/react README.md 5 10
uvx zread cat facebook/react README.md 5-10
uvx zread cat facebook/react README.md 5~
uvx zread cat facebook/react/README.md 5:
uvx zread find facebook/react hooks

# 仓库发现
uvx zread top                          # 本周热门
uvx zread top 4                        # 最近4周
uvx zread rand python                  # Python 项目
uvx zread rand awesome-list            # 精选资源

# 仓库信息
uvx zread stat torvalds/linux

# AI 问答（需要登录账号的免费 Token）
uvx zread ai golang/go "channel 和 mutex 怎么选择" -t your-token
uvx zread ai python/cpython --model claude-sonnet-4.6 -t your-token
uvx zread ai rust-lang/rust            # 进入交互模式

# 导出文档
uvx zread cp golang/go                          # 导出到当前目录
uvx zread cp python/cpython -l zh               # 指定语言
uvx zread cp vuejs/vue -c 20                    # 调整并发数

# 直连模式（仅访问 GitHub，不访问 zread.ai）
uvx zread ls golang/go -d
uvx zread cat golang/go docs/README.md -d
uvx zread find golang/go goroutine -d

# 配置 AI 编码智能体
uvx zread install claude-code                   # 配置 Claude Code
uvx zread install codex -t your-token           # 配置 Codex 并携带 token
uvx zread install hermes --print                # 仅打印 Hermes 配置
uvx zread install claude-code --url http://zread.internal:8708/mcp  # 指向共享服务
```

## MCP 客户端配置

### 一键配置

`install` 命令可以为常用 AI 编码智能体一键配置 zread MCP 服务：

```bash
uvx zread install claude-code -t your-token   # Claude Code（执行 `claude mcp add`）
uvx zread install codex -t your-token         # OpenAI Codex CLI（执行 `codex mcp add`）
uvx zread install hermes -t your-token        # Hermes Agent（写入 ~/.hermes/config.yaml）
```

token 为可选项——不提供时除 `ask_ai` 工具外的所有功能均可正常使用。添加 `-p` / `--print` 参数可只打印配置内容而不做任何修改。

### Claude Code

```bash
claude mcp add --scope user --env ZREAD_TOKEN=your-token zread -- uvx zread mcp
```

或添加到 `~/.claude.json`（用户级）/ `.mcp.json`（项目级）：

```json
{
  "mcpServers": {
    "zread": {
      "command": "uvx",
      "args": ["zread", "mcp"],
      "env": { "ZREAD_TOKEN": "your-token" }
    }
  }
}
```

### Codex

```bash
codex mcp add --env ZREAD_TOKEN=your-token zread -- uvx zread mcp
```

或添加到 `~/.codex/config.toml`：

```toml
[mcp_servers.zread]
command = "uvx"
args = ["zread", "mcp"]

[mcp_servers.zread.env]
ZREAD_TOKEN = "your-token"
```

### Hermes Agent

添加到 `~/.hermes/config.yaml`：

```yaml
mcp_servers:
  zread:
    command: "uvx"
    args: ["zread", "mcp"]
    env:
      ZREAD_TOKEN: "your-token"
```

### 其他 MCP 客户端

在任意支持 MCP 的客户端中添加以下配置：

```json
{
  "mcpServers": {
    "zread": {
      "command": "uvx",
      "args": ["zread", "mcp"],
      "env": { "ZREAD_TOKEN": "your-token" }
    }
  }
}
```

## 公司级部署（Docker）

无需每位工程师在本机各自运行 `uvx zread mcp`，可以为全公司部署**一个共享的 zread MCP 服务**，让所有 AI 智能体连接它。配置（zread.ai token、直连模式、GitHub token）集中管理，客户端只需要一个 URL。

### 启动服务

```bash
# 单次运行
docker build -t zread-mcp .
docker run -d --name zread-mcp -p 8708:8708 \
  -e ZREAD_TOKEN=your-token \
  zread-mcp

# 或使用 compose（推荐）：复制 .env.example 为 .env 并编辑，然后
docker compose up -d
```

共享 MCP 端点为 `http://<你的主机>:8708/mcp`（streamable HTTP）。

服务端环境变量（见 `.env.example`）：`ZREAD_TOKEN`（全员可用 `ask_ai`，无需分发 token）、`ZREAD_DIRECT`（公司级直连模式，不访问 zread.ai）、`GITHUB_TOKEN`、`ZREAD_LANG`、`ZREAD_MODEL`、`ZREAD_BASE_URL`。

### 连接智能体

每位工程师执行一条命令，指向共享服务而非本地进程：

```bash
uvx zread install claude-code --url http://zread.internal:8708/mcp
uvx zread install hermes      --url http://zread.internal:8708/mcp
uvx zread install codex       --url http://zread.internal:8708/mcp   # 打印 config.toml 配置片段
```

等效的手动配置：

```bash
# Claude Code
claude mcp add --scope user --transport http zread http://zread.internal:8708/mcp
```

```toml
# Codex（~/.codex/config.toml）
[mcp_servers.zread]
url = "http://zread.internal:8708/mcp"
```

```yaml
# Hermes Agent（~/.hermes/config.yaml）
mcp_servers:
  zread:
    url: "http://zread.internal:8708/mcp"
```

### 容器内使用 CLI

镜像内置完整 CLI，同一套部署也可当作共享工具箱：

```bash
docker exec zread-mcp zread ls golang/go -p
docker run --rm zread-mcp top -p
```

> 注意：MCP 端点本身没有内置认证，请部署在内网或负责认证/TLS 的反向代理之后。

## MCP 工具

| 工具              | 说明                                                                       | 直连模式 |
| ---------------- | -------------------------------------------------------------------------- | -------- |
| `read_doc`       | 获取指定文档页面内容                                                       | ✅ 仓库 Markdown 文件 |
| `search_wiki`   | 在仓库文档中搜索关键词                                                     | ✅ 在仓库文档中匹配 |
| `get_doc_outline`| 获取仓库文档目录结构                                                       | ✅ 仓库 Markdown 目录树 |
| `discover_repo`  | 随机发现推荐仓库                                                           | ✅ GitHub 搜索 |
| `get_trending`   | 热门仓库榜单                                                               | ✅ GitHub 搜索 |
| `get_repo_info`  | 获取仓库信息和索引状态                                                     | ✅ GitHub 仓库 API |
| `read_source_file`| 获取源代码文件内容                                                         | ✅ raw.githubusercontent |
| `ask_ai`         | 向仓库 AI 智能问答（需 Token），支持 `glm-5.1` 和 `claude-sonnet-4.6` 模型 | ❌ 不注册 |

`ask_ai` 仅在服务配置了 `ZREAD_TOKEN` 且未启用直连模式时注册。

## 无需 Zread.ai 账号使用

大部分功能不需要注册账号或配置 token，开箱即用：

- **浏览文档** - `zread ls`、`zread cat`
- **搜索** - `zread find`（搜索仓库和文档）
- **发现仓库** - `zread top`、`zread rand`、`zread stat`
- **导出文档** - `zread cp`（含 `llms.txt` / `llms-full.txt`）

唯一需要 token 的功能是 AI 问答：CLI 的 `zread ai` 命令和 MCP 的 `ask_ai` 工具。MCP 服务器在未配置 `ZREAD_TOKEN` 时启动，只是不注册 `ask_ai` 工具，其他工具全部正常可用。

```bash
# CLI，无需 token
uvx zread ls golang/go
uvx zread cat vuejs/vue
uvx zread find ai sandbox

# MCP 服务器，无需 token
uvx zread mcp
```

无 token 的 MCP 客户端配置（`zread install <agent>` 不带 `-t` 参数时生成的配置相同）：

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

之后想启用 AI 问答，按下文说明获取免费 token 并通过 `ZREAD_TOKEN` 配置即可。

### 直连模式：完全不连接 zread.ai

上述方式仍会匿名访问 zread.ai。如果希望 zread **完全不访问** zread.ai，可使用直连模式：所有数据直接来自 GitHub（`api.github.com` + `raw.githubusercontent.com`）。

```bash
# 按命令启用
zread ls golang/go --direct
zread cat golang/go docs/README.md -d
zread find golang/go goroutine -d          # 在仓库自带的 Markdown 文档中搜索
zread stat torvalds/linux -d
zread cp vuejs/vue -d

# 进程级：环境变量
export ZREAD_DIRECT=1

# 或写入配置文件 ~/.config/zread/zread.toml
# [zread]
# direct = true

# 直连模式启动 MCP 服务器
zread mcp --direct
```

直连模式下的功能差异：

| 功能 | zread.ai 模式 | 直连模式 |
| --- | --- | --- |
| `ls` / 文档目录 | AI 生成的 wiki 页面 | 仓库自带的 Markdown 文件（README、`docs/` 等） |
| `cat` / `read_doc` | AI wiki 页面内容 | GitHub 原始文件内容 |
| `find <repo> <query>` | wiki 全文搜索 | 在仓库 Markdown 文档中关键词匹配 |
| `find <query>` / `top` / `rand` / `stat` | zread.ai 目录 | GitHub 搜索 / 仓库 API |
| `cp` 导出 | wiki 导出 + `llms.txt` | Markdown 文档导出 + `llms.txt` |
| `zread ai` / MCP `ask_ai` 工具 | zread.ai 大模型 | **不可用**（明确报错；MCP 不注册该工具） |

直连模式匿名使用 GitHub 公开 API（每小时 60 次）。设置 `GITHUB_TOKEN`（或 `ZREAD_GITHUB_TOKEN` / 配置文件中的 `github_token`）可提升限额并访问私有仓库。读取文件内容（`cat`、`read_doc`、`read_source_file`）完全不消耗 API 配额。

无 token、不访问 zread.ai 的 MCP 客户端配置：

```json
{
  "mcpServers": {
    "zread": {
      "command": "uvx",
      "args": ["zread", "mcp", "--direct"]
    }
  }
}
```

另外：`ZREAD_BASE_URL` 可以把非直连模式指向自建的 zread 兼容 API，而不是 `https://zread.ai`。

## 获取 Token

AI 问答功能需要登录 Zread.ai 账号获取免费的 JWT Token：

1. 访问 https://zread.ai 并登录
2. 按 F12 打开浏览器控制台
3. 粘贴运行：
   ```javascript
   prompt(
     "复制token",
     JSON.parse(localStorage.getItem("CGX_AUTH_STORAGE")).state.token,
   );
   ```
4. 复制弹窗中的 Token

## 环境变量

| 变量          | 说明                                                          |
| ------------- | ------------------------------------------------------------- |
| `ZREAD_TOKEN` | zread.ai 登录账号的免费 JWT Token，仅 AI 问答功能需要         |
| `ZREAD_LANG`  | 默认语言 (`zh` / `en`)，优先级低于 `--lang`，高于系统locale   |
| `ZREAD_MODEL` | 默认 AI 模型 (`glm-5.1` / `claude-sonnet-4.6`)，优先级低于 `--model` |
| `ZREAD_DIRECT` | `1`/`true` 启用直连模式：数据仅来自 GitHub，完全不访问 zread.ai |
| `GITHUB_TOKEN` | 可选的 GitHub token，直连模式使用（提升 API 限额、访问私有仓库）；`ZREAD_GITHUB_TOKEN` 优先级更高 |
| `ZREAD_BASE_URL` | 自建 zread 兼容 API 的地址（默认 `https://zread.ai`） |

## 配置文件

你也可以使用配置文件来配置 zread。优先级为：**命令行参数 > 环境变量 > 配置文件**。

**配置文件路径：**
- macOS: `~/.config/zread/zread.toml`
- Linux: `~/.config/zread/zread.toml`（或 `$XDG_CONFIG_HOME/zread/zread.toml`）
- Windows: `%APPDATA%\zread\zread.toml`

**配置文件格式（TOML）：**

```toml
[zread]
token = "your-token-here"
lang = "zh"  # 可选，默认为 "zh"
model = "glm-5.1"  # 可选，默认为 "glm-5.1"，也支持 "claude-sonnet-4.6"
direct = false  # 可选，true = 直连模式（仅访问 GitHub，不访问 zread.ai）
github_token = ""  # 可选，直连模式使用的 GitHub token
base_url = "https://zread.ai"  # 可选，自建 zread 兼容 API 地址
```

## 贡献

欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解如何参与。

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件
