#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zread CLI 与 MCP 服务。

独立的 GitHub 文档 / 源码阅读工具：所有数据直接来自 GitHub，无账号、无外部
SaaS。此包入口重新导出公共 API；实现拆分在子模块中：

- zread.config      配置、语言 / i18n、GitHub 端点与 token
- zread.http        httpx 包装（超时 / 重定向 / 指数退避重试）
- zread.cache       进程内 TTL 缓存 + 磁盘 ETag 缓存
- zread.github      GitHub 数据层（API + raw 文件）
- zread.render      Rich / 纯文本渲染
- zread.tools       MCP 工具函数（docstring 即工具描述）
- zread.export      文档导出（llms.txt / llms-full.txt）
- zread.mcp_server  MCP 服务注册与运行
- zread.cli         Typer CLI
"""

from zread.config import (
    APP_NAME,
    APP_VERSION,
    USER_AGENT,
    ai_api_key,
    ai_backend_url,
    ai_llm_model,
    default_lang,
    github_api_url,
    github_raw_url,
    github_token,
    set_default_lang,
    tr,
)
from zread.github import (
    METRICS,
    fetch_markdown,
    fetch_repo_files,
    fetch_repo_files_with_meta,
    fetch_repo_metadata,
    fetch_repo_outline,
    get_trending_repos,
    parse_repo_url,
    recommend_repos,
)
from zread.tools import (
    analyze_project,
    ask,
    chat,
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
from zread.cli import cli_app, main

__all__ = [
    # 元信息 / 配置
    "APP_NAME",
    "APP_VERSION",
    "USER_AGENT",
    "METRICS",
    "default_lang",
    "set_default_lang",
    "github_api_url",
    "github_raw_url",
    "github_token",
    "ai_backend_url",
    "ai_api_key",
    "ai_llm_model",
    "tr",
    # 数据层公共 API
    "parse_repo_url",
    "fetch_repo_outline",
    "fetch_markdown",
    "fetch_repo_files",
    "fetch_repo_files_with_meta",
    "fetch_repo_metadata",
    "get_trending_repos",
    "recommend_repos",
    # MCP 工具
    "read_doc",
    "search_wiki",
    "get_doc_outline",
    "discover_repo",
    "search_repos",
    "get_trending",
    "get_repo_info",
    "read_source_file",
    "list_repo_files",
    "search_code",
    "get_releases",
    "get_rate_limit",
    # MCP 资源 / 提示
    "documentation_page_resource",
    "documentation_catalog_resource",
    "weekly_trending_resource",
    "analyze_project",
    "compare_projects",
    "learn_project",
    # AI Q&A (self-hosted RAG)
    "ask",
    "chat",
    # 入口
    "cli_app",
    "main",
]


if __name__ == "__main__":
    main()
