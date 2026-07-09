# -*- coding: utf-8 -*-
"""Export 功能：导出仓库文档（可含源码）到本地，生成 llms.txt / llms-full.txt。"""

import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from zread.config import DEFAULT_HEADERS, USER_AGENT, github_raw_url, github_token, tr
from zread.github import (
    _github_repo_tree,
    _is_doc_path,
    _page_url,
    fetch_repo_metadata,
    fetch_repo_outline,
    parse_repo_url,
)
from zread.http import httpx

# --include-source 的保护上限：跳过超大文件与二进制文件
_SOURCE_FILE_LIMIT = 500
_SOURCE_MAX_BYTES = 512 * 1024
_BINARY_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".svgz",
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".mov", ".avi", ".webm", ".ogg", ".wav", ".flac",
    ".so", ".dylib", ".dll", ".exe", ".bin", ".dat", ".db", ".sqlite",
    ".jar", ".class", ".pyc", ".pyd", ".wasm", ".o", ".a",
)


def _front_matter(owner: str, repo_name: str, slug: str, ref: Optional[str]) -> str:
    """为导出的文档页生成 YAML front matter。"""
    return "\n".join(
        [
            "---",
            f"path: {slug}",
            f"repository: {owner}/{repo_name}",
            f"ref: {ref or 'HEAD'}",
            f"source: {_page_url(owner, repo_name, slug, ref)}",
            "---",
            "",
            "",
        ]
    )


async def _fetch_page_async(
    client: Any,
    repo: str,
    page: Dict[str, Any],
    lang: str,
    output_dir: Path,
    progress_cb: Optional[Callable[[], None]] = None,
    ref: Optional[str] = None,
    save: bool = True,
    front_matter: bool = False,
) -> Dict[str, Any]:
    """异步获取单个页面内容并（可选）保存"""
    slug = page.get("slug", "")

    if not slug:
        return {"success": False, "page": page, "error": "no slug"}

    # slug 即文件路径，从 raw 下载并保留目录结构
    try:
        parsed = parse_repo_url(repo)
        owner, repo_name = parsed["owner"], parsed["repo"]
        url = f"{github_raw_url()}/{owner}/{repo_name}/{ref or 'HEAD'}/{slug}"
        response = await client.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=30.0
        )
        token = github_token()
        if response.status_code == 404 and token:
            response = await client.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Authorization": f"Bearer {token}",
                },
                timeout=30.0,
            )
        response.raise_for_status()
        md_content = response.text

        file_path = None
        if save:
            file_path = output_dir / slug
            # 防路径穿越：slug 来自远端 tree 响应（API 端点可被配置覆盖），
            # 绝不允许写出 output_dir 之外
            root = output_dir.resolve()
            resolved = file_path.resolve()
            if resolved == root or not resolved.is_relative_to(root):
                if progress_cb:
                    progress_cb()
                return {"success": False, "page": page, "error": "unsafe path"}
            file_path.parent.mkdir(parents=True, exist_ok=True)
            saved_content = md_content
            if front_matter:
                saved_content = (
                    _front_matter(owner, repo_name, slug, ref) + md_content
                )
            file_path.write_text(saved_content, encoding="utf-8")

        if progress_cb:
            progress_cb()
        return {
            "success": True,
            "page": page,
            "content": md_content,
            "file_path": file_path,
        }
    except Exception as e:
        if progress_cb:
            progress_cb()
        return {"success": False, "page": page, "error": str(e)}


def _looks_binary(path: str) -> bool:
    return path.lower().endswith(_BINARY_EXTENSIONS)


def _select_source_files(repo: str, ref: Optional[str], lang: str) -> List[str]:
    """挑选 --include-source 要下载的源码文件（排除文档、二进制与超大文件）。"""
    tree = _github_repo_tree(repo, ref=ref, lang=lang)
    if not tree:
        return []
    picked = []
    for entry in tree["files"]:
        path = entry["path"]
        if _is_doc_path(path) or _looks_binary(path):
            continue
        size = entry.get("size") or 0
        if size > _SOURCE_MAX_BYTES:
            continue
        picked.append(path)
        if len(picked) >= _SOURCE_FILE_LIMIT:
            break
    return picked


