# -*- coding: utf-8 -*-
"""GitHub 数据层：所有数据直接来自 GitHub（REST API + raw 文件），无外部 SaaS。

诊断信息一律输出到 stderr —— stdio 模式下 stdout 是 MCP 的 JSON-RPC 通道，
任何杂散输出都会破坏协议。
"""

import json
import re
import sys
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import arrow

from zread.cache import MISSING, TTLCache, http_cache
from zread.config import (
    USER_AGENT,
    default_lang,
    github_api_url,
    github_raw_url,
    github_token,
    tr,
)
from zread.http import httpx

# 作为"文档"的文件扩展名
_GH_DOC_EXTENSIONS = (".md", ".mdx", ".markdown", ".rst")
# 大纲最多收录的文档文件数量（防止超大仓库刷屏）
_GH_DOC_TREE_LIMIT = 500
# 文档搜索最多下载的文件数量
_GH_SEARCH_FILE_LIMIT = 30

# 进程内缓存：带 TTL 和容量上限（长驻共享服务不再无限增长 / 永不过期）
_GH_REPO_CACHE = TTLCache(maxsize=256, ttl=900.0)
_GH_TREE_CACHE = TTLCache(maxsize=16, ttl=900.0)

# 运行期计数（/healthz 暴露）
METRICS: Dict[str, int] = {
    "api_requests": 0,
    "raw_requests": 0,
    "cache_revalidated_304": 0,
    "rate_limited": 0,
    "request_errors": 0,
}


def _warn(message: str) -> None:
    """诊断输出统一走 stderr，避免污染 stdio MCP 通道。"""
    print(message, file=sys.stderr)


def _page_url(owner: str, repo_name: str, slug: str, ref: Optional[str] = None) -> str:
    """构建文档页面链接（GitHub 文件页，slug 即仓库内文件路径）"""
    return f"https://github.com/{owner}/{repo_name}/blob/{ref or 'HEAD'}/{slug}"


# ==========================================
# 仓库路径 / URL 解析
# ==========================================


def parse_repo_url(url_or_path: str) -> Dict[str, Any]:
    """
    统一解析多种格式的仓库 URL 或路径

    支持的格式:
        - owner/repo
        - owner/repo@ref（分支 / tag / commit）
        - owner/repo/file/path
        - https://github.com/owner/repo
        - https://github.com/owner/repo.git
        - https://github.com/owner/repo/file/path
        - https://github.com/owner/repo/blob/branch/file.py
        - https://github.com/owner/repo/blob/commit/file.py
        - https://raw.githubusercontent.com/owner/repo/branch/file.py
        - github.com/owner/repo/... （可省略协议）
        - 以上任意格式 + #L20 或 #L20-L30 行号

    返回:
        {
            "owner": str,           # 仓库所有者
            "repo": str,            # 仓库名
            "repo_path": str,       # owner/repo 格式
            "source": str,          # 来源类型: repo|github|raw_github
            "file_path": str|None,  # 文件路径（如果有）
            "ref": str|None,        # 分支 / tag / commit（如果有）
            "start_line": int|None, # 起始行号
            "end_line": int|None,   # 结束行号
        }
    """
    url = url_or_path.strip()
    result: Dict[str, Any] = {
        "owner": "",
        "repo": "",
        "repo_path": "",
        "source": "repo",
        "file_path": None,
        "ref": None,
        "start_line": None,
        "end_line": None,
    }

    # 提取行号标记 #L20-L30 或 #L20
    line_match = re.search(r"#L(\d+)(?:-L?(\d+))?$", url)
    if line_match:
        result["start_line"] = int(line_match.group(1))
        result["end_line"] = int(line_match.group(2)) if line_match.group(2) else None
        url = url[: line_match.start()]

    # 移除协议头
    if url.startswith("https://"):
        url = url[8:]
    elif url.startswith("http://"):
        url = url[7:]

    url = url.rstrip("/")

    def _clean_repo_name(name: str) -> str:
        return name[:-4] if name.endswith(".git") else name

    # 解析 raw.githubusercontent.com URL（第三段是 ref）
    if "raw.githubusercontent.com" in url:
        match = re.match(
            r"raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$", url
        )
        if match:
            result["owner"] = match.group(1)
            result["repo"] = _clean_repo_name(match.group(2))
            result["ref"] = match.group(3)
            result["file_path"] = match.group(4)
            result["repo_path"] = f"{result['owner']}/{result['repo']}"
            result["source"] = "raw_github"
            return result

    # 解析 github.com/blob|tree|raw URL（保留 ref，不再丢弃）
    if "github.com" in url:
        match = re.match(
            r"github\.com/([^/]+)/([^/]+)/(?:blob|raw|tree)/([^/]+)(?:/(.+))?$", url
        )
        if match:
            result["owner"] = match.group(1)
            result["repo"] = _clean_repo_name(match.group(2))
            result["ref"] = match.group(3)
            result["file_path"] = match.group(4) or None
            result["repo_path"] = f"{result['owner']}/{result['repo']}"
            result["source"] = "github"
            return result

    # 移除域名前缀
    if url.startswith("github.com/"):
        url = url[11:]
        result["source"] = "github"

    # 解析 owner/repo[@ref][/path] 格式
    parts = [p for p in url.split("/") if p != ""]
    if len(parts) >= 2:
        repo_part = parts[1]
        if "@" in repo_part:
            repo_part, _, ref_part = repo_part.partition("@")
            result["ref"] = ref_part or None
        result["owner"] = parts[0]
        result["repo"] = _clean_repo_name(repo_part)
        result["repo_path"] = f"{result['owner']}/{result['repo']}"
        if len(parts) > 2:
            result["file_path"] = "/".join(parts[2:])
        return result

    raise ValueError(tr("errors.parse_repo_url_failed", input=url_or_path))


