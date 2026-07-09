# -*- coding: utf-8 -*-
"""MCP 工具层：所有工具函数（docstring 即工具描述，供 LLM 阅读，保持准确）。

约定：数据层返回 None 表示获取失败；空列表 / 空字符串是合法结果，原样返回。
"""

import json
import re
from typing import Dict, List, Optional

from typing_extensions import TypedDict

from zread.config import default_lang, github_token, tr
from zread.github import (
    _github_rate_limit,
    _github_releases,
    _github_repo_metadata,
    _github_repo_tree,
    _github_search_code,
    _github_search_docs,
    fetch_markdown,
    fetch_repo_files,
    fetch_repo_outline,
    get_trending_repos,
    parse_repo_url,
    recommend_repos,
    _github_search_repos,
)

# ==========================================
# 结果类型
# ==========================================


class _RepoItem(TypedDict):
    url: str
    name: str
    description: str
    language: str
    topics: List[str]
    stars: int


class _RepoInfo(_RepoItem, total=False):
    default_branch: str
    pushed_at: int
    license: str
    error: str


class _DiscoverResult(TypedDict, total=False):
    topics: List[str]
    repos: List[_RepoItem]
    error: str


class _OutlinePage(TypedDict):
    slug: str
    title: str


class _DocOutline(TypedDict, total=False):
    pages: List[_OutlinePage]
    error: str


class _WikiSearchItem(TypedDict):
    title: str
    slug: str
    matches: List[str]


class _SearchWikiResult(TypedDict, total=False):
    results: List[_WikiSearchItem]
    error: str


class _SearchReposResult(TypedDict, total=False):
    repos: List[_RepoItem]
    error: str


class _TrendingGroup(TypedDict, total=False):
    title: str
    time_span: Dict[str, str]
    repos: List[_RepoItem]


class _TrendingResult(TypedDict, total=False):
    groups: List[_TrendingGroup]
    error: str


class _FileEntry(TypedDict):
    path: str
    size: int


class _RepoFilesResult(TypedDict, total=False):
    files: List[_FileEntry]
    total: int
    truncated: bool
    error: str


class _CodeSearchItem(TypedDict):
    path: str
    name: str
    url: str
    fragments: List[str]


class _CodeSearchResult(TypedDict, total=False):
    results: List[_CodeSearchItem]
    error: str


class _ReleaseItem(TypedDict):
    tag: str
    name: str
    published_at: str
    prerelease: bool
    url: str
    body: str


class _ReleasesResult(TypedDict, total=False):
    releases: List[_ReleaseItem]
    error: str


class _RateLimitResult(TypedDict, total=False):
    authenticated: bool
    resources: Dict[str, Dict[str, object]]
    error: str


class _ErrorResult(TypedDict):
    error: str


# ==========================================
# 清洗辅助
# ==========================================


def _clean_repo_item(item: Dict, lang: str) -> _RepoItem:
    url = item.get("url", f"https://github.com/{item.get('owner')}/{item.get('name')}")
    desc = (
        item.get("description_zh", "") if lang == "zh" else item.get("description", "")
    )
    if not desc:
        desc = item.get("description", "")
    return {
        "url": url,
        "name": item.get("name", ""),
        "description": desc.replace("\n", " "),
        "language": item.get("language", ""),
        "topics": item.get("topics", []),
        "stars": item.get("star_count", 0),
    }


def _clean_repo_info(item: Dict) -> _RepoInfo:
    lang = default_lang()
    result: _RepoInfo = _clean_repo_item(item, lang)
    default_branch = item.get("default_branch")
    if default_branch:
        result["default_branch"] = default_branch
    last_commit = item.get("last_commit") or {}
    if last_commit.get("when"):
        result["pushed_at"] = last_commit["when"]
    license_info = item.get("license")
    if isinstance(license_info, dict) and license_info.get("name"):
        result["license"] = license_info["name"]
    return result


def _clean_trending(data: List[Dict]) -> List[_TrendingGroup]:
    result: List[_TrendingGroup] = []
    for group in data:
        item: _TrendingGroup = {
            "title": group.get("title", ""),
            "repos": [
                _clean_repo_item(r, default_lang()) for r in group.get("repos", [])
            ],
        }
        time_span = group.get("time_span")
        if time_span:
            item["time_span"] = time_span
        result.append(item)
    return result


def _truncate_text(text: str, max_bytes: Optional[int]) -> str:
    """按 UTF-8 字节数截断输出，避免超大文件撑爆智能体上下文窗口。"""
    if not max_bytes or max_bytes <= 0:
        return text
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    clipped = raw[:max_bytes].decode("utf-8", errors="ignore")
    notice = tr(
        "messages.truncated_output", shown=max_bytes, total=len(raw)
    )
    return f"{clipped}\n\n{notice}"


