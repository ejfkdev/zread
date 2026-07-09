# -*- coding: utf-8 -*-
"""渲染层：Rich / 纯文本格式化、Markdown 图片渲染、终端主题。"""

import asyncio
import os
import re
from io import BytesIO
from typing import Any, Callable, Dict, List, Optional

import arrow
import darkdetect
import typer
from rich.console import Console
from rich.markdown import Markdown, MarkdownElement
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Column, Table
from rich.text import Text
from rich.tree import Tree

from zread.config import tr
from zread.github import _page_url, parse_repo_url
from zread.http import httpx

# 全局图片缓存
_IMAGE_CACHE: Dict[str, Any] = {}
_TEXTUAL_IMAGE_CLASS: Any = None
_PIL_IMAGE_CLASS: Any = None


def _get_syntax_theme() -> str:
    """获取当前系统主题对应的语法高亮主题"""
    try:
        if darkdetect.isDark():
            return "github-dark"
    except Exception:
        pass
    return "default"


def _get_search_highlight_style() -> str:
    """获取搜索结果高亮样式，根据系统主题自动切换"""
    try:
        if darkdetect.isDark():
            return "white on color(236)"  # 暗色主题：白字深灰底
    except Exception:
        pass
    return "black on cornsilk1"  # 明亮主题：黑字米白底


# ==========================================
# Markdown 图片渲染（可选依赖 textual-image）
# ==========================================


class MarkdownImage(MarkdownElement):
    """自定义 Markdown 图片元素，支持在终端渲染图片"""

    new_line = True

    @classmethod
    def create(cls, markdown, token):
        return cls(token)

    def __init__(self, token):
        self.uri = token.attrs.get("src", "")
        self.alt_text = token.content or ""
        self.raw_markdown = f"![{self.alt_text}]({self.uri})"
        super().__init__()

    def __rich_console__(self, console, options):
        if not self.uri:
            yield Text(self.raw_markdown, style="dim")
            return

        if self.uri in _IMAGE_CACHE and _IMAGE_CACHE[self.uri] is not None:
            pil_img = _IMAGE_CACHE[self.uri]
            try:
                textual_image_class = _get_textual_image_class()
                if textual_image_class is None:
                    raise RuntimeError("textual-image unavailable")
                yield textual_image_class(pil_img, width="80%", height="40%")
            except Exception:
                yield Text(self.raw_markdown, style="dim")
        else:
            yield Text(self.raw_markdown, style="dim")


class ImageAwareMarkdown(Markdown):
    """支持图片渲染的 Markdown 类"""

    elements = Markdown.elements.copy()
    elements["image"] = MarkdownImage

    def __init__(self, markup: str, code_theme: str = "default", **kwargs):
        super().__init__(markup, code_theme=code_theme, **kwargs)


def _get_pil_image_class():
    """按需导入 PIL.Image，减少普通 CLI 启动开销。"""
    global _PIL_IMAGE_CLASS
    if _PIL_IMAGE_CLASS is None:
        from PIL import Image as pil_image_class

        _PIL_IMAGE_CLASS = pil_image_class
    return _PIL_IMAGE_CLASS


def _get_textual_image_class():
    """按需导入 textual-image，减少普通 CLI 启动开销。"""
    global _TEXTUAL_IMAGE_CLASS
    if _TEXTUAL_IMAGE_CLASS is None:
        try:
            from textual_image.renderable import Image as textual_image_class
        except Exception:
            _TEXTUAL_IMAGE_CLASS = False
            return None
        _TEXTUAL_IMAGE_CLASS = textual_image_class
    return None if _TEXTUAL_IMAGE_CLASS is False else _TEXTUAL_IMAGE_CLASS


def _fetch_image_sync(url: str) -> Optional[bytes]:
    """同步获取图片数据（使用 httpx，用于线程池执行）"""
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=2.0,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content
    except Exception:
        return None