async def _export_repo_async(
    repo: str,
    output_dir: Path,
    lang: str,
    concurrency: int,
    progress: Optional[Any] = None,
    task_id: Optional[int] = None,
    pages: Optional[List[Dict[str, Any]]] = None,
    ref: Optional[str] = None,
    include_source: bool = False,
    front_matter: bool = False,
    llms_only: bool = False,
) -> Dict[str, Any]:
    """异步导出仓库文档"""
    if pages is None:
        pages = fetch_repo_outline(repo, lang=lang, ref=ref)
    if not pages:
        return {"success": False, "error": tr("errors.fetch_outline", lang)}

    parsed = parse_repo_url(repo)
    owner, repo_name = parsed["owner"], parsed["repo"]
    ref = ref or parsed.get("ref")

    repo_dir = output_dir / f"{owner}-{repo_name}"
    repo_dir.mkdir(parents=True, exist_ok=True)

    # llms_only 模式：不落地单页文件，只在内存里聚合生成 llms*.txt
    save_pages = not llms_only

    source_paths: List[str] = []
    if include_source and not llms_only:
        source_paths = _select_source_files(repo, ref, lang)
    source_pages = [
        {"slug": path, "topic": path.rsplit("/", 1)[-1], "group": "", "section": ""}
        for path in source_paths
    ]

    total_items = len(pages) + len(source_pages)
    if progress and task_id is not None and source_pages:
        progress.update(task_id, total=total_items)
    completed = 0

    def make_progress_cb():
        def cb():
            nonlocal completed
            completed += 1
            if progress and task_id is not None:
                progress.update(task_id, completed=completed)

        return cb

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        headers=DEFAULT_HEADERS,
        limits=httpx.Limits(
            max_connections=concurrency, max_keepalive_connections=concurrency
        ),
    ) as client:
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_with_limit(page, is_doc: bool):
            async with semaphore:
                return await _fetch_page_async(
                    client,
                    repo,
                    page,
                    lang,
                    repo_dir,
                    make_progress_cb(),
                    ref=ref,
                    save=save_pages,
                    # 源码文件不加 front matter，避免破坏代码
                    front_matter=front_matter and is_doc,
                )

        tasks = [fetch_with_limit(page, True) for page in pages]
        tasks += [fetch_with_limit(page, False) for page in source_pages]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    doc_results = results[: len(pages)]
    source_results = results[len(pages):]

    successful = []
    failed = []
    for r in doc_results:
        if isinstance(r, Exception):
            failed.append({"error": str(r)})
        elif r.get("success"):
            successful.append(r)
        else:
            failed.append(r)

    source_success = sum(
        1
        for r in source_results
        if not isinstance(r, Exception) and r.get("success")
    )

    repo_info = fetch_repo_metadata(repo)
    if repo_info and repo_info.get("_error"):
        repo_info = None

    llms_full_file = _generate_llms_full_txt(
        repo_dir, owner, repo_name, pages, successful, repo_info
    )

    # llms_only 模式下单页文件不存在，llms.txt 使用远程链接
    llms_file = _generate_llms_txt(
        repo_dir,
        owner,
        repo_name,
        pages,
        successful,
        repo_info,
        local_links=save_pages,
    )

    return {
        "success": True,
        "repo_dir": repo_dir,
        "total": total_items,
        "successful": len(successful),
        "failed": len(failed),
        "source_files": source_success,
        "llms_file": llms_file,
        "llms_full_file": llms_full_file,
        "failed_pages": failed,
    }


def _format_repo_info_for_llms(repo_info: Dict[str, Any]) -> str:
    """格式化仓库信息为文本"""
    if not repo_info:
        return ""

    lines = []
    owner = repo_info.get("owner", "")
    name = repo_info.get("name", "")
    description = repo_info.get("description", "")
    stars = repo_info.get("stars", 0)
    language = repo_info.get("language", "")
    topics = repo_info.get("topics", [])
    license_info = repo_info.get("license", {})
    license_name = (
        license_info.get("name", "") if isinstance(license_info, dict) else ""
    )

    lines.append(f"Repository: {owner}/{name}")
    if description:
        lines.append(f"Description: {description}")
    if stars:
        lines.append(f"Stars: {stars}")
    if language:
        lines.append(f"Language: {language}")
    if topics:
        lines.append(f"Topics: {', '.join(topics)}")
    if license_name:
        lines.append(f"License: {license_name}")

    return "\n".join(lines)


