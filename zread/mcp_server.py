# -*- coding: utf-8 -*-
"""MCP 服务封装：工具 / 资源 / 提示注册，stdio / SSE / HTTP 运行。"""

import logging
import sys
from typing import Any, Optional, Tuple

from zread.config import APP_VERSION, tr
from zread.github import METRICS
from zread.tools import (
    analyze_project,
    compare_projects,
    discover_repo,
    documentation_catalog_resource,
    documentation_page_resource,
    get_doc_outline,
    get_rate_limit,
    get_releases,
    get_repo_info,
    get_trending,
    learn_project,
    list_repo_files,
    read_doc,
    read_source_file,
    search_code,
    search_repos,
    search_wiki,
    weekly_trending_resource,
)

_MCP_INSTANCE: Any = None

VALID_TRANSPORTS = ("stdio", "sse", "http")

# MCP 相关库的名称列表（用于日志级别控制）
_MCP_LOGGER_NAMES = ["fastmcp", "mcp", "uvicorn", "starlette", "anyio"]


def _register_tools(mcp: Any) -> None:
    """注册 MCP 工具（全部基于 GitHub，无需任何账号）"""
    # 文档查询工具
    mcp.tool()(read_doc)
    mcp.tool()(search_wiki)
    mcp.tool()(get_doc_outline)

    # 仓库发现工具
    mcp.tool()(discover_repo)
    mcp.tool()(search_repos)
    mcp.tool()(get_trending)
    mcp.tool()(get_repo_info)

    # 文件 / 代码工具
    mcp.tool()(read_source_file)
    mcp.tool()(list_repo_files)
    mcp.tool()(search_code)

    # Releases 与配额
    mcp.tool()(get_releases)
    mcp.tool()(get_rate_limit)


def _register_resources(mcp: Any) -> None:
    """注册 MCP 资源"""
    mcp.resource("docs://{owner}/{repo}/{page_slug}")(documentation_page_resource)
    mcp.resource("catalog://{owner}/{repo}")(documentation_catalog_resource)
    mcp.resource("trending://weekly")(weekly_trending_resource)


def _register_prompts(mcp: Any) -> None:
    """注册 MCP 提示模板"""
    mcp.prompt()(analyze_project)
    mcp.prompt()(compare_projects)
    mcp.prompt()(learn_project)


def _register_healthz(mcp: Any) -> None:
    """HTTP/SSE 模式下暴露 /healthz（版本 + 运行计数）。

    fastmcp 版本不支持 custom_route 时静默跳过，不影响 MCP 本身。
    """
    try:
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        @mcp.custom_route("/healthz", methods=["GET"])
        async def healthz(request: Request) -> JSONResponse:
            return JSONResponse(
                {
                    "status": "ok",
                    "name": "zread",
                    "version": APP_VERSION,
                    "metrics": dict(METRICS),
                }
            )

    except Exception:
        pass


def _get_mcp() -> Any:
    """按需创建并缓存 MCP 实例，避免普通 CLI 启动时导入 fastmcp。"""
    global _MCP_INSTANCE
    if _MCP_INSTANCE is None:
        from fastmcp import FastMCP

        mcp = FastMCP("zread")
        _register_tools(mcp)
        _register_resources(mcp)
        _register_prompts(mcp)
        _register_healthz(mcp)
        _MCP_INSTANCE = mcp
    return _MCP_INSTANCE


def _parse_address(transport: str, address: Optional[str]) -> Tuple[str, int, str]:
    """解析地址参数

    支持格式:
        - host
        - host:port
        - :port
        - host:port/path
        - :port/path

    返回: (host, port, path)；端口非法时抛 ValueError
    """
    if transport == "stdio" or not address:
        default_path = "/sse" if transport == "sse" else "/mcp"
        return "127.0.0.1", 8708, default_path

    if "/" in address:
        addr_part, path_part = address.split("/", 1)
        path = "/" + path_part
    else:
        addr_part = address
        path = "/sse" if transport == "sse" else "/mcp"

    if ":" in addr_part:
        host, port_str = addr_part.rsplit(":", 1)
        if port_str:
            try:
                port = int(port_str)
            except ValueError:
                raise ValueError(tr("errors.invalid_address", address=address))
            if not (0 < port < 65536):
                raise ValueError(tr("errors.invalid_address", address=address))
        else:
            port = 8708
        host = host if host else "127.0.0.1"
    else:
        host = addr_part if addr_part else "127.0.0.1"
        port = 8708

    return host, port, path


def _run_mcp_server(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8708,
    path: str = "/mcp",
) -> None:
    """运行 MCP 服务器（所有工具基于 GitHub，无需账号）。

    未知 transport 抛 ValueError —— 此前会打印"已启动"然后静默退出。
    """
    if transport not in VALID_TRANSPORTS:
        raise ValueError(tr("errors.unknown_transport", transport=transport))

    mcp = _get_mcp()

    # 打印启动信息到 stderr
    print(tr("mcp.started"), file=sys.stderr)

    if transport == "stdio":
        # stdio 模式：stdout 是 JSON-RPC 通道，所有日志压到 stderr / ERROR 级
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.ERROR)

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.ERROR)
        root_logger.handlers = []
        root_logger.addHandler(handler)

        for name in _MCP_LOGGER_NAMES:
            logging.getLogger(name).setLevel(logging.ERROR)
            logging.getLogger(name).propagate = False

        mcp.run(transport="stdio", show_banner=False)
    elif transport == "sse":
        print(
            tr("mcp.sse_started", url=f"http://{host}:{port}{path}"),
            file=sys.stderr,
        )
        mcp.run(transport="sse", host=host, port=port, path=path)
    else:  # http
        print(
            tr("mcp.http_started", url=f"http://{host}:{port}{path}"),
            file=sys.stderr,
        )
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            path=path,
            stateless_http=True,
        )