async def _preload_images_async(md_text: str) -> None:
    """异步并行预加载 markdown 中的图片"""
    urls = re.findall(r"!\[.*?\]\((http[s]?://.*?)\)", md_text)
    urls_to_fetch = [url for url in urls if url not in _IMAGE_CACHE]

    if not urls_to_fetch:
        return

    loop = asyncio.get_running_loop()

    async def fetch_one(url: str) -> None:
        try:
            content = await asyncio.wait_for(
                loop.run_in_executor(None, _fetch_image_sync, url), timeout=2.0
            )
            if content:
                pil_image_class = _get_pil_image_class()
                _IMAGE_CACHE[url] = pil_image_class.open(BytesIO(content))
            else:
                _IMAGE_CACHE[url] = None
        except Exception:
            _IMAGE_CACHE[url] = None

    await asyncio.gather(*(fetch_one(url) for url in urls_to_fetch))


def _preload_images_sync(md_text: str) -> None:
    """预加载 markdown 中的图片（CLI 同步上下文）"""
    urls = re.findall(r"!\[.*?\]\((http[s]?://.*?)\)", md_text)
    urls_to_fetch = [url for url in urls if url not in _IMAGE_CACHE]

    if not urls_to_fetch:
        return

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # 没有运行中的事件循环，直接运行异步预加载
        try:
            asyncio.run(_preload_images_async(md_text))
            return
        except Exception:
            pass

    # 已在事件循环内（或异步执行失败）：同步串行获取，保证渲染前图片就绪
    for url in urls_to_fetch:
        try:
            content = _fetch_image_sync(url)
            if content:
                pil_image_class = _get_pil_image_class()
                _IMAGE_CACHE[url] = pil_image_class.open(BytesIO(content))
            else:
                _IMAGE_CACHE[url] = None
        except Exception:
            _IMAGE_CACHE[url] = None


# ==========================================
# 通用仓库列表格式化（trending/search/discover/find 共用）
# ==========================================


def _format_repo_items_plain(
    items: List[Dict], lang: str = "zh", start_idx: int = 1
) -> List[str]:
    """格式化单个仓库项为纯文本行列表"""
    lines = []
    for idx, item in enumerate(items, start_idx):
        url = item.get(
            "url", f"https://github.com/{item.get('owner')}/{item.get('name')}"
        )
        desc = (
            item.get("description_zh", "")
            if lang == "zh"
            else item.get("description", "")
        )
        if not desc:
            desc = item.get("description", tr("messages.no_description", lang))
        desc = desc.replace("\n", " ")

        star_count = item.get("star_count", 0)
        url_line = f"{url}"
        if star_count:
            url_line += f"  🌟 {star_count:,}"
        lines.append(f"{idx}. {url_line}")

        if desc:
            lines.append(f"   {desc}")

        language = item.get("language", "")
        topics = item.get("topics", [])
        lang_topic_parts = []
        if language:
            lang_topic_parts.append(f"🔤 {language}")
        if topics:
            lang_topic_parts.append(f"🏷️ {', '.join(topics)}")
        if lang_topic_parts:
            lines.append(f"   {'  '.join(lang_topic_parts)}")

        lines.append("")
    return lines