# ==========================================
# 底层请求（含 ETag 磁盘缓存与速率限制提示）
# ==========================================


def _gh_headers() -> Dict[str, str]:
    """GitHub API 请求头（含可选 token）"""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _is_rate_limited(response: Any) -> bool:
    return (
        response is not None
        and response.status_code in (403, 429)
        and response.headers.get("x-ratelimit-remaining") == "0"
    )


def _rate_limit_message(response: Any, lang: str) -> str:
    message = tr("errors.github_rate_limited", lang)
    reset = response.headers.get("x-ratelimit-reset", "") if response is not None else ""
    if reset:
        try:
            reset_at = arrow.get(int(reset))
            when = reset_at.humanize(locale="zh" if lang == "zh" else "en")
            message += " " + tr("errors.rate_limit_resets", lang, when=when)
        except Exception:
            pass
    return message


def _cache_key(url: str, params: Optional[dict]) -> str:
    key = url
    if params:
        key += "?" + urllib.parse.urlencode(sorted(params.items()))
    # 带 token 与匿名的可见内容不同，缓存需区分
    if github_token():
        key += "#auth"
    return key


def _gh_api_get(
    path: str,
    params: Optional[dict] = None,
    lang: str = "zh",
    accept: Optional[str] = None,
) -> Optional[Any]:
    """请求 GitHub REST API：404 与限流返回 None 并向 stderr 提示。

    携带 If-None-Match 条件头：304 命中时直接返回磁盘缓存内容，不消耗配额。
    """
    url = f"{github_api_url()}{path}"
    headers = _gh_headers()
    if accept:
        headers["Accept"] = accept

    disk = http_cache()
    key = _cache_key(url, params)
    entry = disk.load(key) if disk else None
    if entry:
        headers["If-None-Match"] = entry["etag"]

    METRICS["api_requests"] += 1
    try:
        response = httpx.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 304 and entry is not None:
            METRICS["cache_revalidated_304"] += 1
            return json.loads(entry["body"])
        if response.status_code == 404:
            return None
        response.raise_for_status()
        if disk:
            etag = response.headers.get("etag", "")
            if etag:
                disk.store(key, etag, response.text)
        return response.json()
    except httpx.HTTPStatusError as e:
        if _is_rate_limited(e.response):
            METRICS["rate_limited"] += 1
            _warn(_rate_limit_message(e.response, lang))
        else:
            METRICS["request_errors"] += 1
            _warn(tr("errors.github_request_failed", lang, error=e))
        return None
    except httpx.RequestError as e:
        METRICS["request_errors"] += 1
        _warn(tr("errors.github_request_failed", lang, error=e))
        return None
    except json.JSONDecodeError as e:
        METRICS["request_errors"] += 1
        _warn(tr("errors.github_request_failed", lang, error=e))
        return None