def _search_wiki_raw(
    repo_url_or_path: str, query: str, ref: Optional[str] = None
) -> Optional[List[Dict]]:
    """搜索仓库文档（grep 仓库内 Markdown 文件），返回原始数据（MCP JSON 用）"""
    results = _github_search_docs(repo_url_or_path, query, default_lang(), ref)
    if results is None:
        return None
    return [
        {
            "title": r.get("title", ""),
            "slug": r.get("slug", ""),
            "matches": [
                re.sub(r"<[^>]+>", "", m.get("content", ""))
                for m in r.get("matches", [])
            ],
        }
        for r in results
    ]


# ==========================================
# MCP Tools: 文档查询
# ==========================================


def read_doc(
    repo: str,
    slug: str,
    ref: Optional[str] = None,
    max_bytes: Optional[int] = None,
) -> str:
    """Read a documentation file from a GitHub repository.

    The slug is the file path inside the repository (for example "README.md",
    "docs/guide.md"). The special slug "1-overview" resolves to the README.
    Content is fetched straight from GitHub.

    Pages may contain two kinds of links:
    - Source file links: `[name](path#Lstart-Lend)` — follow them with
      `read_source_file(repo, file_path, start_line, end_line)`.
    - Doc links: `[title](slug)` — follow them with `read_doc(repo, slug)`.

    Args:
        repo: Repository in owner/repo format.
        slug: File path inside the repository ("1-overview" for the README).
        ref: Optional branch, tag, or commit (defaults to the default branch).
        max_bytes: Optional maximum size of the returned text in bytes;
            longer content is truncated with a notice.

    Returns:
        The Markdown content of the page.

    Examples:
        read_doc("openclaw/openclaw", "1-overview")
        read_doc("golang/go", "doc/contribute.md", ref="release-branch.go1.22")
    """
    result = fetch_markdown(repo, slug, lang=default_lang(), ref=ref)
    if result is None:
        return tr("errors.fetch_page_for_slug_failed", slug=slug)
    return _truncate_text(result, max_bytes)


def search_wiki(repo: str, query: str, ref: Optional[str] = None) -> _SearchWikiResult:
    """Search the documentation files of a GitHub repository.

    Greps the repository's Markdown/reST docs (README, docs/, ...) for the
    keyword and returns matching pages with content snippets. An empty
    results list means the search ran but found nothing.

    Args:
        repo: Repository in owner/repo format.
        query: Search keyword, e.g. "install", "config", "API".
        ref: Optional branch, tag, or commit.

    Returns:
        {"results": [{"title", "slug", "matches"}]} or {"error": ...}.

    Examples:
        search_wiki("python/cpython", "GIL")
        search_wiki("facebook/react", "hooks")
    """
    results = _search_wiki_raw(repo, query, ref)
    if results is not None:
        return {"results": results}
    return {"error": tr("errors.search_failed")}


def get_doc_outline(repo: str, ref: Optional[str] = None) -> _DocOutline:
    """List the documentation files of a GitHub repository.

    Returns the repository's own Markdown docs (README, docs/, ...). Each
    page's slug is the file path inside the repository and can be passed
    directly to read_doc(repo, slug).

    Args:
        repo: Repository in owner/repo format.
        ref: Optional branch, tag, or commit.

    Returns:
        {"pages": [{"slug", "title"}]} or {"error": ...}.

    Examples:
        get_doc_outline("golang/go")
        get_doc_outline("microsoft/vscode")
    """
    outline = fetch_repo_outline(repo, lang=default_lang(), ref=ref)
    if outline is None:
        return {"error": tr("errors.fetch_repo_outline_failed")}

    pages = [{"slug": p.get("slug", ""), "title": p.get("title", "")} for p in outline]
    return {"pages": pages}


# ==========================================
# MCP Tools: 仓库发现
# ==========================================


def discover_repo(topic: str = "") -> _DiscoverResult:
    """Discover notable GitHub repositories, optionally filtered by topic.

    Picks a randomized selection of highly-starred repositories from GitHub
    search, optionally restricted to a GitHub topic tag.

    Args:
        topic: GitHub topic tag such as "python", "awesome-list", or
            "machine-learning". Empty returns popular repositories overall.

    Returns:
        {"topics": [...], "repos": [...]} or {"error": ...}.

    Examples:
        discover_repo()
        discover_repo("rust")
        discover_repo("awesome-list")
    """
    result = recommend_repos(topic=topic, lang=default_lang())
    if result is not None:
        repos = result.get("repos", []) if isinstance(result, dict) else []
        topics = result.get("topics", []) if isinstance(result, dict) else []
        return {
            "topics": topics,
            "repos": [_clean_repo_item(r, default_lang()) for r in repos],
        }
    return {"error": tr("errors.fetch_recommend_repo_failed")}