def _format_single_repo_info(
    data: Dict[str, Any], lang: str = "zh", show_status: bool = True
) -> Text:
    """
    统一格式化单个仓库信息

    格式：
    - URL (一半暗一半蓝) + 🌟 + 星标数量
    - 描述
    - 语言 + topics
    - 最后提交 / 文档更新时间
    """
    lines = []

    url = data.get("url", "")
    if not url:
        url = f"https://github.com/{data.get('owner', '')}/{data.get('name', '')}"

    url_text = Text()
    link_style = f"link {url}"
    if "/" in url:
        parts = url.split("/")
        if len(parts) >= 2:
            base = "/".join(parts[:-2]) + "/" if len(parts) > 2 else ""
            owner_repo = "/".join(parts[-2:])
            if base:
                url_text.append(base, style=f"dim {link_style}")
            url_text.append(owner_repo, style=f"bold blue {link_style}")
        else:
            url_text.append(url, style=f"bold blue {link_style}")
    else:
        url_text.append(url, style=f"bold blue {link_style}")

    star_count = data.get("star_count", 0)
    if star_count:
        url_text.append(f"  🌟 {star_count:,}", style="yellow")

    lines.append(url_text)

    desc_key = "description_zh" if lang == "zh" else "description"
    description = data.get(desc_key, "") or data.get("description", "")
    if description:
        lines.append(Text(description.strip()))

    language = data.get("language", "")
    topics = data.get("topics", [])
    lang_topic_line = Text()
    if language:
        lang_topic_line.append(f"🔤 {language}", style="green")
    if topics:
        if language:
            lang_topic_line.append("  ")
        lang_topic_line.append("🏷️ " + ", ".join(topics), style="dim")
    if language or topics:
        lines.append(lang_topic_line)

    if show_status:
        last_commit = data.get("last_commit", {})
        last_commit_when = last_commit.get("when", 0)

        parts = []
        if last_commit_when:
            try:
                commit_time = arrow.get(last_commit_when)
                commit_ago = commit_time.humanize(
                    locale=lang if lang == "zh" else "en"
                )
                if lang == "zh":
                    parts.append(f"📝 {commit_ago}提交代码")
                else:
                    parts.append(f"📝 code committed {commit_ago}")
            except Exception:
                pass

        default_branch = data.get("default_branch", "")
        if default_branch:
            parts.append(f"🌿 {default_branch}")

        if parts:
            status_line = Text()
            status_line.append("  |  ".join(parts), style="yellow")
            lines.append(status_line)

    return Text("\n").join(lines)


def _format_repo_items_rich_table(
    items: List[Dict], lang: str, start_idx: int = 1
) -> Table:
    """创建 Rich Table 用于渲染仓库列表"""
    table = Table(
        Column(justify="right"),
        Column(justify="left"),
        show_header=False,
        box=None,
        padding=(0, 2),
    )

    for idx, item in enumerate(items, start_idx):
        cell_content = _format_single_repo_info(item, lang, show_status=False)
        table.add_row(str(idx), cell_content)
        if idx < len(items) + start_idx - 1:
            table.add_row("", "")

    return table


# --- Trending 格式化 ---
def _format_trending_plain(data: List[Dict], lang: str) -> str:
    """纯文本格式输出 trending（编号跨周连续递增）"""
    lines = []
    next_idx = 1
    for group in data:
        title = group.get("title", "Trending")
        time_span = group.get("time_span", {})
        lines.append(f"# {title}")
        if time_span:
            lines.append(f"# {time_span.get('start', '')} - {time_span.get('end', '')}")
        lines.append("")

        repos = group.get("repos", [])
        lines.extend(_format_repo_items_plain(repos, lang, start_idx=next_idx))
        next_idx += len(repos)
    return "\n".join(lines)


def _format_trending_rich(data: List[Dict], lang: str) -> None:
    """使用 Rich Table 渲染 trending 到控制台"""
    console = Console()
    total_count = 1

    for group in data:
        title = group.get("title", "Trending")
        time_span = group.get("time_span", {})

        header = f"# {title}"
        if time_span:
            header += f" ({time_span.get('start', '')} - {time_span.get('end', '')})"

        table = _format_repo_items_rich_table(
            group.get("repos", []), lang, start_idx=total_count
        )
        total_count += len(group.get("repos", []))

        console.print(Panel(table, title=header, border_style="blue"))


# --- Repo List 格式化（find/discover/search 共用） ---
def _format_repo_list_plain(items: List[Dict], lang: str) -> str:
    """纯文本格式输出仓库列表"""
    lines = _format_repo_items_plain(items, lang)
    return "\n".join(lines)


def _format_repo_list_rich(items: List[Dict], lang: str) -> None:
    """Rich 表格格式输出仓库列表"""
    console = Console()
    table = _format_repo_items_rich_table(items, lang)
    console.print(table)


