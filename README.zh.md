# Zread — 在终端和 AI 智能体里读 GitHub 文档与代码

[中文](README.zh.md) | [English](README.md)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Protocol-green)](https://modelcontextprotocol.io/)
[![CLI](https://img.shields.io/badge/Interface-CLI-2E8B57)](https://pypi.org/project/zread/)
[![Transport](https://img.shields.io/badge/Transport-stdio%20%7C%20http%20%7C%20sse-6A5ACD)](https://github.com/valeriikot/zread)
[![I18N](https://img.shields.io/badge/I18N-zh%20%7C%20en-FF8C00)](https://github.com/valeriikot/zread)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

在终端里、或从 AI 编码智能体里，阅读任意 GitHub 仓库的文档和源代码——**数据直接来自 GitHub**。无需注册账号、无需 API key、不依赖任何外部服务。所有内容都基于 GitHub 公开 API 和 `raw.githubusercontent.com`；可选的 `GITHUB_TOKEN` 只是用来提升速率限制、访问私有仓库。

> 这是 [ejfkdev/zread](https://github.com/ejfkdev/zread) 的**独立分支**。原项目依赖 zread.ai SaaS 提供 AI 生成的 wiki 和问答；本分支彻底移除了该依赖，所有内容直接来自 GitHub，因此可以零第三方账号自托管。

**双重身份**：

- 🖥️ **CLI 工具** —— 直接在终端运行，无需配置
- 🔌 **MCP 服务器** —— 与 Claude Code、Codex、Hermes Agent、Cline 等 AI 编码智能体集成

**核心特点**：

- 🔒 无账号、无 token、无 SaaS —— 数据直接来自 GitHub
- 📖 阅读仓库文档（README、`docs/` 等）和任意源文件，支持行号范围
- 🔍 在仓库文档中搜索，并通过 GitHub API 搜索 / 发现仓库
- 🛠️ 一条命令配置 Claude Code、Codex、Hermes Agent（`zread install`）
- 🏢 为整个团队自托管一个共享的 Docker 化 MCP 服务
- 🌐 支持多种传输协议：stdio、HTTP、SSE

## 目录

- [功能](#功能)
- [快速启动](#快速启动) — [命令行工具](#命令行工具) · [从源码安装](#从源码安装) · [MCP 服务器](#mcp-服务器)
- [CLI 命令](#cli-命令) — [全局选项](#全局选项) · [命令示例](#命令示例)
- [MCP 客户端配置](#mcp-客户端配置) — [Claude Code](#claude-code) · [Codex](#codex) · [Hermes Agent](#hermes-agent)
- [自托管部署（Docker）](#自托管部署docker)
- [MCP 工具](#mcp-工具)
- [GitHub Token（可选）](#github-token可选)
- [环境变量](#环境变量)
- [配置文件](#配置文件)

## 功能

- 📖 **阅读文档** —— 在终端浏览仓库自带的 Markdown 文档（README、`docs/` 等）
- 🔍 **搜索文档** —— 在仓库的 Markdown 文件中关键词搜索
- 🌟 **发现仓库** —— 通过 GitHub 搜索获取热门与推荐仓库
- 📄 **查看源码** —— 读取任意文件内容，支持行号范围
- 📥 **导出文档** —— 将仓库文档导出到本地，生成 `llms.txt` / `llms-full.txt`（CLI 专属）
- 🔌 **MCP 集成** —— 一条命令接入 AI 编码智能体（`zread install claude-code|codex|hermes`）
- 🏢 **Docker 部署** —— 为整个组织自托管一个共享 MCP 服务

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
# stdio 模式（本地智能体）
uvx zread mcp

# HTTP 模式（共享 / 自托管服务）
uvx zread mcp http
```

无需 token 或账号——服务器会立即暴露所有工具。

## CLI 命令

```bash
# 启动 MCP 服务器
zread mcp [stdio|http|sse] [address] [-l zh|en]

# 列出仓库文档（仓库自带的 Markdown 文件）
zread ls <repo> [-l zh|en] [-j] [-p]

# 读取文档或源代码文件
zread cat <repo> [path] [-l zh|en] [-j] [-p]
#
# 自动识别参数：
# - `zread cat owner/repo` 读取 README
# - `zread cat owner/repo docs/guide.md` 读取该文件
# - github.com/owner/repo/README.md#L1-10、owner/repo/README.md#L1-10 也支持

# 搜索
zread find <query>                        # 搜索 GitHub 仓库
zread find <repo> <query>                 # 在仓库文档内搜索

# 发现仓库
zread rand [topic] [-l zh|en] [-j] [-p]

# 获取热门仓库榜单
zread top [weeks] [-l zh|en] [-j] [-p]

# 显示仓库信息
zread stat <repo> [-l zh|en] [-j] [-p]

# 导出仓库文档到本地，并生成 llms.txt / llms-full.txt
zread cp <repo> [output_dir] [-l zh|en] [-c concurrency]

# 为 AI 编码智能体配置 zread MCP 服务
# （默认本地 stdio；-u 可指向共享 HTTP 服务）
zread install <claude-code|codex|hermes> [-u url] [-p]
```

### 全局选项

命令行支持纯文本与 JSON 输出，兼容管道工具流：

| 选项                 | 说明                                                           |
| -------------------- | -------------------------------------------------------------- |
| `-l, --lang {zh,en}` | 语言（优先级：`--lang` > `ZREAD_LANG` > 系统locale，默认 `en`） |
| `-j, --json`         | JSON 格式输出                                                  |
| `-p, --plain`        | 纯文本输出                                                     |
| `-h, --help`         | 显示帮助                                                       |
| `-v, --version`      | 显示版本                                                       |

### 命令示例

```bash
# MCP 服务器
uvx zread mcp                          # stdio 模式（默认）
uvx zread mcp http                     # HTTP 模式
uvx zread mcp http :8080               # 指定端口
uvx zread mcp http 0.0.0.0:3000/custom # 自定义地址和路径

# 文档与源码
uvx zread ls golang/go
uvx zread cat vuejs/vue                 # README
uvx zread cat golang/go README.md
uvx zread cat golang/go docs/README.md
uvx zread cat python/cpython Lib/http/client.py
uvx zread cat github.com/facebook/react/README.md#L1-10
uvx zread cat facebook/react README.md 5 10
uvx zread cat facebook/react README.md 5-10
uvx zread find golang/go goroutine      # 在仓库 Markdown 文档中搜索

# 仓库发现
uvx zread top
uvx zread top 4
uvx zread rand python
uvx zread rand awesome-list
uvx zread stat torvalds/linux

# 导出文档
uvx zread cp golang/go
uvx zread cp python/cpython -l zh
uvx zread cp vuejs/vue -c 20

# 配置 AI 编码智能体
uvx zread install claude-code
uvx zread install codex
uvx zread install hermes --print
uvx zread install claude-code --url http://zread.internal:8708/mcp
```

## MCP 客户端配置

### 一键配置

`install` 命令可以为常用 AI 编码智能体一键配置 zread MCP 服务：

```bash
uvx zread install claude-code   # Claude Code（执行 `claude mcp add`）
uvx zread install codex         # OpenAI Codex CLI（打印 config.toml 配置片段）
uvx zread install hermes        # Hermes Agent（写入 ~/.hermes/config.yaml）
```

添加 `-p` / `--print` 可只打印配置而不实际修改；`-u <url>` 可指向共享 HTTP 服务（见[自托管部署](#自托管部署docker)）。

### Claude Code

```bash
claude mcp add --scope user zread -- uvx zread mcp
```

或添加到 `~/.claude.json`（用户级）/ `.mcp.json`（项目级）：

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

或添加到 `~/.codex/config.toml`：

```toml
[mcp_servers.zread]
command = "uvx"
args = ["zread", "mcp"]
```

### Hermes Agent

添加到 `~/.hermes/config.yaml`：

```yaml
mcp_servers:
  zread:
    command: "uvx"
    args: ["zread", "mcp"]
```

### 其他 MCP 客户端

在任意支持 MCP 的客户端中添加以下配置：

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

## 自托管部署（Docker）

无需每位工程师在本机各自运行 `uvx zread mcp`，可以为全团队部署**一个共享的 zread MCP 服务**，让所有 AI 智能体连接它。没有需要依赖的 SaaS，上游也无需任何认证——容器只与 GitHub 通信。

### 启动服务

```bash
# 单次运行
docker build -t zread-mcp .
docker run -d --name zread-mcp -p 8708:8708 zread-mcp
#   可选：-e GITHUB_TOKEN=... 用于提升 API 限额 / 访问私有仓库

# 或使用 compose（推荐）：复制 .env.example 为 .env 并编辑，然后
docker compose up -d
```

共享 MCP 端点为 `http://<你的主机>:8708/mcp`（streamable HTTP）。

服务端环境变量（见 `.env.example`）：`GITHUB_TOKEN`（可选——提升限额、访问私有仓库）与 `ZREAD_LANG`。

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

> 注意：MCP 端点本身没有内置认证，请部署在内网或负责认证/TLS 的反向代理之后。若企业网络使用 TLS 拦截代理，可在构建时传入其 CA：`docker build --build-arg EXTRA_CA_CERT="$(cat ca.pem)" -t zread-mcp .`

## MCP 工具

所有工具都直接来自 GitHub，无需任何账号或 token：

| 工具               | 说明                                          | 数据来源 |
| ------------------ | --------------------------------------------- | -------- |
| `read_doc`         | 读取文档页面（仓库中的 Markdown 文件）        | raw.githubusercontent |
| `search_wiki`      | 在仓库 Markdown 文档中关键词搜索              | GitHub tree + raw |
| `get_doc_outline`  | 列出仓库的 Markdown 文档                      | GitHub tree API |
| `discover_repo`    | 随机发现推荐仓库                              | GitHub 搜索 |
| `get_trending`     | 热门仓库榜单                                  | GitHub 搜索 |
| `get_repo_info`    | 仓库信息                                      | GitHub repos API |
| `read_source_file` | 读取源代码文件内容（可指定行号范围）          | raw.githubusercontent |

## GitHub Token（可选）

在公开仓库上一切都可匿名使用。未认证的 GitHub API 限额约为每小时 60 次；读取文件内容（`cat`、`read_doc`、`read_source_file`）走 `raw.githubusercontent.com`，不消耗该配额。

配置 token 可将 API 限额提升到每小时 5000 次，并读取私有仓库：

```bash
export GITHUB_TOKEN=ghp_your_token   # 或 ZREAD_GITHUB_TOKEN
```

一个具备读取权限的 [细粒度或经典 PAT](https://github.com/settings/tokens) 即可。该 token 只会发送到 `api.github.com`（以及私有仓库 404 重试时的 `raw.githubusercontent.com`），不会发往任何其他地方。

## 环境变量

| 变量                  | 说明                                                                       |
| --------------------- | -------------------------------------------------------------------------- |
| `GITHUB_TOKEN`        | 可选的 GitHub token —— 提升 API 限额、访问私有仓库。`ZREAD_GITHUB_TOKEN` 优先级更高。 |
| `ZREAD_LANG`          | 默认语言（`zh` / `en`），优先级低于 `--lang`、高于系统 locale               |

## 配置文件

也可以通过配置文件配置 zread。优先级为：**命令行参数 > 环境变量 > 配置文件**。

**配置文件位置：**
- macOS：`~/.config/zread/zread.toml`
- Linux：`$XDG_CONFIG_HOME/zread/zread.toml`（若设置）或 `~/.config/zread/zread.toml`
- Windows：`%APPDATA%\zread\zread.toml`

**配置文件格式（TOML）：**

```toml
[zread]
lang = "en"          # 可选，默认 "en"
github_token = ""    # 可选，用于提升限额 / 访问私有仓库的 GitHub token
```

## 贡献

欢迎贡献。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

MIT 许可证。详见 [LICENSE](LICENSE)。