def search_repos(query: str) -> _SearchReposResult:
    """Search GitHub repositories by keyword.

    Uses the GitHub repository search API. An empty repos list means the
    search ran successfully but matched nothing.

    Args:
        query: Search keyword, e.g. "react", "http client".

    Returns:
        {"repos": [...]} or {"error": ...}.

    Examples:
        search_repos("axios")
        search_repos("neural network")
    """
    result = _github_search_repos(query, lang=default_lang())
    if result is not None:
        return {"repos": [_clean_repo_item(r, default_lang()) for r in result]}
    return {"error": tr("errors.search_repo_failed")}


def get_trending(weeks: int = 1) -> _TrendingResult:
    """Get trending GitHub repositories, grouped by week.

    Each group lists the most-starred repositories created in that week
    (GitHub search: created that week, ordered by stars).

    Args:
        weeks: Number of recent weeks to return (1-8, default 1). Each week
            costs one GitHub search API request.

    Returns:
        {"groups": [{"title", "time_span", "repos"}]} or {"error": ...}.

    Examples:
        get_trending()
        get_trending(4)
    """
    weeks = max(1, min(int(weeks), 8))
    result = get_trending_repos(lang=default_lang(), weeks=weeks)
    if result is not None:
        return {"groups": _clean_trending(result[:weeks])}
    return {"error": tr("errors.fetch_trending_repo_failed")}


def get_repo_info(repo: str) -> _RepoInfo:
    """Get metadata for a GitHub repository.

    Returns description, primary language, topics, star count, default
    branch, last-push time, and license — straight from the GitHub API.

    Args:
        repo: Repository in owner/repo format.

    Returns:
        Repository info dict, or {"error": ...} if the repository does not
        exist or cannot be fetched.

    Examples:
        get_repo_info("golang/go")
        get_repo_info("torvalds/linux")
    """
    if "/" not in repo:
        return {"error": tr("errors.invalid_repo_format")}
    result = _github_repo_metadata(repo, default_lang())
    if result is None:
        return {"error": tr("errors.fetch_repo_info_failed")}
    if result.get("_error"):
        return {"error": tr("errors.repo_not_found")}
    return _clean_repo_info(result)


def read_source_file(
    repo: str,
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    ref: Optional[str] = None,
    max_bytes: Optional[int] = None,
) -> str:
    """Read a source file from a GitHub repository.

    Fetches the file content from GitHub, optionally limited to a line range
    and/or a maximum byte size.

    Args:
        repo: Repository in owner/repo format.
        path: File path inside the repository, e.g. "src/config.ts".
        start_line: First line to include (1-based, inclusive).
        end_line: Last line to include (inclusive).
        ref: Optional branch, tag, or commit (defaults to the default branch).
        max_bytes: Optional maximum size of the returned text in bytes;
            longer content is truncated with a notice.

    Returns:
        The file content as plain text.

    Examples:
        read_source_file("golang/go", "src/net/http/server.go")
        read_source_file("python/cpython", "Lib/http/client.py", start_line=20)
        read_source_file("kubernetes/kubernetes", "cmd/kubelet/app/server.go", 200, 250)
    """
    content = fetch_repo_files(
        repo_path=repo,
        file_path=path,
        start_line=start_line,
        end_line=end_line,
        ref=ref,
    )
    if content is None:
        return tr("errors.fetch_file_failed_for_path", path=path)
    return _truncate_text(content, max_bytes)


def list_repo_files(
    repo: str,
    path: str = "",
    ref: Optional[str] = None,
    limit: int = 200,
) -> _RepoFilesResult:
    """List files in a GitHub repository, optionally under a directory.

    Returns file paths and sizes from the repository's git tree, so agents
    can navigate beyond Markdown docs. "truncated" is true when GitHub
    returned an incomplete tree for a very large repository.

    Args:
        repo: Repository in owner/repo format.
        path: Optional directory prefix to filter by, e.g. "src".
        ref: Optional branch, tag, or commit.
        limit: Maximum number of entries to return (default 200).

    Returns:
        {"files": [{"path", "size"}], "total": N, "truncated": bool}
        or {"error": ...}. "total" counts all matches before the limit.

    Examples:
        list_repo_files("golang/go", "src/net/http")
        list_repo_files("facebook/react", ref="v18.2.0")
    """
    result = _github_repo_tree(repo, path=path, ref=ref, lang=default_lang())
    if result is None:
        return {"error": tr("errors.fetch_tree_failed")}
    limit = max(1, int(limit))
    return {
        "files": result["files"][:limit],
        "total": result["total"],
        "truncated": result["truncated"],
    }