# --- Status 格式化 ---
def _format_status_plain(item: Dict, lang: str) -> str:
    """纯文本格式输出状态"""
    url = item.get("url", f"https://github.com/{item.get('owner')}/{item.get('name')}")
    desc = (
        item.get("description_zh", "") if lang == "zh" else item.get("description", "")
    )
    if not desc:
        desc = item.get("description", tr("messages.no_description", lang))
    desc = desc.replace("\n", " ")

    lines = [
        f"url: {url}",
        f"description: {desc}",
        f"language: {item.get('language', 'N/A')}",
        f"topics: {' '.join(item.get('topics', []))}",
        f"stars: {item.get('star_count', 0)}",
    ]
    default_branch = item.get("default_branch", "")
    if default_branch:
        lines.append(f"default branch: {default_branch}")
    return "\n".join(lines)


# --- Outline 格式化 ---
def _format_outline_plain(
    data: Dict, owner: str, repo_name: str, ref: Optional[str] = None
) -> str:
    """纯文本格式输出大纲"""
    lines = []
    pages = data.get("pages", [])
    if not pages:
        return tr("messages.no_pages")

    groups: Dict[str, Any] = {}
    for page in pages:
        title = page.get("title", "")
        slug = page.get("slug", "")
        if not title or not slug:
            continue

        section = page.get("section", "")
        group = page.get("group", "")
        topic = page.get("topic", "")

        if not section:
            section = "General"

        if section not in groups:
            groups[section] = {}

        full_url = _page_url(owner, repo_name, slug, ref)

        if group:
            if group not in groups[section]:
                groups[section][group] = []
            groups[section][group].append({"title": topic or title, "url": full_url})
        else:
            if "_default" not in groups[section]:
                groups[section]["_default"] = []
            groups[section]["_default"].append(
                {"title": topic or title, "url": full_url}
            )

    for section, section_data in groups.items():
        lines.append(f"# {section}")
        if "_default" in section_data and section_data["_default"]:
            for page in section_data["_default"]:
                lines.append(f"- [{page['title']}]({page['url']})")
        for group, group_pages in section_data.items():
            if group == "_default":
                continue
            lines.append(f"## {group}")
            for page in group_pages:
                lines.append(f"- [{page['title']}]({page['url']})")
        lines.append("")

    return "\n".join(lines)


def _extract_slug_number(slug: str) -> str:
    """从 slug 中提取序号，如 '1-overview' -> '1'"""
    if not slug:
        return ""
    match = re.match(r"^(\d+)-", slug)
    return match.group(1) if match else ""


def _format_outline_rich(
    data: Dict, owner: str, repo_name: str, ref: Optional[str] = None
) -> None:
    """Rich 格式输出大纲（使用 Tree 组件）"""
    pages = data.get("pages", [])
    if not pages:
        typer.echo(tr("messages.no_pages"))
        return

    console = Console()
    root = Tree(f"[bold cyan]{owner}/{repo_name}[/bold cyan]")

    sections: Dict[str, Any] = {}

    for page in pages:
        title = page.get("title", "")
        slug = page.get("slug", "")
        if not title or not slug:
            continue

        section = page.get("section", "") or "General"
        group = page.get("group", "")
        topic = page.get("topic", "")
        display_title = topic or title
        full_url = _page_url(owner, repo_name, slug, ref)

        if section not in sections:
            sections[section] = {}

        if group:
            if group not in sections[section]:
                sections[section][group] = []
            sections[section][group].append(
                {"title": display_title, "url": full_url, "slug": slug}
            )
        else:
            if "_direct" not in sections[section]:
                sections[section]["_direct"] = []
            sections[section]["_direct"].append(
                {"title": display_title, "url": full_url, "slug": slug}
            )

    for section_name, groups in sections.items():
        section_node = root.add(f"[bold magenta]{section_name}[/bold magenta]")

        if "_direct" in groups:
            for page in groups["_direct"]:
                slug_num = _extract_slug_number(page.get("slug", ""))
                prefix = f"{slug_num}. " if slug_num else ""
                link_text = f"[link={page['url']}]🔗 {prefix}{page['title']}[/link]"
                section_node.add(link_text)

        for group_name, group_pages in groups.items():
            if group_name == "_direct":
                continue
            group_node = section_node.add(f"[bold green]{group_name}[/bold green]")
            for page in group_pages:
                slug_num = _extract_slug_number(page.get("slug", ""))
                prefix = f"{slug_num}. " if slug_num else ""
                link_text = f"[link={page['url']}]🔗 {prefix}{page['title']}[/link]"
                group_node.add(link_text)

    console.print(root)