def _organize_pages(
    pages: List[Dict[str, Any]]
) -> "Dict[str, Dict[str, List[Dict]]]":
    """按 section -> group 组织页面。"""
    sections: Dict[str, Dict[str, List[Dict]]] = {}
    for page in pages:
        section = page.get("section", "") or "General"
        group = page.get("group", "")
        topic = page.get("topic", "")
        slug = page.get("slug", "")

        if section not in sections:
            sections[section] = {}

        group_key = group or "_default"
        if group_key not in sections[section]:
            sections[section][group_key] = []

        sections[section][group_key].append(
            {
                "topic": topic or page.get("title", ""),
                "slug": slug,
            }
        )
    return sections


def _generate_llms_full_txt(
    repo_dir: Path,
    owner: str,
    repo_name: str,
    pages: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    repo_info: Optional[Dict[str, Any]],
) -> Path:
    """生成 llms-full.txt 文件（包含完整内容，使用远程链接）"""
    llms_file = repo_dir / "llms-full.txt"

    content_map = {
        r["page"]["slug"]: r["content"] for r in results if r.get("content")
    }
    sections = _organize_pages(pages)

    lines = []
    github_url = f"https://github.com/{owner}/{repo_name}"

    lines.append(github_url)
    lines.append("")

    if repo_info:
        repo_info_text = _format_repo_info_for_llms(repo_info)
        if repo_info_text:
            lines.append(repo_info_text)
            lines.append("")

    lines.append("")

    for section_name, groups in sections.items():
        lines.append(f"# {section_name}")
        lines.append("")

        def _append_page(slug: str) -> None:
            if slug in content_map:
                lines.append(f"- [{slug}]({_page_url(owner, repo_name, slug)})")
                lines.append("")
                lines.append(content_map[slug])
                lines.append("")
                lines.append("---")
                lines.append("")

        if "_default" in groups:
            for page_info in groups["_default"]:
                _append_page(page_info["slug"])

        for group_name, group_pages in groups.items():
            if group_name == "_default":
                continue
            lines.append(f"## {group_name}")
            lines.append("")
            for page_info in group_pages:
                _append_page(page_info["slug"])

        lines.append("")

    llms_file.write_text("\n".join(lines), encoding="utf-8")
    return llms_file


def _generate_llms_txt(
    repo_dir: Path,
    owner: str,
    repo_name: str,
    pages: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    repo_info: Optional[Dict[str, Any]],
    local_links: bool = True,
) -> Path:
    """生成 llms.txt 文件（目录索引；本地相对链接或远程链接）"""
    llms_file = repo_dir / "llms.txt"

    content_map = {
        r["page"]["slug"]: r["content"] for r in results if r.get("content")
    }
    sections = _organize_pages(pages)

    lines = []
    github_url = f"https://github.com/{owner}/{repo_name}"

    lines.append(github_url)
    lines.append("")

    if repo_info:
        repo_info_text = _format_repo_info_for_llms(repo_info)
        if repo_info_text:
            lines.append(repo_info_text)
            lines.append("")

    lines.append("")

    def _link_for(slug: str) -> str:
        # slug 已含扩展名（就是仓库内文件路径），本地链接直接指向落地文件；
        # 此前的 "./{slug}.md" 会生成 README.md.md 这类不存在的目标
        if local_links:
            return f"- [{slug}](./{slug})"
        return f"- [{slug}]({_page_url(owner, repo_name, slug)})"

    for section_name, groups in sections.items():
        lines.append(f"# {section_name}")
        lines.append("")

        if "_default" in groups:
            for page_info in groups["_default"]:
                slug = page_info["slug"]
                if slug in content_map:
                    lines.append(_link_for(slug))

        for group_name, group_pages in groups.items():
            if group_name == "_default":
                continue
            lines.append(f"## {group_name}")
            lines.append("")

            for page_info in group_pages:
                slug = page_info["slug"]
                if slug in content_map:
                    lines.append(_link_for(slug))

            lines.append("")

        lines.append("")

    llms_file.write_text("\n".join(lines), encoding="utf-8")
    return llms_file