def _gh_fetch_raw(
    owner: str,
    repo: str,
    file_path: str,
    lang: str = "zh",
    ref: Optional[str] = None,
) -> Optional[str]:
    """从 raw 域名获取文件内容（默认 HEAD 指向默认分支，可传 ref）。

    公开仓库无需认证；先匿名请求，404 时若配置了 token 再携带 token 重试
    （用于私有仓库），避免把 token 发给不需要它的公开地址。
    """
    url = f"{github_raw_url()}/{owner}/{repo}/{ref or 'HEAD'}/{file_path}"

    disk = http_cache()
    key = _cache_key(url, None)
    entry = disk.load(key) if disk else None
    base_headers: Dict[str, str] = {"User-Agent": USER_AGENT}
    if entry:
        base_headers["If-None-Match"] = entry["etag"]

    METRICS["raw_requests"] += 1
    try:
        response = httpx.get(url, headers=base_headers, timeout=30)
        token = github_token()
        if response.status_code == 404 and token:
            response = httpx.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Authorization": f"Bearer {token}",
                },
                timeout=30,
            )
        if response.status_code == 304 and entry is not None:
            METRICS["cache_revalidated_304"] += 1
            return entry["body"]
        if response.status_code == 404:
            return None
        response.raise_for_status()
        if disk:
            etag = response.headers.get("etag", "")
            if etag:
                disk.store(key, etag, response.text)
        return response.text
    except httpx.RequestError as e:
        METRICS["request_errors"] += 1
        _warn(tr("errors.github_request_failed", lang, error=e))
        return None
    except httpx.HTTPStatusError as e:
        if _is_rate_limited(e.response):
            METRICS["rate_limited"] += 1
            _warn(_rate_limit_message(e.response, lang))
        else:
            METRICS["request_errors"] += 1
            _warn(tr("errors.github_request_failed", lang, error=e))
        return None


# ==========================================
# 仓库元数据 / 文件树
# ==========================================


def _gh_repo_get(owner: str, repo: str, lang: str = "zh") -> Optional[Dict[str, Any]]:
    """获取 GitHub 仓库信息（进程内 TTL 缓存）"""
    key = f"{owner}/{repo}".lower()
    cached = _GH_REPO_CACHE.get(key)
    if cached is not MISSING:
        return cached
    value = _gh_api_get(f"/repos/{owner}/{repo}", lang=lang)
    _GH_REPO_CACHE.set(key, value)
    return value


def _gh_repo_item(gh: Dict[str, Any]) -> Dict[str, Any]:
    """把 GitHub API 的仓库对象映射为 zread 格式的仓库条目"""
    return {
        "url": gh.get("html_url", ""),
        "owner": (gh.get("owner") or {}).get("login", ""),
        "name": gh.get("name", ""),
        "description": gh.get("description") or "",
        "language": gh.get("language") or "",
        "topics": gh.get("topics", []) or [],
        "star_count": gh.get("stargazers_count", 0),
        "stars": gh.get("stargazers_count", 0),
    }