# --- Search Results (in repo) 格式化 ---
def _format_search_results_plain(results: List[Dict]) -> str:
    """纯文本格式输出文档搜索结果 (MCP/plain/JSON 模式，删除所有 HTML 标签)"""
    lines = []
    for idx, result in enumerate(results, 1):
        title = result.get("title", "")
        slug = result.get("slug", "")
        slug_num = slug.split("-")[0] if slug and slug[0].isdigit() else str(idx)
        lines.append(f"{slug_num}. {title}")
        lines.append(f"   slug: {slug}")
        contents = []
        for match in result.get("matches", []):
            text = match.get("highlight") or match.get("content", "")
            text = re.sub(r"<[^>]+>", "", text).replace("\n", " ")
            text = re.sub(r" {3,}", "  ", text).strip()
            if text:
                contents.append(text)
        if contents:
            lines.append(f"   {' '.join(contents)[:200]}...")
        lines.append("")
    return "\n".join(lines)


def _clean_and_extract_em(text: str) -> "tuple[str, list[tuple[int, int]]]":
    """清理 HTML 标签（保留 <em>），返回清理后的文本和 <em> 位置"""
    cleaned = re.sub(r"</?(?!/?em\b)[^>]+>", "", text).replace("\n", " ")
    cleaned = re.sub(r" {3,}", "  ", cleaned).strip()

    em_positions = []
    offset = 0
    for match in re.finditer(r"<em>([^<]*)</em>", cleaned):
        start = match.start() - offset
        end = start + len(match.group(1))
        em_positions.append((start, end))
        offset += 9  # len('<em></em>') = 9

    cleaned_no_em = re.sub(r"</?em>", "", cleaned)
    return cleaned_no_em, em_positions


def _format_search_results_rich(
    results: List[Dict], repo: str = "", ref: Optional[str] = None
) -> None:
    """Rich 格式输出文档搜索结果 (CLI 模式，保留 <em> 并高亮)"""
    console = Console()

    for result in results:
        title = result.get("title", "")
        slug = result.get("slug", "")
        slug_num = _extract_slug_number(slug)
        prefix = f"{slug_num}. " if slug_num else ""
        if repo and "/" in repo:
            # 通过 parse_repo_url 归一化，owner/repo@ref 形式也能生成正确链接
            try:
                parsed_repo = parse_repo_url(repo)
                page_url = _page_url(
                    parsed_repo["owner"],
                    parsed_repo["repo"],
                    slug,
                    ref or parsed_repo.get("ref"),
                )
            except ValueError:
                page_url = f"https://github.com/{repo}/blob/{ref or 'HEAD'}/{slug}"
        else:
            page_url = f"https://github.com/{repo}/blob/{ref or 'HEAD'}/{slug}"

        contents = []
        for match in result.get("matches", []):
            text = match.get("highlight") or match.get("content", "")
            text = re.sub(r"</?(?!/?em\b)[^>]+>", "", text).replace("\n", " ")
            text = re.sub(r" {3,}", "  ", text).strip()
            if text:
                contents.append(text)

        rich_parts = []
        for match_text in contents[:3]:  # 最多取前3个 matches
            cleaned, em_positions = _clean_and_extract_em(match_text)
            if not cleaned:
                continue

            text_obj = Text()
            last_end = 0
            for start, end in em_positions:
                if start > last_end:
                    text_obj.append(cleaned[last_end:start])
                text_obj.append(cleaned[start:end], style=_get_search_highlight_style())
                last_end = end
            if last_end < len(cleaned):
                text_obj.append(cleaned[last_end:])

            rich_parts.append(text_obj)

        if rich_parts:
            content_text = Text(" ").join(rich_parts)
            plain_str = str(content_text)
            if len(plain_str) > 220:
                content_text.truncate(200)
                content_text.append("...")
        else:
            content_text = Text((" ".join(contents)[:200] + "...") if contents else "")

        console.print()
        title_line = f"[link={page_url}]🔗 {prefix}{title}[/link]"
        console.print(title_line)

        if content_text:
            console.print(content_text)
        else:
            console.print(f"[dim]{tr('messages.no_preview')}[/dim]")

        console.print()


