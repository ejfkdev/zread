# Zread - AI 代码仓库阅读助手

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Protocol-green)](https://modelcontextprotocol.io/)
[![PyPI](https://img.shields.io/badge/PyPI-zread-blue)](https://pypi.org/project/zread/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Zread 让你和你的 AI 都更懂代码。代码不用看，直接问。连接 [Zread.ai](https://zread.ai)，AI 驱动的 GitHub 项目文档。

**双重身份**：

- 🖥️ **CLI 工具** - 直接在终端运行，无需配置
- 🔌 **MCP 服务器** - 与 Claude、Cline 等 AI 助手集成

**核心特点**：

- 🔍 无需 Token 即可浏览文档、搜索代码、发现仓库
- 🤖 支持 AI 智能问答（基于仓库文档训练）
- 🌐 支持多种传输协议：stdio、HTTP、SSE
- ⚡ 一行命令即可运行，零配置上手

## 功能

- 📖 **阅读文档** - 直接在终端浏览 GitHub 仓库文档
- 🔍 **搜索代码** - 在仓库文档中搜索关键词
- 🌟 **发现仓库** - 浏览热门榜单、搜索优质项目
- 📥 **导出文档** - 批量导出仓库文档到本地，生成 llms.txt 和 llms-full.txt（CLI 专属）
- 🤖 **AI 问答** - 向仓库 AI 助手提问（需登录账号的免费 Token）
- 📄 **查看源码** - 读取源代码文件内容
- 🔌 **MCP 集成** - 与 AI 助手无缝集成

## 运行示例

<table>
  <tr>
    <td align="center">
      <strong>帮助信息</strong><br>
      <code>zread -h</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/master/image/help.png" alt="zread help" width="100%">
    </td>
    <td align="center">
      <strong>文档目录</strong><br>
      <code>zread ls openclaw/openclaw</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/master/image/ls.png" alt="zread ls" width="100%">
    </td>
    <td align="center">
      <strong>查看文档页</strong><br>
      <code>zread cat openclaw/openclaw</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/master/image/cat-wiki.png" alt="zread cat wiki" width="100%">
    </td>
    <td align="center">
      <strong>查看 GitHub 文件</strong><br>
      <code>zread cat facebook/react README.md</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/master/image/cat-github.png" alt="zread cat github" width="100%">
    </td>
  </tr>
  <tr>
    <td align="center">
      <strong>搜索仓库</strong><br>
      <code>zread find ai sandbox</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/master/image/find-repo.png" alt="zread find repo" width="100%">
    </td>
    <td align="center">
      <strong>搜索文档</strong><br>
      <code>zread find openclaw/openclaw gateway</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/master/image/find-wiki.png" alt="zread find wiki" width="100%">
    </td>
    <td align="center">
      <strong>热门仓库</strong><br>
      <code>zread top</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/master/image/top.png" alt="zread top" width="100%">
    </td>
    <td align="center">
      <strong>随机推荐</strong><br>
      <code>zread rand agent-skills</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/master/image/rand.png" alt="zread rand" width="100%">
    </td>
  </tr>
  <tr>
    <td align="center">
      <strong>单轮 AI 提问</strong><br>
      <code>zread ai openclaw/openclaw 介绍这个库 简单讲讲</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/master/image/ai-ask.png" alt="zread ai ask" width="100%">
    </td>
    <td align="center">
      <strong>交互式 AI 对话</strong><br>
      <code>zread ai openclaw/openclaw</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/master/image/ai-chat.png" alt="zread ai chat" width="100%">
    </td>
    <td align="center">
      <strong>导出仓库文档</strong><br>
      <code>zread cp openclaw/openclaw</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/master/image/cp.png" alt="zread cp" width="100%">
    </td>
    <td align="center">
      <strong>MCP HTTP 服务</strong><br>
      <code>zread mcp http :8080</code><br><br>
      <img src="https://raw.githubusercontent.com/ejfkdev/zread/refs/heads/master/image/mcp-http.png" alt="zread mcp http" width="100%">
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
zread mcp [stdio|http|sse] [address] [options]

# 获取仓库文档目录结构
zread ls <repo> [-l zh|en] [-j] [-p]

# 获取指定页面内容或源代码文件
zread cat <repo> [slug_or_path] [-l zh|en] [-j] [-p]
#
# 自动识别参数类型：
# - 第一个参数只有 repo，第二个参数是 slug/序号(如: 1-overview, 1): 读取 zread 文档页面
# - 其他格式(如: README.md, owner/repo/README.md#L1-10, github.com/owner/repo/README.md#L1-10): 读取 GitHub 文件内容

# 搜索
zread find <query>                        # 搜索 GitHub 仓库
zread find <repo> <query>                 # 在仓库文档内搜索

# 发现推荐仓库
zread rand [topic] [-l zh|en] [-j] [-p]

# 获取热门仓库榜单
zread top [weeks] [-l zh|en] [-j] [-p]

# 获取仓库信息
zread stat <repo> [-l zh|en] [-j] [-p]

# 向仓库 AI 提问（需要登录账号的免费 Token）
zread ai <repo> [question] [-l zh|en] [-t token] [-p] [-j] [-m model]


# 导出仓库文档到本地（CLI 专属，生成 llms.txt 和 llms-full.txt）
zread cp <repo> [output_dir] [-l zh|en] [-c concurrency]
```

### 全局选项

命令行支持纯文本与 JSON 输出，兼容管道工具流：

| 选项                 | 说明                                                           |
| -------------------- | -------------------------------------------------------------- |
| `-l, --lang {zh,en}` | 语言（默认：先读 `ZREAD_LANG`，再读 `$LANG`，都没有则为 `zh`） |
| `-j, --json`         | JSON 格式输出                                                  |
| `-p, --plain`        | 纯文本输出                                                     |
| `-t, --token`        | ZREAD_TOKEN                                                    |
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
uvx zread ai python/cpython --model claude-sonnet-4.5 -t your-token
uvx zread ai rust-lang/rust            # 进入交互模式

# 导出文档
uvx zread cp golang/go                          # 导出到当前目录
uvx zread cp python/cpython -l zh               # 指定语言
uvx zread cp vuejs/vue -c 20                    # 调整并发数
```

## MCP 客户端配置

在支持 MCP 的客户端中添加以下配置：

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

## MCP 工具

| 工具           | 说明                                                                       |
| -------------- | -------------------------------------------------------------------------- |
| `read_page`    | 获取指定文档页面内容                                                       |
| `search_docs`  | 在仓库文档中搜索关键词                                                     |
| `read_outline` | 获取仓库文档目录结构                                                       |
| `discover`     | 随机发现推荐仓库                                                           |
| `trending`     | 热门仓库榜单                                                               |
| `info`         | 获取仓库信息和索引状态                                                     |
| `read_file`    | 获取源代码文件内容                                                         |
| `ask`          | 向仓库 AI 智能问答（需 Token），支持 `glm-4.7` 和 `claude-sonnet-4.5` 模型 |

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
| `ZREAD_LANG`  | 默认语言 (zh/en)，优先级高于 `LANG`                           |

## 贡献

欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解如何参与。

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件