def search_code(repo: str, query: str, limit: int = 10) -> _CodeSearchResult:
    """Search source code inside a GitHub repository.

    Uses the GitHub code search API, which requires authentication: set the
    GITHUB_TOKEN environment variable (or configure github_token). Without a
    token this returns an error — use search_wiki for docs-only search.

    Args:
        repo: Repository in owner/repo format.
        query: Code search query, e.g. "def main", "HttpClient".
        limit: Maximum number of results (default 10).

    Returns:
        {"results": [{"path", "name", "url", "fragments"}]} or {"error": ...}.

    Examples:
        search_code("golang/go", "func ListenAndServe")
    """
    if not github_token():
        return {"error": tr("errors.code_search_needs_token")}
    results = _github_search_code(repo, query, lang=default_lang(), limit=limit)
    if results is None:
        return {"error": tr("errors.search_failed")}
    return {"results": results}


def get_releases(repo: str, limit: int = 5) -> _ReleasesResult:
    """List recent releases of a GitHub repository.

    Returns tag, name, publish date, and (truncated) release notes for the
    most recent releases — useful for changelog questions. An empty list
    means the repository has no releases.

    Args:
        repo: Repository in owner/repo format.
        limit: Maximum number of releases to return (default 5).

    Returns:
        {"releases": [{"tag", "name", "published_at", "prerelease", "url",
        "body"}]} or {"error": ...}.

    Examples:
        get_releases("python/cpython")
        get_releases("nodejs/node", limit=10)
    """
    releases = _github_releases(repo, lang=default_lang(), limit=limit)
    if releases is None:
        return {"error": tr("errors.fetch_releases_failed")}
    return {"releases": releases}


def get_rate_limit() -> _RateLimitResult:
    """Show the current GitHub API rate-limit status.

    Reports remaining/total quota and reset time for the core, search, and
    code-search resources, plus whether a token is configured. Checking the
    rate limit does not consume quota.

    Returns:
        {"authenticated": bool, "resources": {"core": {"limit", "remaining",
        "reset"}, ...}} or {"error": ...}.
    """
    result = _github_rate_limit(lang=default_lang())
    if result is None:
        return {"error": tr("errors.fetch_rate_limit_failed")}
    return result


# ==========================================
# MCP Tools: AI Q&A (self-hosted RAG backend; registered only when configured)
# ==========================================


class _AskResult(TypedDict, total=False):
    answer: str
    reasoning: str
    repo_id: str
    error: str


def ask(repo: str, question: str, ref: Optional[str] = None) -> _AskResult:
    """Ask a question about a repository and get a grounded answer.

    Uses a self-hosted RAG backend that indexes the repo's documentation into
    embeddings and answers via an OpenAI-compatible LLM. The first question
    on a repo may take longer (auto-indexing); subsequent questions are fast.

    Args:
        repo: Repository as owner/repo (e.g. "golang/go"). A full GitHub URL
            or owner/repo@ref form is also accepted.
        question: The question to ask about the repo.
        ref: Optional branch/tag/commit (defaults to the repo's default branch).

    Returns:
        {"answer": str, "reasoning": str (optional thinking), "repo_id": str}
        or {"error": str} if the backend is unreachable.
    """
    import asyncio

    from zread.ai_client import create_talk, delete_talk, stream_message
    from zread.config import ai_api_key, ai_backend_url, ai_llm_model

    backend = ai_backend_url()
    if not backend:
        return {"error": "AI backend not configured (set ZREAD_AI_BACKEND_URL)."}

    parsed = parse_repo_url(repo)
    owner = parsed.get("owner", "")
    repo_name = parsed.get("repo", "")
    if not owner or not repo_name:
        return {"error": f"Could not parse repo from '{repo}'."}
    resolved_ref = ref or parsed.get("ref") or ""
    repo_id = f"{owner}/{repo_name}@{resolved_ref}" if resolved_ref else f"{owner}/{repo_name}"

    async def _run() -> _AskResult:
        import httpx as _httpx

        async with _httpx.AsyncClient() as client:
            try:
                talk_id = await create_talk(client, backend, repo_id, ai_api_key())
            except _httpx.HTTPError as exc:
                return {"error": f"Backend unreachable: {exc}", "repo_id": repo_id}
            try:
                answer_parts: list[str] = []
                reasoning_parts: list[str] = []
                async for ev in stream_message(
                    client, backend, talk_id, question, ai_llm_model() or None, ai_api_key()
                ):
                    if ev.is_error:
                        return {"error": ev.text or "stream error", "repo_id": repo_id}
                    if ev.text:
                        answer_parts.append(ev.text)
                    if ev.reasoning_content:
                        reasoning_parts.append(ev.reasoning_content)
                return {
                    "answer": "".join(answer_parts),
                    "reasoning": "".join(reasoning_parts),
                    "repo_id": repo_id,
                }
            finally:
                await delete_talk(client, backend, talk_id, ai_api_key())

    try:
        return asyncio.run(_run())
    except RuntimeError as exc:
        return {"error": str(exc), "repo_id": repo_id}


