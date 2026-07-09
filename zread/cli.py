# -*- coding: utf-8 -*-
"""CLI：Typer 命令定义（ls/cat/find/top/rand/stat/tree/releases/limits/cp/config/install/mcp）。"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import arrow
import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.tree import Tree
from typing_extensions import Annotated

from zread.config import (
    _IS_INTERACTIVE,
    APP_NAME,
    APP_VERSION,
    CONFIG_KEYS,
    _resolve_lang,
    ai_api_key,
    ai_backend_url,
    ai_llm_model,
    config_file_location,
    config_from_file,
    existing_config_path,
    github_token,
    set_default_lang,
    tr,
)
from zread.export import _export_repo_async
from zread.github import (
    _github_rate_limit,
    _github_releases,
    _github_repo_tree,
    _github_search_code,
    _github_search_docs,
    _github_search_repos,
    _github_trending,
    _github_recommend,
    _page_url,
    fetch_markdown,
    fetch_repo_metadata,
    fetch_repo_files_with_meta,
    fetch_repo_outline,
    parse_repo_url,
)
from zread.mcp_server import (
    VALID_TRANSPORTS,
    _parse_address,
    _run_mcp_server,
)
from zread.render import (
    ImageAwareMarkdown,
    _format_outline_plain,
    _format_outline_rich,
    _format_repo_list_plain,
    _format_repo_list_rich,
    _format_search_results_plain,
    _format_search_results_rich,
    _format_single_repo_info,
    _format_size,
    _format_status_plain,
    _format_trending_plain,
    _format_trending_rich,
    _get_syntax_theme,
    _preload_images_sync,
    _process_markdown_links,
    _render_github_file_output,
    _run_with_cli_status,
)

# 创建 Typer CLI app
cli_app = typer.Typer(
    help=tr("cli.app_help"),
    add_completion=False,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _print_help_with_env(ctx: typer.Context) -> None:
    """打印帮助信息并附加环境变量面板"""
    typer.echo(ctx.get_help())

    console = Console()
    env_table = Table(show_header=False, box=None, padding=(0, 2))
    env_table.add_row("[green]ZREAD_LANG[/green]", tr("cli.env_var_lang_desc"))
    env_table.add_row(
        "[green]GITHUB_TOKEN[/green]", tr("cli.env_var_github_token_desc")
    )
    env_table.add_row(
        "[green]ZREAD_GITHUB_API_URL[/green]", tr("cli.env_var_api_url_desc")
    )
    env_table.add_row(
        "[green]ZREAD_GITHUB_RAW_URL[/green]", tr("cli.env_var_raw_url_desc")
    )
    env_table.add_row("[green]ZREAD_NO_CACHE[/green]", tr("cli.env_var_no_cache_desc"))

    env_panel = Panel(
        env_table,
        title=f"[bold cyan]{tr('cli.env_vars_title')}[/bold cyan]",
        border_style="blue",
        padding=(1, 2),
    )
    console.print(env_panel)

    config_path = existing_config_path()
    config_table = Table(show_header=False, box=None, padding=(0, 2))
    if sys.platform == "darwin":
        config_table.add_row(
            "[cyan]~/.config/zread/zread.toml[/cyan]", tr("config.macos")
        )
    elif sys.platform == "win32":
        config_table.add_row(
            "[cyan]%APPDATA%\\zread\\zread.toml[/cyan]", tr("config.windows")
        )
    else:
        config_table.add_row(
            "[cyan]~/.config/zread/zread.toml[/cyan]", tr("config.linux")
        )
    if config_path:
        config_table.add_row("[green]✓[/green]", tr("config.found", path=config_path))
    else:
        config_table.add_row("[dim]  [/dim]", tr("config.not_found"))

    config_panel = Panel(
        config_table,
        title=f"[bold cyan]{tr('config.title')}[/bold cyan]",
        border_style="blue",
        padding=(1, 2),
    )
    console.print(config_panel)


@cli_app.callback(invoke_without_command=True)
def cli_callback(
    ctx: typer.Context,
    version: Annotated[
        bool, typer.Option("-v", "--version", help=tr("cli.show_version"))
    ] = False,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    help: Annotated[
        bool, typer.Option("-h", "--help", help=tr("cli.show_help"))
    ] = False,
) -> None:
    """CLI 回调函数，无子命令时显示帮助"""
    if lang:
        set_default_lang(lang)

    if version:
        typer.echo(f"{APP_NAME} {APP_VERSION}")
        raise typer.Exit(0)

    if help or ctx.invoked_subcommand is None:
        _print_help_with_env(ctx)
        raise typer.Exit(0)


@cli_app.command(name="mcp", help=tr("cli.commands.mcp"))
def cmd_mcp(
    transport: Annotated[str, typer.Argument(help=tr("cli.args.transport"))] = "stdio",
    address: Annotated[
        Optional[str],
        typer.Argument(help=tr("cli.args.address")),
    ] = None,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
) -> None:
    """启动 MCP 服务器

    默认地址: 127.0.0.1:8708
    - http 模式默认 path: /mcp
    - sse 模式默认 path: /sse

    示例:
        mcp stdio
        mcp http
        mcp http :8080
        mcp http 0.0.0.0:3000/custom
        mcp sse localhost:8080/events
    """
    # MCP 进程级默认语言：显式参数优先，否则沿用环境变量推导结果
    if lang:
        set_default_lang(lang)

    if transport not in VALID_TRANSPORTS:
        typer.echo(
            f"❌ {tr('errors.unknown_transport', transport=transport)}", err=True
        )
        raise typer.Exit(2)

    try:
        host, port, path = _parse_address(transport, address)
    except ValueError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(2)

    _run_mcp_server(transport, host, port, path)


# ==========================================
# install 命令：为 AI 编码智能体配置 zread MCP 服务
# ==========================================

# 支持的智能体及别名
_INSTALL_AGENTS = ("claude-code", "codex", "hermes")
_INSTALL_AGENT_ALIASES = {
    "claude-code": "claude-code",
    "claude_code": "claude-code",
    "claudecode": "claude-code",
    "claude": "claude-code",
    "codex": "codex",
    "hermes": "hermes",
    "hermes-agent": "hermes",
    "hermes_agent": "hermes",
}


def _mcp_server_spec(url: Optional[str] = None) -> Dict[str, Any]:
    """构造 zread MCP 服务的客户端配置

    url 为空：本地 stdio 模式（uvx zread mcp）
    url 非空：连接共享的 HTTP MCP 服务（如公司统一部署的 Docker 实例）
    """
    if url:
        return {"type": "http", "url": url}
    return {"command": "uvx", "args": ["zread", "mcp"]}


def _claude_code_snippet(url: Optional[str] = None) -> str:
    """Claude Code 的 JSON 配置片段（.mcp.json / ~/.claude.json）"""
    return json.dumps(
        {"mcpServers": {"zread": _mcp_server_spec(url)}},
        ensure_ascii=False,
        indent=2,
    )


def _claude_code_add_command(url: Optional[str] = None) -> List[str]:
    """Claude Code CLI 的注册命令"""
    cmd = ["claude", "mcp", "add", "--scope", "user"]
    if url:
        return cmd + ["--transport", "http", "zread", url]
    return cmd + ["zread", "--", "uvx", "zread", "mcp"]


def _codex_snippet(url: Optional[str] = None) -> str:
    """Codex 的 TOML 配置片段（~/.codex/config.toml）"""
    if url:
        return "\n".join(["[mcp_servers.zread]", f'url = "{url}"'])
    return "\n".join(
        [
            "[mcp_servers.zread]",
            'command = "uvx"',
            'args = ["zread", "mcp"]',
        ]
    )


def _codex_add_command() -> List[str]:
    """Codex CLI 的注册命令（stdio 模式）"""
    return ["codex", "mcp", "add", "zread", "--", "uvx", "zread", "mcp"]


def _hermes_snippet(url: Optional[str] = None) -> str:
    """Hermes Agent 的 YAML 配置片段（~/.hermes/config.yaml）"""
    if url:
        return "\n".join(["mcp_servers:", "  zread:", f'    url: "{url}"'])
    return "\n".join(
        [
            "mcp_servers:",
            "  zread:",
            '    command: "uvx"',
            '    args: ["zread", "mcp"]',
        ]
    )


def _run_install_command(cmd: List[str], lang: str) -> None:
    """执行智能体自带的 mcp add 命令"""
    typer.echo(tr("install.running", lang, command=" ".join(cmd)))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        typer.echo(
            tr("install.command_failed", lang, code=result.returncode), err=True
        )
        raise typer.Exit(1)


def _print_manual_config(
    run_cmd: Optional[List[str]], snippet: str, path: str, lang: str
) -> None:
    """打印手动配置说明：可执行命令 + 配置片段"""
    if run_cmd:
        typer.echo(f"\n{tr('install.manual_run', lang)}")
        typer.echo(f"  {' '.join(run_cmd)}")
        typer.echo(f"\n{tr('install.manual_file', lang, path=path)}")
    else:
        typer.echo(f"\n{tr('install.snippet_hint', lang, path=path)}")
    typer.echo(f"\n{snippet}\n")


def _install_hermes(lang: str, url: Optional[str] = None) -> None:
    """将 zread 写入 Hermes Agent 的 ~/.hermes/config.yaml"""
    config_path = Path.home() / ".hermes" / "config.yaml"
    try:
        import yaml
    except ImportError:
        typer.echo(tr("install.yaml_missing", lang), err=True)
        _print_manual_config(None, _hermes_snippet(url), str(config_path), lang)
        raise typer.Exit(1)

    config: Dict[str, Any] = {}
    if config_path.exists():
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            typer.echo(
                tr("install.config_parse_failed", lang, path=config_path, error=e),
                err=True,
            )
            _print_manual_config(None, _hermes_snippet(url), str(config_path), lang)
            raise typer.Exit(1)
        if isinstance(loaded, dict):
            config = loaded
        # 修改前备份原配置（YAML 重写不保留注释）
        backup_path = config_path.with_suffix(".yaml.bak")
        shutil.copy2(config_path, backup_path)
        typer.echo(tr("install.backup_saved", lang, path=backup_path))

    servers = config.setdefault("mcp_servers", {})
    if not isinstance(servers, dict):
        servers = {}
        config["mcp_servers"] = servers
    # Hermes 的远程服务配置只需要 url 字段（无 type）
    servers["zread"] = {"url": url} if url else _mcp_server_spec()

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    typer.echo(tr("install.written", lang, path=config_path))


@cli_app.command(name="install", help=tr("cli.commands.install"))
def cmd_install(
    ctx: typer.Context,
    agent: Annotated[
        Optional[str], typer.Argument(help=tr("cli.args.agent"))
    ] = None,
    print_only: Annotated[
        bool, typer.Option("--print", "-p", help=tr("cli.options.print_only"))
    ] = False,
    url: Annotated[
        Optional[str], typer.Option("--url", "-u", help=tr("cli.options.mcp_url"))
    ] = None,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
) -> None:
    """为 AI 编码智能体配置 zread MCP 服务

    支持的智能体:
        claude-code    Claude Code（使用 claude mcp add）
        codex          OpenAI Codex CLI（使用 codex mcp add）
        hermes         Hermes Agent（写入 ~/.hermes/config.yaml）

    默认配置本地 stdio 服务（uvx zread mcp）；
    使用 --url 可指向公司统一部署的共享 HTTP MCP 服务。

    示例:
        install claude-code
        install codex
        install hermes --print
        install claude-code --url http://zread.internal:8708/mcp
    """
    lang = _resolve_lang(lang)
    if not agent:
        typer.echo(ctx.get_help())
        typer.echo(f"\n❌ {tr('errors.missing_agent', lang)}", err=True)
        raise typer.Exit(1)

    target = _INSTALL_AGENT_ALIASES.get(agent.strip().lower())
    if target is None:
        typer.echo(
            f"❌ {tr('install.unknown_agent', lang, agent=agent, supported=', '.join(_INSTALL_AGENTS))}",
            err=True,
        )
        raise typer.Exit(1)

    if target == "claude-code":
        run_cmd = _claude_code_add_command(url)
        snippet = _claude_code_snippet(url)
        snippet_path = "~/.claude.json (user) / .mcp.json (project)"
        if print_only or shutil.which("claude") is None:
            if not print_only:
                typer.echo(tr("install.cli_not_found", lang, cli="claude"), err=True)
            _print_manual_config(run_cmd, snippet, snippet_path, lang)
        else:
            _run_install_command(run_cmd, lang)
            typer.echo(f"✅ {tr('install.success', lang, agent='Claude Code')}")
    elif target == "codex":
        snippet = _codex_snippet(url)
        snippet_path = "~/.codex/config.toml"
        if url:
            # codex mcp add 不支持 URL 服务，输出手动配置
            _print_manual_config(None, snippet, snippet_path, lang)
        elif print_only or shutil.which("codex") is None:
            if not print_only:
                typer.echo(tr("install.cli_not_found", lang, cli="codex"), err=True)
            _print_manual_config(_codex_add_command(), snippet, snippet_path, lang)
        else:
            _run_install_command(_codex_add_command(), lang)
            typer.echo(f"✅ {tr('install.success', lang, agent='Codex')}")
    else:  # hermes
        if print_only:
            _print_manual_config(
                None, _hermes_snippet(url), "~/.hermes/config.yaml", lang
            )
        else:
            _install_hermes(lang, url)
            typer.echo(f"✅ {tr('install.success', lang, agent='Hermes Agent')}")


# ==========================================
# ls / cat / find
# ==========================================


@cli_app.command(name="ls", help=tr("cli.commands.ls"))
def cmd_get_outline(
    ctx: typer.Context,
    repo: Annotated[Optional[str], typer.Argument(help=tr("cli.args.repo"))] = None,
    ref: Annotated[
        Optional[str], typer.Option("--ref", "-r", help=tr("cli.options.ref"))
    ] = None,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help=tr("cli.options.json"))
    ] = False,
    plain: Annotated[
        bool, typer.Option("--plain", "-p", help=tr("cli.options.plain"))
    ] = not _IS_INTERACTIVE,
) -> None:
    """获取文档目录结构

    示例:
        ls golang/go
        ls python/cpython -p
        ls rust-lang/rust --ref 1.79.0
    """
    if not repo:
        typer.echo(ctx.get_help())
        typer.echo(f"\n❌ {tr('errors.missing_repo')}", err=True)
        raise typer.Exit(1)
    lang = _resolve_lang(lang)

    outline = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.fetch_outline', lang)}[/dim]",
        fetch_repo_outline,
        repo,
        lang=lang,
        ref=ref,
    )
    if not outline:
        typer.echo(tr("errors.fetch_outline", lang), err=True)
        raise typer.Exit(1)

    parsed = parse_repo_url(repo)
    owner, repo_name = parsed["owner"], parsed["repo"]

    use_ref = ref or parsed.get("ref")
    if json_output:
        typer.echo(json.dumps({"pages": outline}, ensure_ascii=False, indent=2))
    elif plain:
        output = _format_outline_plain({"pages": outline}, owner, repo_name, use_ref)
        typer.echo(output)
    else:
        _format_outline_rich({"pages": outline}, owner, repo_name, use_ref)


# zread slug 模式: 纯数字序号 或 数字前缀 slug
ZREAD_SLUG_PATTERN = re.compile(r"^(?:\d+|\d+-[a-z][a-z-]*)$")


def _is_zread_slug(value: str) -> bool:
    """判断参数是否为 zread 页面 slug。"""
    return ZREAD_SLUG_PATTERN.fullmatch(value.strip()) is not None


def _parse_line_range(arg: str) -> Tuple[Optional[int], Optional[int]]:
    """解析行号范围

    支持的格式:
    - 5, #L5, L5       -> start=5
    - 5:20, 5-20       -> start=5, end=20
    - 5:, 5-, 5~       -> start=5
    - :10, -10, ~10    -> start=1, end=10
    - #L5-L10          -> start=5, end=10

    返回: (start_line, end_line) 或 (None, None) 如果不是行号格式
    """
    range_match = re.match(r"^(?:#L)?(\d+)[:~-]L?(\d+)$", arg)
    if range_match:
        return (int(range_match.group(1)), int(range_match.group(2)))

    start_only_match = re.match(r"^(?:#L)?(\d+)[:~-]$", arg)
    if start_only_match:
        return (int(start_only_match.group(1)), None)

    prefix_match = re.match(r"^[:~-](\d+)$", arg)
    if prefix_match:
        return (1, int(prefix_match.group(1)))

    single_match = re.match(r"^(?:#L|L)?(\d+)$", arg)
    if single_match:
        return (int(single_match.group(1)), None)

    return (None, None)


def _parse_cat_args(
    args: List[str],
) -> Tuple[str, Optional[str], Optional[int], Optional[int], bool, Optional[str]]:
    """按顺序解析 cat 命令的参数

    参数顺序:
    - 文档模式: owner/repo [slug]
    - GitHub 文件: owner/repo[/path] [path] [start] [end]

    GitHub 文件模式支持示例:
    - github.com/owner/repo/README.md#L1-10
    - github.com/owner/repo/blob/v1.0/README.md（保留 ref）
    - owner/repo README.md
    - owner/repo@v1.0 README.md
    - owner/repo/README.md
    - owner/repo README.md 5 10
    - owner/repo README.md 5:10 / 5~10 / 5-10
    - owner/repo README.md 5 / 5: / 5~ / 5-
    - owner/repo README.md :10 / ~10 / -10

    返回: (owner_repo, file_path_or_slug, start_line, end_line, is_zread_page, ref)
    """
    if not args:
        return ("", None, None, None, False, None)

    parsed = parse_repo_url(args[0])
    owner_repo = parsed["repo_path"]
    remaining_args = list(args[1:])

    embedded_path = parsed.get("file_path")
    start_line = parsed.get("start_line")
    end_line = parsed.get("end_line")
    ref = parsed.get("ref")

    # 文档模式要求第一个参数只包含 repo，不带文件路径
    if embedded_path is None:
        if not remaining_args:
            return (owner_repo, "1-overview", None, None, True, ref)
        if _is_zread_slug(remaining_args[0]):
            return (owner_repo, remaining_args[0], None, None, True, ref)

    file_path = embedded_path
    if file_path is None:
        if not remaining_args:
            return (owner_repo, None, start_line, end_line, False, ref)
        file_path = remaining_args.pop(0)

    if remaining_args and start_line is None:
        parsed_start, parsed_end = _parse_line_range(remaining_args[0])
        if parsed_start is not None:
            start_line = parsed_start
            end_line = parsed_end
            remaining_args.pop(0)

    if remaining_args and end_line is None and remaining_args[0].isdigit():
        end_line = int(remaining_args.pop(0))

    return (owner_repo, file_path, start_line, end_line, False, ref)


@cli_app.command(
    name="cat",
    help=tr("cli.commands.cat"),
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def cmd_cat(
    ctx: typer.Context,
    repo_or_url: Annotated[
        Optional[str], typer.Argument(help=tr("cli.args.repo_or_url"))
    ] = None,
    path_or_slug: Annotated[
        Optional[str],
        typer.Argument(help=tr("cli.args.path_or_slug")),
    ] = None,
    arg3: Annotated[
        Optional[str],
        typer.Argument(help=tr("cli.args.cat_extra")),
    ] = None,
    ref: Annotated[
        Optional[str], typer.Option("--ref", "-r", help=tr("cli.options.ref"))
    ] = None,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help=tr("cli.options.json"))
    ] = False,
    plain: Annotated[
        bool, typer.Option("--plain", "-p", help=tr("cli.options.plain"))
    ] = not _IS_INTERACTIVE,
) -> None:
    """查看仓库内容（文档或源代码文件，直接来自 GitHub）

    自动识别参数类型:
    - 文档 slug 格式(如: 1-overview, 1): 按文档目录序号读取
    - 其他格式: 读取 GitHub 文件内容

    示例:
        cat vuejs/vue                          # 默认读取 README
        cat vuejs/vue 1                        # 文档目录第 1 篇
        cat golang/go README.md                # GitHub 文件
        cat python/cpython Lib/http/client.py  # GitHub 文件
        cat facebook/react README.md 5:20      # 指定行号范围
        cat facebook/react/README.md 5:20      # repo包含文件路径+行号
        cat golang/go@go1.22.0 README.md       # 指定分支 / tag
    """
    if not repo_or_url:
        typer.echo(ctx.get_help())
        typer.echo(f"\n❌ {tr('errors.missing_repo_or_url')}", err=True)
        raise typer.Exit(1)
    lang = _resolve_lang(lang)

    # 收集所有位置参数
    all_args = [repo_or_url]
    if path_or_slug is not None:
        all_args.append(path_or_slug)
    if arg3 is not None:
        all_args.append(arg3)
    all_args.extend(ctx.args)

    (
        owner_repo,
        file_path,
        start_line,
        end_line,
        is_zread_page,
        parsed_ref,
    ) = _parse_cat_args(all_args)
    use_ref = ref or parsed_ref

    if is_zread_page:
        _cat_doc_page(
            owner_repo, file_path or "1-overview", lang, json_output, plain, use_ref
        )
    else:
        _cat_github_file_parsed(
            owner_repo, file_path, start_line, end_line, json_output, plain, use_ref
        )


def _cat_doc_page(
    repo: str,
    slug: str,
    lang: str,
    json_output: bool,
    plain: bool,
    ref: Optional[str] = None,
) -> None:
    """读取文档页面"""
    actual_slug = slug
    page_info = None
    pages = None
    use_status = not (json_output or plain)

    # 如果传入的是纯数字，需要先获取目录并按目录顺序定位对应页面
    if slug.isdigit():
        pages = _run_with_cli_status(
            use_status,
            f"[dim]{tr('status.fetch_outline', lang)}[/dim]",
            fetch_repo_outline,
            repo,
            lang=lang,
            ref=ref,
        )
        if not pages:
            typer.echo(tr("errors.fetch_repo_outline", lang), err=True)
            raise typer.Exit(1)

        target_num = int(slug)
        if target_num < 1 or target_num > len(pages):
            typer.echo(
                tr("errors.page_number_not_found", lang, number=target_num), err=True
            )
            raise typer.Exit(1)

        page_info = pages[target_num - 1]
        actual_slug = page_info.get("slug") or ""
        if not actual_slug:
            typer.echo(
                tr("errors.page_missing_slug", lang, number=target_num), err=True
            )
            raise typer.Exit(1)

    content = _run_with_cli_status(
        use_status,
        f"[dim]{tr('status.fetch_page', lang)}[/dim]",
        fetch_markdown,
        repo,
        actual_slug,
        lang,
        ref,
    )
    if not content and slug == "1-overview":
        pages = pages or _run_with_cli_status(
            use_status,
            f"[dim]{tr('status.locate_default_page', lang)}[/dim]",
            fetch_repo_outline,
            repo,
            lang=lang,
            ref=ref,
        )
        if pages:
            first_page = pages[0]
            fallback_slug = first_page.get("slug") or ""
            if fallback_slug and fallback_slug != actual_slug:
                fallback_content = _run_with_cli_status(
                    use_status,
                    f"[dim]{tr('status.fetch_page', lang)}[/dim]",
                    fetch_markdown,
                    repo,
                    fallback_slug,
                    lang,
                    ref,
                )
                if fallback_content:
                    actual_slug = fallback_slug
                    page_info = first_page
                    content = fallback_content

    if not content:
        typer.echo(tr("errors.fetch_page", lang), err=True)
        raise typer.Exit(1)

    # 构建页面标题路径（section / group / topic 或 title）
    if page_info:
        parts = []
        section = page_info.get("section", "")
        group = page_info.get("group", "")
        topic = page_info.get("topic", "")
        title = page_info.get("title", "")

        if section:
            parts.append(section)
        if group:
            parts.append(group)
        parts.append(topic or title)

        path_title = " / ".join(parts) if parts else actual_slug
        parsed = parse_repo_url(repo)
        page_url = _page_url(parsed["owner"], parsed["repo"], actual_slug, ref)

        # 只在非 JSON 模式下输出标题
        if not json_output:
            if plain:
                typer.echo(f"🔗 [{path_title}]({page_url})")
            else:
                console = Console()
                link_text = f"🔗 [link={page_url}]{path_title}[/link]"
                console.print(link_text)
            typer.echo("")

    # 处理 markdown 链接
    content = _process_markdown_links(content, repo)

    # 使用 Rich 渲染 Markdown（除非指定 --plain）
    if json_output:
        typer.echo(json.dumps({"content": content}, ensure_ascii=False, indent=2))
    elif not plain:
        console = Console()
        _preload_images_sync(content)
        theme = _get_syntax_theme()
        md = ImageAwareMarkdown(content, code_theme=theme)
        console.print(md)
    else:
        typer.echo(content)


def _cat_github_file_parsed(
    owner_repo: str,
    file_path: Optional[str],
    start_line: Optional[int],
    end_line: Optional[int],
    json_output: bool,
    plain: bool,
    ref: Optional[str] = None,
) -> None:
    """读取 GitHub 文件内容（已解析参数）"""
    if not owner_repo or not file_path:
        typer.echo(tr("errors.parse_repo_and_file_failed"), err=True)
        raise typer.Exit(1)

    file_meta = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.fetch_file_content')}[/dim]",
        fetch_repo_files_with_meta,
        owner_repo,
        file_path,
        start_line,
        end_line,
        ref=ref,
    )
    if not file_meta:
        typer.echo(tr("errors.fetch_file_content"), err=True)
        raise typer.Exit(1)

    _render_github_file_output(
        file_path=file_path,
        content=file_meta["content"],
        total_lines=file_meta["total_lines"],
        total_size=file_meta["size"],
        actual_start=file_meta["start_line"],
        actual_end=file_meta["end_line"],
        json_output=json_output,
        plain=plain,
    )


@cli_app.command(
    name="find",
    help=tr("cli.commands.find"),
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def cmd_find(
    ctx: typer.Context,
    query: Annotated[Optional[str], typer.Argument(help=tr("cli.args.query"))] = None,
    repo: Annotated[
        Optional[str], typer.Argument(help=tr("cli.args.repo_optional"))
    ] = None,
    code: Annotated[
        bool, typer.Option("--code", help=tr("cli.options.code_search"))
    ] = False,
    ref: Annotated[
        Optional[str], typer.Option("--ref", "-r", help=tr("cli.options.ref"))
    ] = None,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help=tr("cli.options.json"))
    ] = False,
    plain: Annotated[
        bool, typer.Option("--plain", "-p", help=tr("cli.options.plain"))
    ] = not _IS_INTERACTIVE,
) -> None:
    """搜索仓库或文档关键词

    用法:
        find <query>                      # 搜索 GitHub 仓库
        find <repo> <query>               # 在指定仓库文档内搜索
        find <repo> <query> --code        # 在指定仓库源码内搜索（需 GITHUB_TOKEN）

    示例:
        find axios
        find python http client
        find machine learning library
        find facebook/react context api
        find golang/go goroutine scheduler
        find golang/go ListenAndServe --code
    """
    if not query:
        typer.echo(ctx.get_help())
        typer.echo(f"\n❌ {tr('errors.missing_query')}", err=True)
        raise typer.Exit(1)
    lang = _resolve_lang(lang)

    # 检查 query 参数是否是有效的 owner/repo 格式
    # 如果是，则将 repo 视为在仓库内搜索的关键词
    try:
        parse_repo_url(query)
        is_repo_query = True
    except ValueError:
        is_repo_query = False

    if is_repo_query and repo:
        # 在仓库内搜索（文档 grep 或代码搜索）
        keyword = repo
        if ctx.args:
            keyword += " " + " ".join(ctx.args)
        if code:
            _search_code_in_repo(query, keyword, lang, json_output, plain)
        else:
            _search_in_repo(query, keyword, lang, json_output, plain, ref)
    else:
        # 在 GitHub 上搜索仓库；--code 只在仓库内搜索时有意义，静默忽略会误导
        if code:
            typer.echo(f"❌ {tr('errors.code_search_needs_repo', lang)}", err=True)
            raise typer.Exit(1)
        full_query = query
        if repo:
            full_query += " " + repo
        if ctx.args:
            full_query += " " + " ".join(ctx.args)
        _search_repos(full_query, lang, json_output, plain)


def _search_in_repo(
    repo: str,
    keyword: str,
    lang: str,
    json_output: bool,
    plain: bool = False,
    ref: Optional[str] = None,
) -> None:
    """在仓库文档内搜索关键词（grep 仓库自带的 Markdown 文档）"""
    results = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.search_docs', lang)}[/dim]",
        _github_search_docs,
        repo,
        keyword,
        lang,
        ref,
    )
    if results is None:
        typer.echo(tr("errors.search_failed", lang), err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(json.dumps(results, ensure_ascii=False, indent=2))
    elif not results:
        typer.echo(tr("messages.no_results", lang))
    elif plain:
        typer.echo(_format_search_results_plain(results))
    else:
        _format_search_results_rich(results, repo, ref)


def _search_code_in_repo(
    repo: str, keyword: str, lang: str, json_output: bool, plain: bool = False
) -> None:
    """在仓库源码内搜索（GitHub code search API，需要 token）"""
    if not github_token():
        typer.echo(f"❌ {tr('errors.code_search_needs_token', lang)}", err=True)
        raise typer.Exit(1)

    results = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.search_code', lang)}[/dim]",
        _github_search_code,
        repo,
        keyword,
        lang,
    )
    if results is None:
        typer.echo(tr("errors.search_failed", lang), err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(json.dumps(results, ensure_ascii=False, indent=2))
        return
    if not results:
        typer.echo(tr("messages.no_results", lang))
        return

    if plain:
        lines = []
        for idx, item in enumerate(results, 1):
            lines.append(f"{idx}. {item['path']}")
            lines.append(f"   {item['url']}")
            for fragment in item.get("fragments", []):
                snippet = " ".join(fragment.split())[:200]
                lines.append(f"   {snippet}")
            lines.append("")
        typer.echo("\n".join(lines))
    else:
        console = Console()
        for item in results:
            console.print()
            console.print(f"[link={item['url']}]🐙 {item['path']}[/link]")
            for fragment in item.get("fragments", []):
                snippet = " ".join(fragment.split())[:200]
                console.print(f"[dim]{snippet}[/dim]")
        console.print()


def _search_repos(
    query: str, lang: str, json_output: bool, plain: bool = False
) -> None:
    """搜索 GitHub 仓库"""
    data = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.search_repos', lang)}[/dim]",
        _github_search_repos,
        query,
        lang,
    )
    if data is None:
        typer.echo(tr("errors.search_failed", lang), err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if not data:
        typer.echo(tr("messages.no_results", lang))
        return

    if plain:
        output = _format_repo_list_plain(data, lang)
        typer.echo(output)
    else:
        _format_repo_list_rich(data, lang)


# ==========================================
# top / rand / stat
# ==========================================


@cli_app.command(name="top", help=tr("cli.commands.top"))
def cmd_top(
    weeks: Annotated[int, typer.Argument(help=tr("cli.args.weeks"))] = 1,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help=tr("cli.options.json"))
    ] = False,
    plain: Annotated[
        bool, typer.Option("--plain", "-p", help=tr("cli.options.plain"))
    ] = not _IS_INTERACTIVE,
) -> None:
    """获取热门仓库榜单

    示例:
        top
        top 4
        top 2 --json
        top --plain
    """
    lang = _resolve_lang(lang)
    weeks = max(1, weeks)
    result = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.fetch_trending', lang)}[/dim]",
        _github_trending,
        lang,
        weeks,
    )
    if result is None:
        typer.echo(tr("errors.fetch_trending", lang), err=True)
        raise typer.Exit(1)
    limited_result = result[:weeks] if isinstance(result, list) else []

    if json_output:
        typer.echo(json.dumps(limited_result, ensure_ascii=False, indent=2))
        return

    if plain:
        output = _format_trending_plain(limited_result, lang)
        typer.echo(output)
    else:
        _format_trending_rich(limited_result, lang)


@cli_app.command(name="rand", help=tr("cli.commands.rand"))
def cmd_rand(
    topic: Annotated[
        str,
        typer.Argument(help=tr("cli.args.topic_optional")),
    ] = "",
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help=tr("cli.options.json"))
    ] = False,
    plain: Annotated[
        bool, typer.Option("--plain", "-p", help=tr("cli.options.plain"))
    ] = not _IS_INTERACTIVE,
) -> None:
    """随机发现推荐仓库

    常用 topic 标签:
        awesome-list    精选资源列表
        agent-skills    AI Agent 技能
        python          Python 项目
        rust            Rust 项目
        machine-learning 机器学习
        javascript      JavaScript 项目

    示例:
        rand
        rand python
        rand awesome-list
        rand agent-skills --json
        rand rust --plain
    """
    lang = _resolve_lang(lang)
    data = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.fetch_recommend', lang)}[/dim]",
        _github_recommend,
        topic,
        lang,
    )
    if data is None:
        typer.echo(tr("errors.fetch_recommend", lang), err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    repos = data.get("repos", []) if isinstance(data, dict) else data
    if plain:
        output = _format_repo_list_plain(repos or [], lang)
        typer.echo(output)
    else:
        _format_repo_list_rich(repos or [], lang)


@cli_app.command(name="stat", help=tr("cli.commands.stat"))
def cmd_stat(
    ctx: typer.Context,
    repo: Annotated[Optional[str], typer.Argument(help=tr("cli.args.repo"))] = None,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help=tr("cli.options.json"))
    ] = False,
    plain: Annotated[
        bool, typer.Option("--plain", "-p", help=tr("cli.options.plain"))
    ] = not _IS_INTERACTIVE,
) -> None:
    """显示仓库信息

    示例:
        stat torvalds/linux
        stat kubernetes/kubernetes
        stat microsoft/vscode
    """
    if not repo:
        typer.echo(ctx.get_help())
        typer.echo(f"\n❌ {tr('errors.missing_repo')}", err=True)
        raise typer.Exit(1)
    lang = _resolve_lang(lang)

    data = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.fetch_repo_info', lang)}[/dim]",
        fetch_repo_metadata,
        repo,
    )
    if data is None:
        typer.echo(tr("errors.fetch_repo_info", lang), err=True)
        raise typer.Exit(1)

    if isinstance(data, dict) and data.get("_error") == "not_found":
        typer.echo(tr("errors.repo_not_found", lang), err=True)
        raise typer.Exit(1)

    if json_output:
        clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
        typer.echo(json.dumps(clean_data, ensure_ascii=False, indent=2))
    elif plain:
        output = _format_status_plain(data, lang)
        typer.echo(output)
    else:
        console = Console()
        content = _format_single_repo_info(data, lang, show_status=True)
        console.print(
            Panel(
                content,
                title=f"📦 {data.get('owner', '')}/{data.get('name', '')}",
                border_style="blue",
            )
        )


# ==========================================
# tree / releases / limits
# ==========================================


@cli_app.command(name="tree", help=tr("cli.commands.tree"))
def cmd_tree(
    ctx: typer.Context,
    repo: Annotated[Optional[str], typer.Argument(help=tr("cli.args.repo"))] = None,
    path: Annotated[
        str, typer.Argument(help=tr("cli.args.tree_path"))
    ] = "",
    ref: Annotated[
        Optional[str], typer.Option("--ref", "-r", help=tr("cli.options.ref"))
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", "-n", help=tr("cli.options.limit"))
    ] = 200,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help=tr("cli.options.json"))
    ] = False,
    plain: Annotated[
        bool, typer.Option("--plain", "-p", help=tr("cli.options.plain"))
    ] = not _IS_INTERACTIVE,
) -> None:
    """列出仓库文件（可按目录过滤）

    示例:
        tree golang/go src/net/http
        tree facebook/react --ref v18.2.0
        tree rust-lang/rust library/std -n 500
    """
    if not repo:
        typer.echo(ctx.get_help())
        typer.echo(f"\n❌ {tr('errors.missing_repo')}", err=True)
        raise typer.Exit(1)
    lang = _resolve_lang(lang)
    limit = max(1, limit)

    result = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.fetch_tree', lang)}[/dim]",
        _github_repo_tree,
        repo,
        path,
        ref,
        lang,
    )
    if result is None:
        typer.echo(tr("errors.fetch_tree_failed", lang), err=True)
        raise typer.Exit(1)

    files = result["files"][:limit]
    summary = tr("messages.tree_summary", lang, shown=len(files), total=result["total"])

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "files": files,
                    "total": result["total"],
                    "truncated": result["truncated"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if plain:
        for entry in files:
            typer.echo(f"{entry['path']}\t{entry.get('size') or 0}")
        typer.echo(f"# {summary}")
        return

    parsed = parse_repo_url(repo)
    label = f"{parsed['owner']}/{parsed['repo']}"
    if path:
        label += f"/{path.strip('/')}"
    root = Tree(f"[bold cyan]{label}[/bold cyan]  [dim]{summary}[/dim]")
    nodes: Dict[str, Any] = {"": root}
    prefix = path.strip("/")
    for entry in files:
        rel = entry["path"]
        if prefix and rel.startswith(prefix + "/"):
            rel = rel[len(prefix) + 1:]
        parts = rel.split("/")
        for i in range(1, len(parts)):
            dir_key = "/".join(parts[:i])
            if dir_key not in nodes:
                parent = nodes["/".join(parts[: i - 1])]
                nodes[dir_key] = parent.add(f"[bold blue]{parts[i - 1]}/[/bold blue]")
        parent = nodes["/".join(parts[:-1])]
        size = entry.get("size") or 0
        parent.add(f"{parts[-1]} [dim]{_format_size(size)}[/dim]")
    Console().print(root)


@cli_app.command(name="releases", help=tr("cli.commands.releases"))
def cmd_releases(
    ctx: typer.Context,
    repo: Annotated[Optional[str], typer.Argument(help=tr("cli.args.repo"))] = None,
    limit: Annotated[
        int, typer.Option("--limit", "-n", help=tr("cli.options.limit"))
    ] = 5,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help=tr("cli.options.json"))
    ] = False,
    plain: Annotated[
        bool, typer.Option("--plain", "-p", help=tr("cli.options.plain"))
    ] = not _IS_INTERACTIVE,
) -> None:
    """查看仓库 Releases

    示例:
        releases python/cpython
        releases nodejs/node -n 10
    """
    if not repo:
        typer.echo(ctx.get_help())
        typer.echo(f"\n❌ {tr('errors.missing_repo')}", err=True)
        raise typer.Exit(1)
    lang = _resolve_lang(lang)

    releases = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.fetch_releases', lang)}[/dim]",
        _github_releases,
        repo,
        lang,
        max(1, limit),
    )
    if releases is None:
        typer.echo(tr("errors.fetch_releases_failed", lang), err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(json.dumps(releases, ensure_ascii=False, indent=2))
        return

    if not releases:
        typer.echo(tr("messages.releases_none", lang))
        return

    if plain:
        lines = []
        for item in releases:
            date = (item.get("published_at") or "")[:10]
            flags = " (pre-release)" if item.get("prerelease") else ""
            lines.append(f"{item['tag']}  {date}{flags}")
            if item.get("name") and item["name"] != item["tag"]:
                lines.append(f"  {item['name']}")
            lines.append(f"  {item['url']}")
            lines.append("")
        typer.echo("\n".join(lines))
        return

    console = Console()
    for item in releases:
        date = (item.get("published_at") or "")[:10]
        title = f"[bold]{item['tag']}[/bold]"
        if item.get("name") and item["name"] != item["tag"]:
            title += f" — {item['name']}"
        if item.get("prerelease"):
            title += " [yellow](pre-release)[/yellow]"
        if date:
            title += f"  [dim]{date}[/dim]"
        body = item.get("body") or ""
        renderable = (
            ImageAwareMarkdown(body, code_theme=_get_syntax_theme()) if body else ""
        )
        console.print(Panel(renderable, title=title, border_style="blue"))


@cli_app.command(name="limits", help=tr("cli.commands.limits"))
def cmd_limits(
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help=tr("cli.options.json"))
    ] = False,
    plain: Annotated[
        bool, typer.Option("--plain", "-p", help=tr("cli.options.plain"))
    ] = not _IS_INTERACTIVE,
) -> None:
    """显示 GitHub API 配额状态（查询本身不消耗配额）

    示例:
        limits
        limits --json
    """
    lang = _resolve_lang(lang)
    result = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.fetch_limits', lang)}[/dim]",
        _github_rate_limit,
        lang,
    )
    if result is None:
        typer.echo(tr("errors.fetch_rate_limit_failed", lang), err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return

    token_line = (
        tr("limits.token_active", lang)
        if result.get("authenticated")
        else tr("limits.token_missing", lang)
    )

    def _humanize(reset_iso: str) -> str:
        if not reset_iso:
            return ""
        try:
            return arrow.get(reset_iso).humanize(
                locale="zh" if lang == "zh" else "en"
            )
        except Exception:
            return reset_iso

    if plain:
        typer.echo(token_line)
        for name, res in result.get("resources", {}).items():
            typer.echo(
                f"{name}: {res.get('remaining')}/{res.get('limit')}"
                f"  reset {_humanize(res.get('reset', ''))}"
            )
        return

    console = Console()
    table = Table(box=None, padding=(0, 2))
    table.add_column(tr("limits.resource", lang), style="bold")
    table.add_column(tr("limits.remaining", lang), justify="right")
    table.add_column(tr("limits.limit", lang), justify="right")
    table.add_column(tr("limits.resets", lang))
    for name, res in result.get("resources", {}).items():
        remaining = res.get("remaining", 0)
        style = "green" if remaining else "red"
        table.add_row(
            name,
            f"[{style}]{remaining}[/{style}]",
            str(res.get("limit", 0)),
            _humanize(res.get("reset", "")),
        )
    console.print(
        Panel(table, title=f"🔑 {token_line}", border_style="blue", padding=(1, 2))
    )


# ==========================================
# config 命令
# ==========================================

config_app = typer.Typer(help=tr("cli.commands.config"))
cli_app.add_typer(config_app, name="config")

_SECRET_KEYS = ("github_token",)


def _mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return value[:4] + "…" + value[-2:]


def _write_config_values(values: Dict[str, Any]) -> Path:
    """把 [zread] 表写回配置文件（并将权限收紧为 0600，token 不可全局可读）。"""
    path = config_file_location()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[zread]"]
    for key, value in values.items():
        escaped = (
            str(value)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        lines.append(f'{key} = "{escaped}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def _check_config_key(key: str, lang: str) -> None:
    if key not in CONFIG_KEYS:
        typer.echo(
            f"❌ {tr('errors.invalid_config_key', lang, name=key, supported=', '.join(CONFIG_KEYS))}",
            err=True,
        )
        raise typer.Exit(1)


@config_app.command("path", help=tr("cli.commands.config_path"))
def cmd_config_path() -> None:
    """显示配置文件路径"""
    path = config_file_location()
    exists = "✓" if path.exists() else "✗"
    typer.echo(f"{path} [{exists}]")


@config_app.command("get", help=tr("cli.commands.config_get"))
def cmd_config_get(
    key: Annotated[
        Optional[str], typer.Argument(help=tr("cli.args.config_key"))
    ] = None,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
) -> None:
    """读取配置项（不带 key 显示全部）"""
    lang = _resolve_lang(lang)
    values = config_from_file()
    if key is not None:
        _check_config_key(key, lang)
        value = values.get(key, "")
        if key in _SECRET_KEYS and value:
            value = _mask_secret(str(value))
        typer.echo(str(value))
        return
    if not values:
        typer.echo(tr("config.not_found", lang))
        return
    for k in CONFIG_KEYS:
        if k in values:
            value = str(values[k])
            if k in _SECRET_KEYS and value:
                value = _mask_secret(value)
            typer.echo(f"{k} = {value}")


@config_app.command("set", help=tr("cli.commands.config_set"))
def cmd_config_set(
    key: Annotated[str, typer.Argument(help=tr("cli.args.config_key"))],
    value: Annotated[str, typer.Argument(help=tr("cli.args.config_value"))],
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
) -> None:
    """写入配置项（zread config set lang en / set github_token ghp_xxx）"""
    lang = _resolve_lang(lang)
    _check_config_key(key, lang)
    if key == "lang" and value not in ("zh", "en"):
        typer.echo(f"❌ {tr('cli.options.lang', lang)}", err=True)
        raise typer.Exit(1)

    values = config_from_file()
    values[key] = value
    path = _write_config_values(values)
    typer.echo(tr("config.set_ok", lang, name=key, path=path))


@config_app.command("unset", help=tr("cli.commands.config_unset"))
def cmd_config_unset(
    key: Annotated[str, typer.Argument(help=tr("cli.args.config_key"))],
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
) -> None:
    """删除配置项"""
    lang = _resolve_lang(lang)
    _check_config_key(key, lang)
    values = config_from_file()
    if key in values:
        del values[key]
        path = _write_config_values(values)
        typer.echo(tr("config.unset_ok", lang, name=key, path=path))
    else:
        typer.echo(tr("config.not_found", lang))


# ==========================================
# cp（导出）
# ==========================================


@cli_app.command(name="cp", help=tr("cli.commands.cp"))
def cmd_cp(
    ctx: typer.Context,
    repo: Annotated[Optional[str], typer.Argument(help=tr("cli.args.repo"))] = None,
    output_dir: Annotated[
        Optional[Path],
        typer.Argument(help=tr("cli.args.output_dir")),
    ] = None,
    ref: Annotated[
        Optional[str], typer.Option("--ref", "-r", help=tr("cli.options.ref"))
    ] = None,
    include_source: Annotated[
        bool,
        typer.Option("--include-source", "-s", help=tr("cli.options.include_source")),
    ] = False,
    front_matter: Annotated[
        bool, typer.Option("--front-matter", help=tr("cli.options.front_matter"))
    ] = False,
    llms_only: Annotated[
        bool, typer.Option("--llms-only", help=tr("cli.options.llms_only"))
    ] = False,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    concurrency: Annotated[
        int, typer.Option("--concurrency", "-c", help=tr("cli.options.concurrency"))
    ] = 10,
) -> None:
    """导出仓库文档到本地

    下载所有页面的 Markdown 内容，并生成 llms.txt 和 llms-full.txt 文件。

    示例:
        cp golang/go
        cp python/cpython -l zh
        cp vuejs/vue -c 20
        cp golang/go --ref go1.22.0 --front-matter
        cp golang/go --include-source
        cp golang/go --llms-only
    """
    if not repo:
        typer.echo(ctx.get_help())
        typer.echo(f"\n❌ {tr('errors.missing_repo')}", err=True)
        raise typer.Exit(1)
    lang = _resolve_lang(lang)

    if output_dir is None:
        output_dir = Path.cwd()

    parsed = parse_repo_url(repo)
    owner, repo_name = parsed["owner"], parsed["repo"]
    repo_dir_name = f"{owner}-{repo_name}"

    typer.echo(tr("messages.exporting_repo", lang, repo=f"{owner}/{repo_name}"))
    typer.echo(tr("messages.output_dir", lang, path=str(output_dir / repo_dir_name)))
    typer.echo(tr("messages.language_label", lang, lang_code=lang))
    typer.echo(tr("messages.concurrency_label", lang, concurrency=concurrency))
    typer.echo("")

    # 先获取页面数量
    pages = fetch_repo_outline(repo, lang=lang, ref=ref)
    if not pages:
        typer.echo(f"❌ {tr('errors.fetch_outline', lang)}", err=True)
        raise typer.Exit(1)

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(complete_style="cyan", finished_style="green"),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=Console(),
            transient=True,
        ) as progress:
            task_id = progress.add_task(
                tr("status.downloading_repo", lang, repo=f"{owner}/{repo_name}"),
                total=len(pages),
            )
            result = asyncio.run(
                _export_repo_async(
                    repo,
                    output_dir,
                    lang,
                    concurrency,
                    progress,
                    task_id,
                    pages,
                    ref=ref,
                    include_source=include_source,
                    front_matter=front_matter,
                    llms_only=llms_only,
                )
            )

        if not result.get("success"):
            typer.echo(
                tr(
                    "errors.export_failed_with_reason",
                    lang,
                    error=result.get("error"),
                ),
                err=True,
            )
            raise typer.Exit(1)

        typer.echo(tr("messages.export_complete", lang))
        typer.echo(tr("messages.export_total", lang, count=result["total"]))
        typer.echo(tr("messages.export_success", lang, count=result["successful"]))
        typer.echo(tr("messages.export_failed", lang, count=result["failed"]))
        if include_source:
            typer.echo(
                tr("messages.export_source_files", lang, count=result["source_files"])
            )
        typer.echo("")
        typer.echo(tr("messages.export_repo_dir", lang, path=result["repo_dir"]))
        typer.echo(tr("messages.export_llms_file", lang, path=result["llms_file"]))
        typer.echo(
            tr("messages.export_llms_full_file", lang, path=result["llms_full_file"])
        )

        if result["failed"] > 0:
            typer.echo("")
            typer.echo(tr("messages.export_failed_pages", lang))
            for f in result["failed_pages"][:5]:
                page = f.get("page", {})
                slug = page.get("slug", "unknown")
                error = f.get("error", tr("messages.unknown_error", lang))
                typer.echo(f"   - {slug}: {error}", err=True)

    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(tr("errors.export_failed_with_reason", lang, error=e), err=True)
        raise typer.Exit(1)


# ==========================================
# ai — RAG Q&A over a repo (self-hosted backend)
# ==========================================


@cli_app.command(name="ai", help="Ask a question about a repo (self-hosted RAG backend).")
def cmd_ai(
    ctx: typer.Context,
    repo: Annotated[
        Optional[str],
        typer.Argument(help="Repository as owner/repo (e.g. golang/go)."),
    ] = None,
    question: Annotated[
        Optional[str], typer.Argument(help="Question to ask about the repo.")
    ] = None,
    ref: Annotated[
        Optional[str], typer.Option("--ref", "-r", help="Branch / tag / commit.")
    ] = None,
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="LLM model override (default: backend config)."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help="Output raw JSON.")
    ] = False,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
) -> None:
    """Ask a question about a repository using the self-hosted RAG backend.

    The first question on a repo may take longer while the backend indexes
    its documentation; subsequent questions stream back quickly.

    Examples:
        ai golang/go "How are goroutines scheduled?"
        ai microsoft/vscode "How do I write an extension?" --json
        ai vuejs/vue "What is the reactivity system?" --ref v3.4.0
    """
    lang = _resolve_lang(lang)

    backend = ai_backend_url()
    if not backend:
        typer.echo(
            "AI backend not configured.\n"
            "Set ZREAD_AI_BACKEND_URL (e.g. http://localhost:8709) "
            "or run: zread config set ai_backend_url http://localhost:8709",
            err=True,
        )
        raise typer.Exit(1)

    if not repo or not question:
        typer.echo(ctx.get_help())
        typer.echo(
            "\nUsage: zread ai <owner/repo> <question>", err=True
        )
        raise typer.Exit(1)

    # Resolve repo + ref into the backend's repo_id.
    parsed = parse_repo_url(repo)
    owner = parsed.get("owner", "")
    repo_name = parsed.get("repo", "")
    if not owner or not repo_name:
        typer.echo(f"Could not parse repo from '{repo}'.", err=True)
        raise typer.Exit(1)
    resolved_ref = ref or parsed.get("ref") or ""
    repo_id = (
        f"{owner}/{repo_name}@{resolved_ref}" if resolved_ref else f"{owner}/{repo_name}"
    )

    asyncio.run(
        _ai_ask_async(
            backend=backend,
            repo_id=repo_id,
            question=question,
            model=model,
            json_output=json_output,
        )
    )


async def _ai_ask_async(
    backend: str,
    repo_id: str,
    question: str,
    model: Optional[str],
    json_output: bool,
) -> None:
    """Run one ask: create talk → stream answer → delete talk."""
    from zread.ai_client import create_talk, delete_talk, stream_message

    async with httpx.AsyncClient() as client:
        try:
            talk_id = await create_talk(client, backend, repo_id, ai_api_key())
        except httpx.HTTPError as exc:
            typer.echo(f"Backend unreachable at {backend}: {exc}", err=True)
            raise typer.Exit(1)

        answer_parts: list[str] = []
        reasoning_parts: list[str] = []
        try:
            if not json_output:
                typer.echo("")  # blank line before streamed answer
            async for ev in stream_message(
                client,
                backend,
                talk_id,
                question,
                model or ai_llm_model() or None,
                ai_api_key(),
            ):
                if ev.is_error:
                    typer.echo(f"\nError: {ev.text}", err=True)
                    break
                if ev.is_finish:
                    break
                if ev.event == "answer":
                    if json_output:
                        if ev.text:
                            answer_parts.append(ev.text)
                        if ev.reasoning_content:
                            reasoning_parts.append(ev.reasoning_content)
                    else:
                        # Stream tokens live to the terminal.
                        if ev.reasoning_content:
                            typer.echo(ev.reasoning_content, nl=False)
                        if ev.text:
                            typer.echo(ev.text, nl=False)
        finally:
            await delete_talk(client, backend, talk_id, ai_api_key())

        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "answer": "".join(answer_parts),
                        "reasoning": "".join(reasoning_parts),
                        "repo_id": repo_id,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            typer.echo("")  # trailing newline after streamed text


def main():
    """主入口函数"""
    cli_app()