def _gh_full_tree(
    owner: str, repo: str, lang: str = "zh", ref: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """获取仓库完整文件树（blob 列表 + truncated 标记，进程内 TTL 缓存）。"""
    key = f"{owner}/{repo}@{ref or ''}".lower()
    cached = _GH_TREE_CACHE.get(key)
    if cached is not MISSING:
        return cached

    tree_ref = ref
    if not tree_ref:
        info = _gh_repo_get(owner, repo, lang)
        if not info:
            _GH_TREE_CACHE.set(key, None)
            return None
        tree_ref = info.get("default_branch") or "HEAD"

    data = _gh_api_get(
        f"/repos/{owner}/{repo}/git/trees/{urllib.parse.quote(tree_ref, safe='')}",
        params={"recursive": "1"},
        lang=lang,
    )
    if not data:
        _GH_TREE_CACHE.set(key, None)
        return None

    files = [
        {"path": item.get("path", ""), "size": item.get("size", 0)}
        for item in data.get("tree", [])
        if item.get("type") == "blob"
    ]
    truncated = bool(data.get("truncated"))
    if truncated:
        _warn(tr("errors.tree_truncated_warning", lang, repo=f"{owner}/{repo}"))
    result = {"files": files, "truncated": truncated}
    _GH_TREE_CACHE.set(key, result)
    return result


def _is_doc_path(path: str) -> bool:
    lower = path.lower()
    return lower.endswith(_GH_DOC_EXTENSIONS) or lower.rsplit("/", 1)[-1] == "readme"


def _gh_doc_rank(path: str) -> Tuple[int, str]:
    """文档排序：README 最前，其次根目录，再次 docs/ 目录，最后其余"""
    lower = path.lower()
    name = lower.rsplit("/", 1)[-1]
    if "/" not in path and name.startswith("readme"):
        rank = 0
    elif "/" not in path:
        rank = 1
    elif lower.startswith(("docs/", "doc/", "documentation/")):
        rank = 2
    else:
        rank = 3
    return (rank, lower)


def _gh_doc_tree(
    owner: str, repo: str, lang: str = "zh", ref: Optional[str] = None
) -> Optional[List[str]]:
    """列出仓库中的文档文件（Markdown/reST），按重要性排序"""
    tree = _gh_full_tree(owner, repo, lang, ref)
    if tree is None:
        return None
    paths = [f["path"] for f in tree["files"] if _is_doc_path(f["path"])]
    paths.sort(key=_gh_doc_rank)
    return paths[:_GH_DOC_TREE_LIMIT]


# ==========================================
# 高层数据函数
# ==========================================


def _github_repo_outline(
    repo_url_or_path: str, lang: str = "zh", ref: Optional[str] = None
) -> Optional[List[Dict[str, Any]]]:
    """仓库文档大纲：仓库自带的 Markdown 文件列表（slug = 文件路径）"""
    parsed = parse_repo_url(repo_url_or_path)
    owner, repo = parsed["owner"], parsed["repo"]
    tree = _gh_doc_tree(owner, repo, lang, ref or parsed.get("ref"))
    if tree is None:
        return None

    pages = []
    for order, path in enumerate(tree, 1):
        parts = path.split("/")
        section = parts[0] if len(parts) > 1 else ""
        group = "/".join(parts[1:-1])
        pages.append(
            {
                "page_id": path,
                "slug": path,
                "title": path,
                "topic": parts[-1],
                "group": group,
                "section": section,
                "order": order,
            }
        )
    return pages


def _github_fetch_markdown(
    repo_url_or_path: str, slug: str, lang: str = "zh", ref: Optional[str] = None
) -> Optional[str]:
    """读取文档：slug 即仓库内文件路径；默认 slug 映射到 README"""
    parsed = parse_repo_url(repo_url_or_path)
    owner, repo = parsed["owner"], parsed["repo"]
    use_ref = ref or parsed.get("ref")
    if slug == "1-overview":
        for candidate in ("README.md", "README.rst", "README", "readme.md"):
            content = _gh_fetch_raw(owner, repo, candidate, lang, ref=use_ref)
            if content is not None:
                return content
        return None
    return _gh_fetch_raw(owner, repo, slug, lang, ref=use_ref)


def _github_search_docs(
    repo_url_or_path: str, query: str, lang: str = "zh", ref: Optional[str] = None
) -> Optional[List[Dict[str, Any]]]:
    """文档搜索：下载仓库 Markdown 文件后按行匹配关键词"""
    parsed = parse_repo_url(repo_url_or_path)
    owner, repo = parsed["owner"], parsed["repo"]
    use_ref = ref or parsed.get("ref")
    tree = _gh_doc_tree(owner, repo, lang, use_ref)
    if tree is None:
        return None
    candidates = tree[:_GH_SEARCH_FILE_LIMIT]

    from concurrent.futures import ThreadPoolExecutor

    def fetch(path: str) -> Tuple[str, Optional[str]]:
        return (path, _gh_fetch_raw(owner, repo, path, lang, ref=use_ref))

    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = list(pool.map(fetch, candidates))

    needle = query.lower()
    results: List[Dict[str, Any]] = []
    for path, content in fetched:
        if not content:
            continue
        matches = []
        for line in content.splitlines():
            stripped = line.strip()
            if needle in stripped.lower():
                # 用 <em> 标记命中词，格式化层负责高亮或去除标签
                pattern = re.compile(re.escape(query), re.IGNORECASE)
                highlighted = pattern.sub(lambda m: f"<em>{m.group(0)}</em>", stripped)
                matches.append({"content": highlighted[:300]})
                if len(matches) >= 3:
                    break
        if matches:
            results.append({"title": path, "slug": path, "matches": matches})
    return results


def _github_search_repos(
    query: str, lang: str = "zh"
) -> Optional[List[Dict[str, Any]]]:
    """仓库搜索：GitHub search API"""
    data = _gh_api_get(
        "/search/repositories",
        params={"q": query, "per_page": 10},
        lang=lang,
    )
    if data is None:
        return None
    return [_gh_repo_item(item) for item in data.get("items", [])]


def _github_trending(
    lang: str = "zh", weeks: int = 4
) -> Optional[List[Dict[str, Any]]]:
    """热榜：按周查询 GitHub 上新建且星标最多的仓库"""
    groups: List[Dict[str, Any]] = []
    now = arrow.utcnow()
    for offset in range(max(1, weeks)):
        end = now.shift(weeks=-offset)
        start = end.shift(weeks=-1)
        query = (
            f"created:{start.format('YYYY-MM-DD')}..{end.format('YYYY-MM-DD')}"
            " stars:>10"
        )
        data = _gh_api_get(
            "/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": 10},
            lang=lang,
        )
        if data is None:
            break
        groups.append(
            {
                "title": tr("messages.direct_trending_title", lang),
                "time_span": {
                    "start": start.format("YYYY-MM-DD"),
                    "end": end.format("YYYY-MM-DD"),
                },
                "repos": [_gh_repo_item(item) for item in data.get("items", [])],
            }
        )
    return groups or None