# ==========================================
# Markdown 链接处理与文件渲染
# ==========================================


def _process_markdown_links(content: str, repo: str) -> str:
    """处理 markdown 中的链接

    - slug 格式链接: [xxx](slug) -> [🔗xxx](https://github.com/owner/repo/blob/HEAD/slug)
    - 代码文件链接: [xxx](path/file.py) -> [🐙xxx](https://github.com/owner/repo/blob/HEAD/path/file.py)
    """
    parsed = parse_repo_url(repo)
    repo_path = parsed["repo_path"]

    # 匹配 markdown 链接: [text](url)，排除图片 ![text](url)
    # 使用递归方式处理嵌套的 []，如 [🐙来源: [README.md](/README.md#L1-L6)]
    link_pattern = re.compile(
        r"(?<!!)\[(?:[^\[\]]|\[(?:[^\[\]]|\[[^\[\]]*\])*\])*\]\(([^)]+)\)"
    )

    # slug 格式: 数字-名称
    slug_pattern = re.compile(r"^\d+-[a-zA-Z0-9-]+(?<!-)$")
    # 任意 URI scheme（mailto:、ftp:、tel: 等）
    scheme_pattern = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")

    def _prefix_slug_text(text: str, slug: str) -> str:
        slug_num_match = re.match(r"^(\d+)-", slug)
        if not slug_num_match:
            return text
        prefix = f"{slug_num_match.group(1)}."
        return text if text.startswith(prefix) else f"{prefix}{text}"

    def _relative_to_blob_url(url: str) -> str:
        # 统一使用 HEAD（指向默认分支）；硬编码 main 会给默认分支为
        # master 的仓库生成 404 链接。去掉 ./ 与 / 前缀避免链接含 /./
        file_path = re.sub(r"^(?:\./)+", "", url).lstrip("/")
        return f"https://github.com/{repo_path}/blob/HEAD/{file_path}"

    def _rewrite_markdown_link(full_match: str, text: str, url: str) -> str:
        url_path = url.split("#")[0]
        last_segment = url_path.split("/")[-1] if "/" in url_path else url_path
        last_segment = last_segment.lstrip("/")

        if slug_pattern.match(last_segment):
            link_text = _prefix_slug_text(text, last_segment)
            if url.startswith(("http://", "https://")):
                full_url = url
            elif scheme_pattern.match(url):
                # mailto:、ftp: 等非 http scheme 保持原样
                return full_match
            else:
                full_url = _relative_to_blob_url(url)
            return f"[🔗{link_text}]({full_url})"

        if "." in last_segment:
            # 绝对 URL / 带 scheme 的链接不是仓库内文件：保持原样，
            # 不加 🐙 标记（此前 example.com、mailto: 都被误标 / 误改写）
            if url.startswith(("http://", "https://")) or scheme_pattern.match(url):
                return full_match
            return f"[🐙{text}]({_relative_to_blob_url(url)})"

        return full_match

    def replace_link(match):
        full_match = match.group(0)
        url = match.group(1)

        url_start = full_match.rfind("](")
        if url_start == -1:
            return full_match
        text = full_match[1:url_start]
        return _rewrite_markdown_link(full_match, text, url)

    return link_pattern.sub(replace_link, content)