def chat(repo: str, question: str, ref: Optional[str] = None) -> _AskResult:
    """Conversational alias for ask(). Streams then returns the full answer.

    Kept as a distinct tool so agents can pick a "chat" affordance. Same
    behavior and return shape as ``ask``.
    """
    return ask(repo, question, ref)


# ==========================================
# MCP Resources: 资源访问
# ==========================================


def documentation_page_resource(owner: str, repo: str, page_slug: str) -> str:
    """文档页面资源"""
    return read_doc(f"{owner}/{repo}", page_slug)


def documentation_catalog_resource(owner: str, repo: str) -> str:
    """文档目录资源（JSON 字符串）"""
    return json.dumps(get_doc_outline(f"{owner}/{repo}"), ensure_ascii=False, indent=2)


def weekly_trending_resource() -> str:
    """本周热门仓库资源（JSON 字符串）"""
    result = get_trending(1)
    return json.dumps(result, ensure_ascii=False, indent=2)


# ==========================================
# MCP Prompts: 提示模板
# ==========================================


def analyze_project(repo_path: str) -> str:
    """
    分析项目架构和功能

    使用此提示让 AI 深度分析一个项目的架构、功能和使用方法。
    """
    return f"""请对仓库 {repo_path} 进行全面的技术解析：

1. **项目概述**
   - 项目定位和目标
   - 核心功能特性
   - 适用场景

2. **技术架构**
   - 技术栈分析
   - 核心模块划分
   - 架构设计亮点

3. **使用指南**
   - 快速开始步骤
   - 关键配置说明
   - 常见使用模式

4. **评价与建议**
   - 项目优缺点
   - 与其他方案对比
   - 推荐使用场景

请使用可用的工具获取文档信息，并基于实际内容进行分析。"""


def compare_projects(repo_a: str, repo_b: str) -> str:
    """
    对比两个项目

    对比分析两个项目的功能、架构和适用场景，帮助做出技术选型决策。
    """
    return f"""请对比分析以下两个项目：

**项目 A**: {repo_a}
**项目 B**: {repo_b}

对比维度：

1. **功能定位**
   - 各自解决的核心问题
   - 功能覆盖范围对比
   - 差异化特性

2. **技术实现**
   - 技术栈差异
   - 架构设计对比
   - 性能特点

3. **生态与社区**
   - Star 数和活跃度
   - 文档完善度
   - 社区支持

4. **选型建议**
   - 各自适用场景
   - 优缺点总结
   - 推荐选择

请获取两个项目的文档信息后进行客观对比。"""


def learn_project(repo_path: str) -> str:
    """
    学习项目使用

    帮助初学者快速理解和上手一个项目。
    """
    return f"""我想学习项目 {repo_path}，请帮我：

1. **快速了解**
   - 项目是做什么的
   - 主要使用场景
   - 核心价值

2. **入门指导**
   - 安装和配置步骤
   - 第一个示例
   - 常用命令

3. **深入学习**
   - 核心概念解释
   - 关键 API 介绍
   - 最佳实践

4. **实战建议**
   - 学习路径规划
   - 常见 pitfalls
   - 相关资源推荐

请基于项目文档提供系统的学习指导。"""


# 兼容旧公共 API：按 owner/path 查询仓库信息（CLI stat 用）
def _get_repo_info(owner_or_path: str, lang: str = "zh"):
    """查看仓库信息（GitHub 仓库 API）"""
    if "/" not in owner_or_path:
        raise ValueError(tr("errors.invalid_repo_format"))
    return _github_repo_metadata(owner_or_path, lang)