def _github_recommend(topic: str = "", lang: str = "zh") -> Optional[Dict[str, Any]]:
    """随机推荐：GitHub search 结果中随机抽取"""
    import random

    query = f"topic:{topic} stars:>100" if topic else "stars:>5000"
    data = _gh_api_get(
        "/search/repositories",
        params={
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": 30,
            "page": random.randint(1, 3),
        },
        lang=lang,
    )
    if data is None:
        return None
    items = [_gh_repo_item(item) for item in data.get("items", [])]
    random.shuffle(items)
    return {"topics": [topic] if topic else [], "repos": items[:10]}


def _github_repo_metadata(
    repo_url_or_path: str, lang: str = "zh"
) -> Optional[Dict[str, Any]]:
    """仓库信息：GitHub repos API 映射为通用元数据格式"""
    parsed = parse_repo_url(repo_url_or_path)
    owner, repo = parsed["owner"], parsed["repo"]
    gh = _gh_repo_get(owner, repo, lang)
    if gh is None:
        return {"_error": "not_found"}

    item = _gh_repo_item(gh)
    item["status"] = "success"
    pushed_at = gh.get("pushed_at")
    if pushed_at:
        try:
            item["last_commit"] = {"when": arrow.get(pushed_at).int_timestamp}
        except Exception:
            pass
    gh_license = gh.get("license")
    if isinstance(gh_license, dict):
        item["license"] = gh_license
    default_branch = gh.get("default_branch")
    if default_branch:
        item["default_branch"] = default_branch
    return item