def _format_size(size: int) -> str:
    """格式化文件大小。"""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


_GITHUB_FILE_LEXER_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "jsx",
    ".tsx": "tsx",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    ".ps1": "powershell",
    ".sql": "sql",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".xml": "xml",
    ".svg": "xml",
    ".dockerfile": "dockerfile",
    "dockerfile": "dockerfile",
    ".makefile": "makefile",
    "makefile": "makefile",
    ".vue": "vue",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".r": "r",
    ".m": "objective-c",
    ".mm": "objective-c",
    ".pl": "perl",
    ".pm": "perl",
    ".t": "perl",
    ".lua": "lua",
    ".vim": "vim",
    ".elm": "elm",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".ex": "elixir",
    ".exs": "elixir",
    ".fs": "fsharp",
    ".fsx": "fsharp",
    ".ml": "ocaml",
    ".mli": "ocaml",
    ".hs": "haskell",
    ".lhs": "haskell",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".edn": "clojure",
    ".dart": "dart",
    ".groovy": "groovy",
    ".gradle": "groovy",
    ".tf": "terraform",
    ".tfvars": "terraform",
    ".nim": "nim",
    ".pony": "pony",
    ".cr": "crystal",
    ".v": "v",
    ".zig": "zig",
    ".wat": "wast",
    ".wast": "wast",
    ".graphql": "graphql",
    ".gql": "graphql",
}


def _get_github_file_lexer(file_path: str) -> str:
    """根据文件路径推断 Syntax lexer。"""
    ext = os.path.splitext(file_path)[1].lower()
    basename = os.path.basename(file_path).lower()
    return _GITHUB_FILE_LEXER_MAP.get(ext) or _GITHUB_FILE_LEXER_MAP.get(
        basename, "text"
    )


def _render_github_file_output(
    file_path: str,
    content: str,
    total_lines: int,
    total_size: int,
    actual_start: Optional[int],
    actual_end: Optional[int],
    json_output: bool,
    plain: bool,
) -> None:
    """统一渲染 GitHub 文件内容。"""
    import json as json_module

    file_info = tr(
        "messages.file_info",
        file_path=file_path,
        total_lines=total_lines,
        size=_format_size(total_size),
    )
    if actual_start and actual_end and (actual_start > 1 or actual_end < total_lines):
        file_info += tr(
            "messages.file_info_showing_lines",
            start=actual_start,
            end=actual_end,
        )

    if json_output:
        typer.echo(
            json_module.dumps(
                {
                    "content": content,
                    "file_path": file_path,
                    "total_lines": total_lines,
                    "size": total_size,
                    "size_formatted": _format_size(total_size),
                    "showing_lines": f"{actual_start}-{actual_end}"
                    if actual_start and actual_end
                    else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if plain:
        typer.echo(file_info)
        typer.echo("-" * 60)
        typer.echo(content)
        return

    console = Console()
    theme = _get_syntax_theme()
    syntax = Syntax(
        content,
        _get_github_file_lexer(file_path),
        theme=theme,
        line_numbers=True,
        word_wrap=True,
        start_line=actual_start if actual_start else 1,
    )
    console.print(Panel(syntax, title=file_info, border_style="blue"))


def _run_with_cli_status(
    enabled: bool, message: str, fn: Callable[..., Any], *args, **kwargs
) -> Any:
    """在 Rich 渲染路径下为数据获取阶段显示等待动画。"""
    if not enabled:
        return fn(*args, **kwargs)

    from rich.status import Status

    console = Console()
    status = Status(message, spinner="dots", console=console)
    status.start()
    try:
        return fn(*args, **kwargs)
    finally:
        status.stop()