def _github_fetch_file_meta(
    repo_path: str,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    lang: str = "zh",
    ref: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """读取文件：raw 下载 + 本地行号截取"""
    parsed = parse_repo_url(repo_path)
    owner, repo = parsed["owner"], parsed["repo"]
    content = _gh_fetch_raw(owner, repo, file_path, lang, ref=ref or parsed.get("ref"))
    if content is None:
        _warn(tr("errors.file_not_found_or_inaccessible", lang))
        return None

    lines = content.split("\n")
    total_lines = len(lines)
    size = len(content.encode("utf-8"))

    if start_line is None and end_line is None:
        return {
            "content": content,
            "total_lines": total_lines,
            "size": size,
            "file_path": file_path,
            "start_line": 1,
            "end_line": total_lines,
            "is_snippet": False,
        }

    start_idx = max(0, (start_line or 1) - 1)
    end_idx = min(total_lines, end_line) if end_line is not None else total_lines
    selected = "\n".join(lines[start_idx:end_idx]) if start_idx < end_idx else ""
    return {
        "content": selected,
        "total_lines": total_lines,
        "size": size,
        "file_path": file_path,
        "start_line": start_line or 1,
        "end_line": end_line or total_lines,
        "is_snippet": False,
    }


# ==========================================
# 新增数据端点：文件树 / 代码搜索 / Releases / 速率限制
# ==========================================


def _github_repo_tree(
    repo_url_or_path: str,
    path: str = "",
    ref: Optional[str] = None,
    lang: str = "zh",
) -> Optional[Dict[str, Any]]:
    """列出仓库文件（可按路径前缀过滤）。返回 {files, total, truncated}。"""
    parsed = parse_repo_url(repo_url_or_path)
    owner, repo = parsed["owner"], parsed["repo"]
    tree = _gh_full_tree(owner, repo, lang, ref or parsed.get("ref"))
    if tree is None:
        return None

    prefix = (path or "").strip("/")
    if prefix:
        needle = prefix + "/"
        files = [
            f
            for f in tree["files"]
            if f["path"] == prefix or f["path"].startswith(needle)
        ]
    else:
        files = tree["files"]
    return {"files": files, "total": len(files), "truncated": tree["truncated"]}


def _github_search_code(
    repo_url_or_path: str, query: str, lang: str = "zh", limit: int = 10
) -> Optional[List[Dict[str, Any]]]:
    """仓库内代码搜索（GitHub code search API，需要 token）。"""
    parsed = parse_repo_url(repo_url_or_path)
    owner, repo = parsed["owner"], parsed["repo"]
    data = _gh_api_get(
        "/search/code",
        params={"q": f"{query} repo:{owner}/{repo}", "per_page": max(1, limit)},
        lang=lang,
        accept="application/vnd.github.text-match+json",
    )
    if data is None:
        return None

    results = []
    for item in data.get("items", []):
        fragments = []
        for tm in item.get("text_matches", []) or []:
            fragment = (tm.get("fragment") or "").strip()
            if fragment:
                fragments.append(fragment[:300])
        results.append(
            {
                "path": item.get("path", ""),
                "name": item.get("name", ""),
                "url": item.get("html_url", ""),
                "fragments": fragments[:3],
            }
        )
    return results


def _github_releases(
    repo_url_or_path: str, lang: str = "zh", limit: int = 5
) -> Optional[List[Dict[str, Any]]]:
    """仓库 Releases 列表（最新在前）。"""
    parsed = parse_repo_url(repo_url_or_path)
    owner, repo = parsed["owner"], parsed["repo"]
    data = _gh_api_get(
        f"/repos/{owner}/{repo}/releases",
        params={"per_page": max(1, limit)},
        lang=lang,
    )
    if data is None:
        return None

    releases = []
    for item in data:
        body = (item.get("body") or "").strip()
        if len(body) > 2000:
            body = body[:2000] + "…"
        releases.append(
            {
                "tag": item.get("tag_name", ""),
                "name": item.get("name") or item.get("tag_name", ""),
                "published_at": item.get("published_at") or "",
                "prerelease": bool(item.get("prerelease")),
                "url": item.get("html_url", ""),
                "body": body,
            }
        )
    return releases


def _github_rate_limit(lang: str = "zh") -> Optional[Dict[str, Any]]:
    """当前 GitHub API 配额（/rate_limit 本身不消耗配额）。"""
    data = _gh_api_get("/rate_limit", lang=lang)
    if data is None:
        return None
    resources = data.get("resources", {}) or {}
    result: Dict[str, Any] = {"authenticated": bool(github_token()), "resources": {}}
    for name in ("core", "search", "code_search"):
        res = resources.get(name)
        if not isinstance(res, dict):
            continue
        reset_ts = res.get("reset")
        reset_iso = ""
        if reset_ts:
            try:
                reset_iso = arrow.get(int(reset_ts)).isoformat()
            except Exception:
                pass
        result["resources"][name] = {
            "limit": res.get("limit", 0),
            "remaining": res.get("remaining", 0),
            "reset": reset_iso,
        }
    return result


# ==========================================
# 公共 API（保持原有函数签名，新增可选 ref）
# ==========================================


def fetch_repo_outline(
    repo_url_or_path: str, lang: str = "zh", ref: Optional[str] = None
) -> Optional[List[Dict[str, Any]]]:
    """
    获取仓库文档目录（outline）——仓库自带的 Markdown 文件列表

    :param repo_url_or_path: 支持格式 owner/repo 或 https://github.com/owner/repo
    :param lang: 语言，可选 "zh" 或 "en"
    :param ref: 可选分支 / tag / commit
    :return: pages 列表（slug 即文件路径），失败返回 None
    """
    return _github_repo_outline(repo_url_or_path, lang, ref)


def fetch_markdown(
    repo_url_or_path: str, slug: str, lang: str = "zh", ref: Optional[str] = None
) -> Optional[str]:
    """
    获取文档正文——slug 即仓库内 Markdown 文件路径

    :param repo_url_or_path: 支持格式 owner/repo 或完整 URL
    :param slug: 文件路径（"1-overview" 映射到 README）
    :param lang: 语言，默认 'zh'
    :param ref: 可选分支 / tag / commit
    :return: Markdown 字符串 或 None
    """
    return _github_fetch_markdown(repo_url_or_path, slug, lang, ref)


def recommend_repos(topic: str = "", lang: str = "zh") -> Optional[Dict[str, Any]]:
    """
    随机推荐仓库 (按 GitHub topic 标签筛选)
    :param topic: 可选的 GitHub topic 标签，如 "awesome-list", "python", "rust"
    :param lang: 语言，可选 "zh" 或 "en"
    :return: dict 包含 topics 和 repos，或 None
    """
    return _github_recommend(topic, lang)


def get_trending_repos(
    lang: str = "zh", weeks: int = 4
) -> Optional[List[Dict[str, Any]]]:
    """获取每周热榜（GitHub 上按周新建、按星标排序）"""
    return _github_trending(lang, weeks)


def fetch_repo_metadata(repo_url_or_path: str) -> Optional[Dict[str, Any]]:
    """
    获取仓库元数据（直接来自 GitHub 仓库 API）

    :return: 仓库信息字典（未找到时为 {"_error": "not_found"}），失败返回 None
    """
    return _github_repo_metadata(repo_url_or_path, default_lang())


def fetch_repo_files_with_meta(
    repo_path: str,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    token: Optional[str] = None,
    ref: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    获取仓库内的文件内容及其元数据（raw 下载 + 本地行号截取）

    :return: 包含 content, total_lines, size 等信息的字典，失败返回 None
    """
    return _github_fetch_file_meta(
        repo_path, file_path, start_line, end_line, default_lang(), ref
    )


def fetch_repo_files(
    repo_path: str,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    token: Optional[str] = None,
    ref: Optional[str] = None,
) -> Optional[str]:
    """
    获取仓库内的文件内容（兼容 MCP 的简化接口）

    :param repo_path: 仓库路径，支持格式: owner/repo 或 https://github.com/owner/repo
    :param file_path: 文件路径，如 "src/config.ts"
    :param start_line: 可选，开始行号（包含），从 1 开始计数
    :param end_line: 可选，结束行号（包含）
    :param token: 保留参数（历史兼容），实际 token 取自环境 / 配置
    :param ref: 可选分支 / tag / commit
    :return: 指定行范围的纯文本内容，失败返回 None
    """
    result = fetch_repo_files_with_meta(
        repo_path, file_path, start_line, end_line, token, ref
    )
    return result["content"] if result else None
