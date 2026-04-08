#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "httpx>=0.25.0",
#   "fastmcp>=3.0.0",
#   "typer>=0.9.0",
#   "arrow>=1.3.0",
#   "darkdetect>=0.8.0",
#   "python-i18n>=0.3.9",
#   "pylocale>=0.0.1",
#   "rich>=13.7.0",
#   "Pillow>=10.0.0",
#   "textual-image>=0.2.0",
#   "typing-extensions>=4.8.0",
# ]
# ///

"""Zread CLI 与 MCP 服务。"""

# 标准库
import asyncio
import json
import logging
import locale
import os
import re
import sys
import threading
import time
import urllib.parse

# 忽略 httpx 的 DeprecationWarning
import warnings
from contextlib import asynccontextmanager, contextmanager
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# arrow 用于人性化时间显示
import arrow

# darkdetect 用于检测系统主题
import darkdetect

# 第三方库
import httpx as _httpx
import i18n
import typer
from rich.box import SIMPLE_HEAD

# Rich 用于 Markdown 渲染
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown, MarkdownElement
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.syntax import Syntax
from rich.table import Column, Table
from rich.text import Text
from rich.tree import Tree
from typing_extensions import Annotated

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings(
    "ignore", message=".*Palette images with Transparency.*", category=UserWarning
)
warnings.filterwarnings("ignore", module="PIL")

# TOML 配置文件读取（Python 3.11+ 内置 tomllib，之前的版本需要 tomli）
try:
    import tomllib
except ImportError:
    import tomli as tomllib

# 全局图片缓存
_IMAGE_CACHE: Dict[str, Any] = {}
_TEXTUAL_IMAGE_CLASS: Any = None
_PIL_IMAGE_CLASS: Any = None
_MCP_INSTANCE: Any = None
HTTPX_TIMEOUT_SECONDS = 5.0
HTTPX_MAX_REDIRECTS = 2
HTTPX_MAX_RETRIES = 3
HTTPX_RETRY_STATUS_CODES = {429, 502, 503, 504}

# ==========================================
# 全局配置
# ==========================================

# 配置文件路径（跨平台支持）
_CONFIG_PATH: Optional[Path] = None


def _get_config_path() -> Optional[Path]:
    """获取配置文件路径。

    优先级：
    - macOS: ~/.config/zread/zread.toml
    - Linux: $XDG_CONFIG_HOME/zread/zread.toml（默认 ~/.config/zread/zread.toml）
    - Windows: %APPDATA%/zread/zread.toml
    """
    global _CONFIG_PATH
    if _CONFIG_PATH is not None:
        return _CONFIG_PATH

    home = Path.home()

    if sys.platform == "darwin":
        config_file = home / ".config" / "zread" / "zread.toml"
    elif sys.platform == "win32":
        config_file = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "zread" / "zread.toml"
    else:
        # Linux 和其他 POSIX 系统
        xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
        if xdg_config:
            config_file = Path(xdg_config) / "zread" / "zread.toml"
        else:
            config_file = home / ".config" / "zread" / "zread.toml"

    _CONFIG_PATH = config_file if config_file.exists() else None
    return _CONFIG_PATH


# 加载配置文件（仅用于获取默认值，不覆盖环境变量）
def _load_config() -> Dict[str, Any]:
    """从配置文件读取配置（如果存在）。

    配置文件格式 (TOML):
        [zread]
        token = "your-token-here"
        lang = "zh"  # 可选，默认为 "zh"
    """
    config_path = _get_config_path()
    if not config_path:
        return {}

    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        return config.get("zread", {}) if isinstance(config, dict) else {}
    except Exception:
        return {}


_CONFIG_FROM_FILE: Dict[str, Any] = _load_config()

# 硬编码 token（可选，优先级：命令行参数 > 环境变量 > 配置文件）
# 使用 --no-token 参数可在无 token 模式下运行，只提供不需要 token 的功能
_DEFAULT_TOKEN = os.environ.get("ZREAD_TOKEN", _CONFIG_FROM_FILE.get("token", ""))

# 固定域名
BASE_URL = "https://zread.ai"
APP_NAME = "zread"

# 版本号：从包元数据获取，本地开发时从 _version.py 获取
try:
    from importlib.metadata import version, PackageNotFoundError
    APP_VERSION = version("zread")
except PackageNotFoundError:
    try:
        from zread_version import __version__ as APP_VERSION
    except (ImportError, ModuleNotFoundError):
        APP_VERSION = "0.0.0"

# User-Agent
USER_AGENT = f"Mozilla/5.0 (compatible; {APP_NAME}/{APP_VERSION}; +https://github.com/efjdkev/zread)"

# 默认请求头
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
}

LOCALES_DIR = Path(__file__).resolve().parent / "locales"

# Markdown 链接正则（slug 转链接）
SLUG_LINK_PATTERN = re.compile(
    r"(?P<text>\[(?P<content>[^\]]+)\])(?P<prefix>\()(?P<slug>\d+-[a-zA-Z0-9_-]+)"
)


def _apply_httpx_client_defaults(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """为 httpx Client/AsyncClient 注入统一默认配置。"""
    merged = dict(kwargs)
    merged.setdefault("follow_redirects", True)
    merged.setdefault("max_redirects", HTTPX_MAX_REDIRECTS)
    merged.setdefault("timeout", HTTPX_TIMEOUT_SECONDS)
    return merged


def _apply_httpx_request_defaults(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """为单次请求注入统一默认配置。"""
    merged = dict(kwargs)
    merged.setdefault("follow_redirects", True)
    merged.setdefault("timeout", HTTPX_TIMEOUT_SECONDS)
    return merged


def _retry_sync_request(request_fn: Callable[[], Any]) -> Any:
    """同步请求自动重试。"""
    last_error: Optional[Exception] = None
    for _ in range(HTTPX_MAX_RETRIES):
        try:
            return request_fn()
        except (_httpx.RequestError, _httpx.HTTPStatusError) as exc:
            last_error = exc
            if isinstance(exc, _httpx.HTTPStatusError):
                response = exc.response
                if (
                    response is None
                    or response.status_code not in HTTPX_RETRY_STATUS_CODES
                ):
                    raise
    if last_error:
        raise last_error
    raise RuntimeError(tr("errors.http_request_failed"))


async def _retry_async_request(request_fn: Callable[[], Any]) -> Any:
    """异步请求自动重试。"""
    last_error: Optional[Exception] = None
    for _ in range(HTTPX_MAX_RETRIES):
        try:
            return await request_fn()
        except (_httpx.RequestError, _httpx.HTTPStatusError) as exc:
            last_error = exc
            if isinstance(exc, _httpx.HTTPStatusError):
                response = exc.response
                if (
                    response is None
                    or response.status_code not in HTTPX_RETRY_STATUS_CODES
                ):
                    raise
    if last_error:
        raise last_error
    raise RuntimeError(tr("errors.http_request_failed"))


def _raise_for_retryable_status(response: _httpx.Response) -> None:
    """对可重试状态码抛出 HTTPStatusError，交给统一重试层处理。"""
    if response.status_code in HTTPX_RETRY_STATUS_CODES:
        request = response.request or _httpx.Request("GET", str(response.url))
        raise _httpx.HTTPStatusError(
            f"Retryable HTTP error: {response.status_code}",
            request=request,
            response=response,
        )


class WrappedHTTPXClient(_httpx.Client):
    """带默认超时、重定向和重试的同步 httpx Client。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **_apply_httpx_client_defaults(kwargs))

    def request(self, method: str, url: str, *args, **kwargs):
        request_kwargs = _apply_httpx_request_defaults(kwargs)
        return _retry_sync_request(
            lambda: self._request_once(method, url, *args, **request_kwargs)
        )

    def _request_once(self, method: str, url: str, *args, **kwargs):
        response = super(WrappedHTTPXClient, self).request(method, url, *args, **kwargs)
        _raise_for_retryable_status(response)
        return response

    @contextmanager
    def stream(self, method: str, url: str, *args, **kwargs):
        stream_kwargs = _apply_httpx_request_defaults(kwargs)
        stream_cm, response = _retry_sync_request(
            lambda: self._open_stream_once(method, url, *args, **stream_kwargs)
        )
        try:
            yield response
        finally:
            stream_cm.__exit__(None, None, None)

    def _open_stream_once(self, method: str, url: str, *args, **kwargs):
        stream_cm = super(WrappedHTTPXClient, self).stream(method, url, *args, **kwargs)
        response = stream_cm.__enter__()
        try:
            _raise_for_retryable_status(response)
        except Exception:
            stream_cm.__exit__(*sys.exc_info())
            raise
        return stream_cm, response


class WrappedHTTPXAsyncClient(_httpx.AsyncClient):
    """带默认超时、重定向和重试的异步 httpx Client。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **_apply_httpx_client_defaults(kwargs))

    async def request(self, method: str, url: str, *args, **kwargs):
        request_kwargs = _apply_httpx_request_defaults(kwargs)
        return await _retry_async_request(
            lambda: self._request_once(method, url, *args, **request_kwargs)
        )

    async def _request_once(self, method: str, url: str, *args, **kwargs):
        response = await super(WrappedHTTPXAsyncClient, self).request(
            method, url, *args, **kwargs
        )
        _raise_for_retryable_status(response)
        return response

    @asynccontextmanager
    async def stream(self, method: str, url: str, *args, **kwargs):
        stream_kwargs = _apply_httpx_request_defaults(kwargs)
        stream_cm, response = await _retry_async_request(
            lambda: self._open_stream_once(method, url, *args, **stream_kwargs)
        )
        try:
            yield response
        finally:
            await stream_cm.__aexit__(None, None, None)

    async def _open_stream_once(self, method: str, url: str, *args, **kwargs):
        stream_cm = super(WrappedHTTPXAsyncClient, self).stream(
            method, url, *args, **kwargs
        )
        response = await stream_cm.__aenter__()
        try:
            _raise_for_retryable_status(response)
        except Exception:
            await stream_cm.__aexit__(*sys.exc_info())
            raise
        return stream_cm, response


class WrappedHTTPXModule:
    """兼容 httpx 常用接口的包装器。"""

    Client = WrappedHTTPXClient
    AsyncClient = WrappedHTTPXAsyncClient
    Timeout = _httpx.Timeout
    Limits = _httpx.Limits
    RequestError = _httpx.RequestError
    HTTPStatusError = _httpx.HTTPStatusError

    def request(self, method: str, url: str, *args, **kwargs):
        request_kwargs = _apply_httpx_request_defaults(kwargs)
        return self._request_via_client(method, url, *args, **request_kwargs)

    def get(self, url: str, *args, **kwargs):
        return self.request("GET", url, *args, **kwargs)

    def post(self, url: str, *args, **kwargs):
        return self.request("POST", url, *args, **kwargs)

    def delete(self, url: str, *args, **kwargs):
        return self.request("DELETE", url, *args, **kwargs)

    def _request_via_client(self, method: str, url: str, *args, **kwargs):
        with self.Client() as client:
            return client.request(method, url, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(_httpx, name)


httpx = WrappedHTTPXModule()


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
            # 如果不支持图片渲染，显示原文
            yield Text(self.raw_markdown, style="dim")
            return

        # 检查缓存
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
            # 缓存未命中，显示原文
            yield Text(self.raw_markdown, style="dim")


class ImageAwareMarkdown(Markdown):
    """支持图片渲染的 Markdown 类"""

    elements = Markdown.elements.copy()
    elements["image"] = MarkdownImage

    def __init__(self, markup: str, code_theme: str = "default", **kwargs):
        """初始化，支持 code_theme 参数"""
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
        """获取单张图片"""
        try:
            # 使用 asyncio.wait_for 实现硬超时 2.0 秒
            content = await asyncio.wait_for(
                loop.run_in_executor(None, _fetch_image_sync, url), timeout=2.0
            )
            if content:
                pil_image_class = _get_pil_image_class()
                _IMAGE_CACHE[url] = pil_image_class.open(BytesIO(content))
            else:
                _IMAGE_CACHE[url] = None
        except asyncio.TimeoutError:
            _IMAGE_CACHE[url] = None
        except Exception:
            _IMAGE_CACHE[url] = None

    # 并发执行所有图片下载
    await asyncio.gather(*(fetch_one(url) for url in urls_to_fetch))


# 保持向后兼容的同步包装函数
def _preload_images_sync(md_text: str) -> None:
    """预加载 markdown 中的图片（自动检测是否使用异步并行）"""
    urls = re.findall(r"!\[.*?\]\((http[s]?://.*?)\)", md_text)
    urls_to_fetch = [url for url in urls if url not in _IMAGE_CACHE]

    if not urls_to_fetch:
        return

    # 检查是否已有运行中的事件循环
    try:
        loop = asyncio.get_running_loop()
        # 已有事件循环，创建任务并等待
        # 注意：在同步上下文中这不会执行，但在异步上下文中会
        loop.create_task(_preload_images_async(md_text))
    except RuntimeError:
        # 没有运行中的事件循环，直接运行异步函数
        try:
            asyncio.run(_preload_images_async(md_text))
        except Exception:
            # 异步执行失败，回退到同步串行获取
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


# --- 通用仓库列表格式化（trending/search/discover/find 共用） ---
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

        # 第一行：URL + 星标
        star_count = item.get("star_count", 0)
        url_line = f"{url}"
        if star_count:
            url_line += f"  🌟 {star_count:,}"
        lines.append(f"{idx}. {url_line}")

        # 描述
        if desc:
            lines.append(f"   {desc}")

        # 语言和 topics
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
    - 状态 (未收录/索引中显示黄色，已收录不显示)
    - 更新时间 (超过5天显示黄色)

    :param data: 仓库数据 dict
    :param lang: 语言
    :param show_status: 是否显示状态和更新时间
    :return: Rich Text 对象
    """
    lines = []

    # 第一行：URL (一半暗一半蓝) + 🌟 + 星标数量
    url = data.get("url", "")
    if not url:
        url = f"https://github.com/{data.get('owner', '')}/{data.get('name', '')}"

    url_text = Text()
    link_style = f"link {url}"
    # 分割 URL，前面部分 dim，后面部分 blue
    if "/" in url:
        # 找到 owner/repo 之前的部分
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

    # 添加星标
    star_count = data.get("star_count", 0)
    if star_count:
        url_text.append(f"  🌟 {star_count:,}", style="yellow")

    lines.append(url_text)

    # 描述
    desc_key = "description_zh" if lang == "zh" else "description"
    description = data.get(desc_key, "") or data.get("description", "")
    if description:
        lines.append(Text(description.strip()))

    # 语言和 topics
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

    # 状态和更新时间
    if show_status:
        status = data.get("status", "")
        updated_at = data.get("updated_at", 0)
        last_commit = data.get("last_commit", {})
        last_commit_when = last_commit.get("when", 0)

        status_line = Text()
        parts = []

        # 1. 最后提交时间
        if last_commit_when:
            try:
                commit_time = arrow.get(last_commit_when)
                commit_ago = commit_time.humanize(locale=lang if lang == "zh" else "en")
                if lang == "zh":
                    parts.append(f"📝 {commit_ago}提交代码")
                else:
                    parts.append(f"📝 code committed {commit_ago}")
            except Exception:
                pass

        # 2. 收录状态
        if status == "inactive":
            parts.append("⚠️ 未收录" if lang == "zh" else "⚠️ not indexed")
        elif status != "success":
            parts.append("⏳ 索引中" if lang == "zh" else "⏳ indexing")

        # 3. 文档更新时间
        if updated_at:
            try:
                update_time = arrow.get(updated_at)
                update_ago = update_time.humanize(locale=lang if lang == "zh" else "en")
                if lang == "zh":
                    parts.append(f"📚 {update_ago}更新文档")
                else:
                    parts.append(f"📚 docs updated {update_ago}")
            except Exception:
                pass

        if parts:
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
        # 使用统一的格式化函数（列表不显示状态）
        cell_content = _format_single_repo_info(item, lang, show_status=False)
        table.add_row(str(idx), cell_content)
        # 添加空行（最后一项除外）
        if idx < len(items) + start_idx - 1:
            table.add_row("", "")

    return table


# --- Trending 格式化 ---
def _format_trending_plain(data: List[Dict], lang: str) -> str:
    """纯文本格式输出 trending"""
    lines = []
    for group in data:
        title = group.get("title", "Trending")
        time_span = group.get("time_span", {})
        lines.append(f"# {title}")
        if time_span:
            lines.append(f"# {time_span.get('start', '')} - {time_span.get('end', '')}")
        lines.append("")

        group_lines = _format_repo_items_plain(
            group.get("repos", []), lang, start_idx=len(lines) // 5 + 1
        )
        lines.extend(group_lines)
    return "\n".join(lines)


def _format_trending_rich(data: List[Dict], lang: str) -> None:
    """使用 Rich Table 渲染 trending 到控制台"""
    console = Console()
    total_count = 1

    for group in data:
        title = group.get("title", "Trending")
        time_span = group.get("time_span", {})

        # 标题
        header = f"# {title}"
        if time_span:
            header += f" ({time_span.get('start', '')} - {time_span.get('end', '')})"

        # 表格
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
        f"status: {item.get('status', 'N/A')}",
        f"stars: {item.get('star_count', 0)}",
    ]
    return "\n".join(lines)


# --- Outline 格式化 ---
def _format_outline_plain(data: Dict, owner: str, repo_name: str) -> str:
    """纯文本格式输出大纲"""
    lines = []
    pages = data.get("pages", [])
    if not pages:
        return tr("messages.no_pages")

    # 按组分组
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

        full_url = f"https://zread.ai/{owner}/{repo_name}/{slug}"

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

    # 输出
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


def _format_outline_rich(data: Dict, owner: str, repo_name: str) -> None:
    """Rich 格式输出大纲（使用 Tree 组件）"""
    pages = data.get("pages", [])
    if not pages:
        typer.echo(tr("messages.no_pages"))
        return

    console = Console()

    # 构建树结构
    root = Tree(f"[bold cyan]{owner}/{repo_name}[/bold cyan]")

    # 按 section -> group -> pages 组织
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
        full_url = f"https://zread.ai/{owner}/{repo_name}/{slug}"

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

    # 构建树
    for section_name, groups in sections.items():
        section_node = root.add(f"[bold magenta]{section_name}[/bold magenta]")

        # 直接属于 section 的 pages（没有 group）
        if "_direct" in groups:
            for page in groups["_direct"]:
                # 提取 slug 中的序号
                slug_num = _extract_slug_number(page.get("slug", ""))
                prefix = f"{slug_num}. " if slug_num else ""
                link_text = f"[link={page['url']}]🔗 {prefix}{page['title']}[/link]"
                section_node.add(link_text)

        # 有 group 的 pages
        for group_name, group_pages in groups.items():
            if group_name == "_direct":
                continue
            group_node = section_node.add(f"[bold green]{group_name}[/bold green]")
            for page in group_pages:
                # 提取 slug 中的序号
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
        # 提取 slug 序号（如 "24-eslint-plugin" -> "24"）
        slug_num = slug.split("-")[0] if slug and slug[0].isdigit() else str(idx)
        lines.append(f"{slug_num}. {title}")
        lines.append(f"   slug: {slug}")
        contents = []
        for match in result.get("matches", []):
            text = match.get("highlight") or match.get("content", "")
            # 删除所有 HTML 标签（包括 <em>）
            text = re.sub(r"<[^>]+>", "", text).replace("\n", " ")
            text = re.sub(r" {3,}", "  ", text).strip()
            if text:
                contents.append(text)
        if contents:
            lines.append(f"   {' '.join(contents)[:200]}...")
        lines.append("")
    return "\n".join(lines)


def _format_search_results_rich(results: List[Dict], repo: str = "") -> None:
    """Rich 格式输出文档搜索结果 (CLI 模式，保留 <em> 并高亮)"""
    console = Console()

    # 构建 zread 基础 URL - 使用 owner/repo 格式
    base_url = f"{BASE_URL}/{repo}" if repo else BASE_URL

    for result in results:
        title = result.get("title", "")
        slug = result.get("slug", "")
        # 提取 slug 序号
        slug_num = _extract_slug_number(slug)
        prefix = f"{slug_num}. " if slug_num else ""
        # 构建页面链接
        page_url = f"{base_url}/{slug}"

        # 内容预览（保留 <em> 标签用于高亮）
        contents = []
        for match in result.get("matches", []):
            text = match.get("highlight") or match.get("content", "")
            # 只删除除了 <em> 之外的 HTML 标签
            text = re.sub(r"</?(?!/?em\b)[^>]+>", "", text).replace("\n", " ")
            text = re.sub(r" {3,}", "  ", text).strip()
            if text:
                contents.append(text)

        # 处理每个 content，提取高亮文本并构建 Rich Text
        # 先清理 HTML 标签（保留 <em> 用于高亮），然后构建 Rich Text
        def clean_and_extract_em(text: str) -> tuple[str, list[tuple[int, int]]]:
            """清理 HTML 标签（保留 <em>），返回清理后的文本和 <em> 位置"""
            # 删除除 <em> 和 </em> 外的所有 HTML 标签
            cleaned = re.sub(r"</?(?!/?em\b)[^>]+>", "", text).replace("\n", " ")
            cleaned = re.sub(r" {3,}", "  ", cleaned).strip()

            # 提取 <em> 位置
            em_positions = []
            offset = 0
            for match in re.finditer(r"<em>([^<]*)</em>", cleaned):
                start = match.start() - offset
                end = start + len(match.group(1))
                em_positions.append((start, end))
                # 更新偏移量（移除 <em> 和 </em> 标签）
                offset += 9  # len('<em></em>') = 9

            # 移除 <em> 标签
            cleaned_no_em = re.sub(r"</?em>", "", cleaned)
            return cleaned_no_em, em_positions

        # 处理每个 match
        rich_parts = []
        for match_text in contents[:3]:  # 最多取前3个 matches
            cleaned, em_positions = clean_and_extract_em(match_text)
            if not cleaned:
                continue

            # 构建 Rich Text - 使用更醒目的高亮颜色（黑字黄底）
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

        # 合并所有 parts
        if rich_parts:
            content_text = Text(" ").join(rich_parts)
            # 截断处理：使用 Rich 的 truncate 保持样式
            plain_str = str(content_text)
            if len(plain_str) > 220:
                content_text.truncate(200)
                content_text.append("...")
        else:
            content_text = Text((" ".join(contents)[:200] + "...") if contents else "")

        # 输出格式：标题行使用参考格式
        console.print()
        title_line = f"[link={page_url}]🔗 {prefix}{title}[/link]"
        console.print(title_line)

        # 内容预览（带高亮）
        if content_text:
            console.print(content_text)
        else:
            console.print(f"[dim]{tr('messages.no_preview')}[/dim]")

        console.print()


def _get_default_lang() -> str:
    """获取默认语言，优先级：CLI --lang > ZREAD_LANG > 配置文件 > 系统locale > en。"""
    argv = sys.argv[1:]
    for idx, arg in enumerate(argv):
        if arg.startswith("--lang="):
            cli_lang = arg.split("=", 1)[1]
            if cli_lang in ("zh", "en"):
                return cli_lang
        if arg in ("--lang", "-l") and idx + 1 < len(argv):
            cli_lang = argv[idx + 1]
            if cli_lang in ("zh", "en"):
                return cli_lang

    zread_lang = os.environ.get("ZREAD_LANG", "")
    if zread_lang in ("zh", "en"):
        return zread_lang

    # 配置文件优先级低于环境变量
    config_lang = _CONFIG_FROM_FILE.get("lang", "")
    if config_lang in ("zh", "en"):
        return config_lang

    return _detect_lang_with_pylocale()


def _normalize_lang_code(raw_lang: Optional[str]) -> str:
    if not raw_lang:
        return "en"
    normalized = raw_lang.replace("-", "_").lower()
    if normalized.startswith("zh"):
        return "zh"
    if normalized.startswith("en"):
        return "en"
    return "en"


def _detect_lang_with_pylocale() -> str:
    """根据系统 locale 检测语言，兼容 Windows/Linux/macOS。"""
    candidates: List[str] = []

    # 先尝试 setlocale 初始化（跨平台兼容）
    try:
        locale.setlocale(locale.LC_ALL, "")
    except Exception:
        pass

    try:
        current_locale, _ = locale.getlocale()
        if current_locale:
            candidates.append(current_locale)
    except Exception:
        pass

    for env_name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        env_value = os.environ.get(env_name, "")
        if env_value:
            candidates.append(env_value)

    for raw_lang in candidates:
        lang = _normalize_lang_code(raw_lang.split(".", 1)[0])
        if lang in ("zh", "en"):
            return lang

    return "en"


# 全局默认语言，可通过 set_default_lang() 修改
_DEFAULT_LANG: str = _get_default_lang()


def _configure_i18n(lang: str) -> None:
    """初始化 i18n 配置。"""
    locale_path = str(LOCALES_DIR)
    if locale_path not in i18n.load_path:
        i18n.load_path.append(locale_path)
    i18n.set("file_format", "yml")
    i18n.set("filename_format", "{namespace}.{locale}.{format}")
    i18n.set("fallback", "zh")
    i18n.set("locale", lang)


def tr(key: str, lang: Optional[str] = None, **kwargs: Any) -> str:
    """读取翻译文本。"""
    locale = lang if lang in ("zh", "en") else _DEFAULT_LANG
    return i18n.t(f"messages.{key}", locale=locale, default=key, **kwargs)


_configure_i18n(_DEFAULT_LANG)


def _unknown_error(lang: Optional[str] = None) -> str:
    return tr("messages.unknown_error", lang)


def set_default_lang(lang: str) -> None:
    """设置全局默认语言"""
    global _DEFAULT_LANG
    if lang in ("zh", "en"):
        _DEFAULT_LANG = lang
        i18n.set("locale", lang)


def _resolve_lang(lang: Optional[str]) -> str:
    """解析本次调用使用的语言，未显式指定时回退到全局默认语言。"""
    return lang if lang in ("zh", "en") else _DEFAULT_LANG


def _http_get(
    url: str,
    lang: str = "zh",
    error_msg: str = "请求失败",
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    cookies: Optional[dict] = None,
    timeout: int = 30,
) -> Optional[dict]:
    """通用 HTTP GET 请求函数，统一处理语言和错误

    Args:
        url: 请求 URL
        lang: 语言，自动添加 x-locale header 和 cookie
        error_msg: 错误提示信息（用于打印）
        params: URL 查询参数
        headers: 额外的请求头
        cookies: 额外的 cookies
        timeout: 超时时间（秒）

    Returns:
        API 响应的 data 字段，失败时返回 None
    """
    # 构建带语言设置的 headers 和 cookies
    merged_headers = {**DEFAULT_HEADERS, "x-locale": lang}
    if headers:
        merged_headers.update(headers)

    merged_cookies = {"x-locale": lang}
    if cookies:
        merged_cookies.update(cookies)

    try:
        response = httpx.get(
            url,
            params=params,
            headers=merged_headers,
            cookies=merged_cookies,
            timeout=timeout,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("code") == 0:
            return result.get("data")
        else:
            print(f"{error_msg}: {result.get('msg', _unknown_error(lang))}")
            return None
    except httpx.RequestError as e:
        print(tr("errors.network_error_with_context", lang, context=error_msg, error=e))
        return None
    except json.JSONDecodeError as e:
        print(
            tr("errors.json_parse_error_with_context", lang, context=error_msg, error=e)
        )
        return None


# ==========================================
# 核心功能函数
# ==========================================


def _get_token(token: Optional[str] = None, required: bool = True) -> Optional[str]:
    """获取 token，优先级：传入参数 > 环境变量 > 硬编码

    :param token: 可选的传入 token
    :param required: 如果为 True 且没有 token，则抛出异常；如果为 False，则返回 None
    """
    if token:
        return token
    if _DEFAULT_TOKEN:
        return _DEFAULT_TOKEN
    if required:
        raise ValueError("Token 未设置。请传入 token 参数，或设置 ZREAD_TOKEN 环境变量")
    return None


def set_default_token(token: str) -> None:
    """设置默认 token（运行时修改）"""
    global _DEFAULT_TOKEN
    _DEFAULT_TOKEN = token


def parse_repo_url(url_or_path: str) -> Dict[str, Any]:
    """
    统一解析多种格式的仓库 URL 或路径

    支持的格式:
        - owner/repo
        - owner/repo/file/path
        - https://zread.ai/owner/repo
        - https://github.com/owner/repo
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
            "zread_url": str,       # https://zread.ai/owner/repo
            "source": str,          # 来源类型: repo|zread|github|raw_github
            "file_path": str|None,  # 文件路径（如果有）
            "start_line": int|None, # 起始行号
            "end_line": int|None,   # 结束行号
        }

    示例:
        >>> parse_repo_url("facebook/react")
        {"owner": "facebook", "repo": "react", "repo_path": "facebook/react", ...}

        >>> parse_repo_url("https://github.com/facebook/react/blob/main/README.md#L10-L20")
        {"owner": "facebook", "repo": "react", "file_path": "README.md", "start_line": 10, "end_line": 20}
    """
    url = url_or_path.strip()
    result: Dict[str, Any] = {
        "owner": "",
        "repo": "",
        "repo_path": "",
        "zread_url": "",
        "source": "repo",
        "file_path": None,
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

    # 解析 raw.githubusercontent.com URL
    if "raw.githubusercontent.com" in url:
        # raw.githubusercontent.com/owner/repo/branch/path
        match = re.match(
            r"raw\.githubusercontent\.com/([^/]+)/([^/]+)/[^/]+/(.+)$", url
        )
        if match:
            result["owner"] = match.group(1)
            result["repo"] = match.group(2)
            result["file_path"] = match.group(3)
            result["repo_path"] = f"{match.group(1)}/{match.group(2)}"
            result["zread_url"] = f"{BASE_URL}/{result['repo_path']}"
            result["source"] = "raw_github"
            return result

    # 解析 github.com/blob URL
    if "github.com" in url and "/blob/" in url:
        # github.com/owner/repo/blob/<ref>/path
        match = re.match(r"github\.com/([^/]+)/([^/]+)/blob/[^/]+/(.+)$", url)
        if match:
            result["owner"] = match.group(1)
            result["repo"] = match.group(2)
            result["file_path"] = match.group(3)
            result["repo_path"] = f"{match.group(1)}/{match.group(2)}"
            result["zread_url"] = f"{BASE_URL}/{result['repo_path']}"
            result["source"] = "github"
            return result

    # 移除域名前缀
    if url.startswith("zread.ai/"):
        url = url[9:]
        result["source"] = "zread"
    elif url.startswith("zread.com/"):
        url = url[10:]
        result["source"] = "zread"
    elif url.startswith("github.com/"):
        url = url[11:]
        result["source"] = "github"

    # 解析 owner/repo/path 格式
    parts = url.split("/")
    if len(parts) >= 2:
        result["owner"] = parts[0]
        result["repo"] = parts[1]
        result["repo_path"] = f"{parts[0]}/{parts[1]}"
        result["zread_url"] = f"{BASE_URL}/{result['repo_path']}"
        # 剩余部分是文件路径
        if len(parts) > 2:
            result["file_path"] = "/".join(parts[2:])
        return result

    raise ValueError(
        f"无法解析仓库路径: {url_or_path}，请使用格式: owner/repo 或完整 URL"
    )


def fetch_repo_outline(
    repo_url_or_path: str, lang: str = "zh"
) -> Optional[List[Dict[str, Any]]]:
    """
    获取仓库文档目录（outline）
    :param repo_url_or_path: 支持多种格式:
        - https://zread.ai/owner/repo
        - https://github.com/owner/repo
        - owner/repo
    :param lang: 语言，可选 "zh" 或 "en"
    :return: pages 列表，失败返回 None
    """
    zread_url = parse_repo_url(repo_url_or_path)["zread_url"]

    # 构建带 X-Locale 的 headers 和 cookies
    headers = {**DEFAULT_HEADERS, "X-Locale": lang}
    cookies = {"X-Locale": lang}

    response = httpx.get(zread_url, headers=headers, cookies=cookies, timeout=30.0)
    response.raise_for_status()
    html = response.text

    # HTML markers for extracting wiki data
    _START_MARKER = '{\\"wiki\\":{\\"info\\":{\\"wiki_id\\":\\"'
    _END_MARKER = ']\\n"])</script><script>self.__next_f.push'

    start_pos = html.find(_START_MARKER)
    if start_pos == -1:
        return None

    end_pos = html.find(_END_MARKER, start_pos)
    if end_pos == -1:
        return None

    try:
        json_str = html[start_pos:end_pos].replace('\\"', '"').replace("\\\\", "\\")
        wiki_obj = json.loads(json_str)

        def find_wiki_node(node):
            if isinstance(node, dict):
                if "wiki" in node and "info" in node["wiki"]:
                    return node["wiki"]
                for v in node.values():
                    res = find_wiki_node(v)
                    if res:
                        return res
            elif isinstance(node, list):
                for item in node:
                    res = find_wiki_node(item)
                    if res:
                        return res
            return None

        wiki_node = find_wiki_node(wiki_obj)
        if not wiki_node:
            return None

        simplified_pages = []
        for page in wiki_node.get("pages", []):
            section = page.get("section", "")
            group = page.get("group", "")
            topic = page.get("topic", "")
            parts = [p for p in [section, group, topic] if p]
            title = "/".join(parts)

            simplified_pages.append(
                {
                    "page_id": page.get("page_id"),
                    "slug": page.get("slug"),
                    "title": title,
                    "topic": topic,
                    "group": group,
                    "section": section,
                    "order": page.get("order"),
                }
            )

        return simplified_pages

    except json.JSONDecodeError as e:
        print(tr("errors.parse_json_failed", error=e))
        return None
    except (KeyError, TypeError) as e:
        print(tr("errors.parse_data_structure_failed", error=e))
        return None


def fetch_markdown(repo_url_or_path: str, slug: str, lang: str = "zh") -> Optional[str]:
    """
    获取 Markdown 正文
    :param repo_url_or_path: 支持多种格式: owner/repo 或完整 URL
    :param slug: 页面 slug
    :param lang: 语言，默认 'zh'
    :return: Markdown 字符串 或 None
    """
    zread_url = parse_repo_url(repo_url_or_path)["zread_url"]
    url = f"{zread_url}/{slug}"

    response = httpx.get(
        url,
        cookies={"X-Locale": lang},
        headers={**DEFAULT_HEADERS, "RSC": "1"},
        timeout=30.0,
    )
    response.raise_for_status()
    content = response.content

    # 倒着搜索 ",---" 第一次出现的位置
    marker = b",---"
    end_pos = content.rfind(marker)
    if end_pos == -1:
        return None

    # 往前找 \n（换行符）
    line_start = content.rfind(b"\n", 0, end_pos)
    if line_start == -1:
        line_start = 0  # 如果没有找到换行符，从开头开始
    else:
        line_start += 1  # 跳过换行符本身

    # 提取中间的字符（如 81:T42bf,）
    header_line = content[line_start : end_pos + 1].decode("latin-1")  # +1 包含逗号

    # 用正则匹配出字节大小
    head_pattern = re.compile(r"^([0-9a-f]+):T([0-9a-f]+),")
    match = head_pattern.match(header_line)
    if not match:
        return None

    try:
        byte_length = int(match.group(2), 16)
    except ValueError:
        return None

    # 计算内容开始位置（头部结束位置，即逗号后的位置）
    header_end = line_start + match.end()

    # 往后提取内容
    try:
        return content[header_end : header_end + byte_length].decode("utf-8")
    except UnicodeDecodeError:
        return None


def search_wiki(repo_url_or_path: str, query: str, lang: str = "zh") -> str:
    """
    搜索 Wiki 内容
    :param repo_url_or_path: 支持多种格式: owner/repo 或完整 URL
    :param query: 搜索词
    :param lang: 语言，默认 'zh'
    :return: 格式化结果字符串
    """
    status = fetch_repo_metadata(repo_url_or_path)
    if not status or not status.get("wiki_id"):
        return "no result"

    wiki_id = status["wiki_id"]
    search_url = f"{BASE_URL}/api/v1/wiki/{wiki_id}/search"

    headers = {**DEFAULT_HEADERS, "x-locale": lang}
    params = {"q": query}

    try:
        response = httpx.get(search_url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("code") != 0 or not data.get("data"):
            return "no result"

        results = data["data"]
        if not results:
            return "no result"

        formatted_results = []
        for result in results:
            lines = [f"# [{result.get('title', '')}]({result.get('slug', '')})"]
            for match in result.get("matches", []):
                text = match.get("highlight") or match.get("content", "")
                text = re.sub(r"<[^>]+>", "", text).replace("\n", "  ")
                text = re.sub(r" {3,}", "  ", text).strip()
                if text:
                    lines.append(text)
            formatted_results.append("\n".join(lines))

        return "\n\n".join(formatted_results) if formatted_results else "no result"

    except httpx.RequestError as e:
        print(tr("errors.search_wiki_network_failed", lang, error=e))
        return "no result"
    except json.JSONDecodeError as e:
        print(tr("errors.search_wiki_parse_failed", lang, error=e))
        return "no result"


def create_talk(token: Optional[str] = None, lang: str = "zh") -> Optional[str]:
    """
    创建 AI 对话
    :param token: 可选，Bearer Token
    :param lang: 语言，默认 'zh'
    :return: talk_id 或 None
    """
    token = _get_token(token)
    url = f"{BASE_URL}/api/v1/talk"
    headers = {
        **DEFAULT_HEADERS,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "x-locale": lang,
    }
    data = {"query": " "}

    try:
        response = httpx.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        if result.get("code") == 0 and result.get("data"):
            return result["data"].get("talk_id")
        else:
            print(
                tr(
                    "errors.create_talk_failed_with_reason",
                    lang,
                    detail=result.get("msg", _unknown_error(lang)),
                )
            )
            return None
    except httpx.RequestError as e:
        print(tr("errors.create_talk_network_failed", lang, error=e))
        return None
    except json.JSONDecodeError as e:
        print(tr("errors.create_talk_parse_failed", lang, error=e))
        return None


async def send_message_async(
    talk_id: str,
    query: str,
    wiki_id: str,
    page_id: str,
    repo_id: Optional[str] = None,
    token: Optional[str] = None,
    model: str = "glm-4.7",
    lang: str = "zh",
):
    """
    异步发送消息并流式获取 AI 回复

    事件类型说明：
    - answer: 流式 chunk，data 里有 reasoning_content 和 text
    - round_finish: 一段正文（由多个 answer text 拼起来的完整句子）
    - finish: 所有话都传完毕了，会话结束

    Yields:
        dict: {"event": "answer"|"round_finish", "reasoning_content": str, "text": str}

    :param model: 'glm-4.7' (默认) 或 'claude-sonnet-4.5'
    """
    token = _get_token(token)
    url = f"{BASE_URL}/api/v1/talk/{talk_id}/message"
    headers = {
        **DEFAULT_HEADERS,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "x-locale": lang,
        "Accept": "text/event-stream",
    }
    context = {
        "wiki": {"page_id": page_id, "wiki_id": wiki_id},
    }
    if repo_id:
        context["repo"] = {"repo_id": repo_id}
    data = {
        "parent_message_id": "",
        "query": query,
        "context": context,
        "model": model,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream(
                "POST", url, headers=headers, json=data
            ) as response:
                response.raise_for_status()

                current_event = None

                async for line in response.aiter_lines():
                    line = line.strip()

                    if not line:
                        continue

                    # 解析 event 行
                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                        if current_event == "finish":
                            # 所有话都传完毕了
                            break
                    # 解析 data 行
                    elif line.startswith("data:"):
                        data_str = line[5:].strip()

                        try:
                            event_data = json.loads(data_str)
                            chunk_reasoning = event_data.get("reasoning_content", "")
                            chunk_text = event_data.get("text", "")

                            if current_event == "answer":
                                # 流式 chunk，yield 出去
                                if chunk_reasoning or chunk_text:
                                    yield {
                                        "event": "answer",
                                        "reasoning_content": chunk_reasoning,
                                        "text": chunk_text,
                                    }
                            elif current_event == "round_finish":
                                # 完整的句子（由多个 answer text 拼起来）
                                if chunk_reasoning or chunk_text:
                                    yield {
                                        "event": "round_finish",
                                        "reasoning_content": chunk_reasoning,
                                        "text": chunk_text,
                                    }
                            elif current_event == "error":
                                # API 返回错误
                                yield {
                                    "event": "error",
                                    "text": event_data.get(
                                        "text", _unknown_error(lang)
                                    ),
                                    "reasoning_content": "",
                                }
                                return
                        except json.JSONDecodeError:
                            continue

    except Exception as e:
        error_msg = tr("errors.send_message_async_failed", lang, error=e)
        print(error_msg)
        yield {"event": "error", "text": error_msg, "reasoning_content": ""}


async def send_repo_message_async(
    talk_id: str,
    repo_path: str,
    query: str,
    token: Optional[str] = None,
    model: str = "glm-4.7",
    lang: str = "zh",
    wiki_id: Optional[str] = None,
    page_id: Optional[str] = None,
    repo_id: Optional[str] = None,
):
    """
    异步发送消息到仓库 AI（自动获取 page_id）

    Args:
        talk_id: 对话 ID
        repo_path: 仓库路径，如 "facebook/react"
        query: 用户问题
        token: 可选的 token
        model: 模型名称
        lang: 语言
        wiki_id: 可选，已获取的 wiki_id
        page_id: 可选，已获取的 page_id
        repo_id: 可选，已获取的 repo_id

    Yields:
        dict: {"event": "answer"|"round_finish"|"error", "reasoning_content": str, "text": str}
    """
    # 如果缺少上下文，则统一补齐
    if wiki_id is None or repo_id is None or page_id is None:
        wiki_id_value, page_id_value, repo_id_value, error_message = (
            _get_repo_ai_context(repo_path, lang)
        )
        if error_message:
            yield {
                "event": "error",
                "text": error_message.replace(
                    tr("errors.error_prefix", lang) + " ", "", 1
                ),
                "reasoning_content": "",
            }
            return
        if wiki_id is None:
            wiki_id = wiki_id_value
        if repo_id is None:
            repo_id = repo_id_value
        if page_id is None:
            page_id = page_id_value

    # 调用底层 send_message_async
    async for chunk in send_message_async(
        talk_id, query, wiki_id, page_id, repo_id, token, model, lang
    ):
        yield chunk


def _collect_ai_chunk(
    chunk: Any,
    reasoning_parts: List[str],
    text_parts: List[str],
    *,
    include_round_finish: bool = True,
) -> Optional[str]:
    """统一收集 AI 流式分片，返回错误信息（如有）。"""
    if not isinstance(chunk, dict) or "event" not in chunk:
        return None

    event_type = chunk.get("event")
    if event_type == "error":
        return chunk.get("text", _unknown_error(_DEFAULT_LANG))

    if event_type == "answer" or (
        include_round_finish and event_type == "round_finish"
    ):
        if chunk.get("reasoning_content"):
            reasoning_parts.append(chunk["reasoning_content"])
        if chunk.get("text"):
            text_parts.append(chunk["text"])

    return None


def _merge_live_ai_chunk(
    chunk: Any, reasoning_text: str, answer_text: str
) -> tuple[str, str]:
    """统一合并 Live 模式下的 AI 分片。"""
    reasoning_parts: List[str] = []
    text_parts: List[str] = []
    _collect_ai_chunk(chunk, reasoning_parts, text_parts, include_round_finish=False)

    if reasoning_parts:
        reasoning_text += "".join(reasoning_parts)
        reasoning_text = re.sub(r"\n{2,}", "\n", reasoning_text)
    if text_parts:
        answer_text += "".join(text_parts)

    return reasoning_text, answer_text


def _get_repo_ai_context(
    repo_path: str, lang: str = "zh"
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """获取仓库 AI 所需上下文，返回 (wiki_id, page_id, repo_id, error_message)。"""
    metadata = fetch_repo_metadata(repo_path)
    unavailable_message = _get_ai_unavailable_message(
        parse_repo_url(repo_path)["repo_path"], metadata
    )
    if unavailable_message:
        return None, None, None, unavailable_message

    if not metadata:
        return None, None, None, tr("errors.fetch_repo_status", lang)

    wiki_id = metadata.get("wiki_id")
    repo_id = metadata.get("repo_id")
    if not wiki_id:
        return None, None, None, tr("errors.repo_missing_docs", lang)

    outline = fetch_repo_outline(repo_path, lang=lang)
    if not outline:
        return None, None, None, tr("errors.repo_has_no_pages", lang)

    page_id = outline[0].get("page_id", "")
    return wiki_id, page_id, repo_id, None


async def _await_with_status(console: Console, message: str, awaitable: Any) -> Any:
    """在 Rich Status 中等待异步结果。"""
    from rich.status import Status

    with Status(message, spinner="dots", console=console):
        return await awaitable


async def _get_first_async_chunk_with_status(
    console: Console, message: str, async_iter: Any
) -> tuple[Any, Optional[Any]]:
    """等待异步迭代器首个可展示分片，返回 (iterator, first_chunk)。"""
    from rich.status import Status

    iterator = async_iter.__aiter__()
    with Status(message, spinner="dots", console=console):
        while True:
            try:
                chunk = await iterator.__anext__()
            except StopAsyncIteration:
                return iterator, None

            if not isinstance(chunk, dict):
                continue
            if chunk.get("event") == "error":
                return iterator, chunk
            if chunk.get("reasoning_content") or chunk.get("text"):
                return iterator, chunk


def send_message(
    talk_id: str,
    query: str,
    wiki_id: str,
    page_id: str,
    repo_id: Optional[str] = None,
    token: Optional[str] = None,
    model: str = "glm-4.7",
    lang: str = "zh",
) -> Optional[str]:
    """
    发送消息并获取 AI 回复（同步版本，调用异步版本）
    :param model: 'glm-4.7' (默认) 或 'claude-sonnet-4.5'
    :return: AI 回复文本（收集所有 round_finish 的内容）
    """
    import asyncio

    full_text = []

    async def collect_result():
        async for item in send_message_async(
            talk_id, query, wiki_id, page_id, repo_id, token, model, lang
        ):
            if not isinstance(item, dict) or "event" not in item:
                continue

            event_type = item.get("event")
            if event_type == "error":
                continue
            # 收集正文内容：
            # - round_finish: 完整段落总结
            # - answer 的 text: 正文片段（不包括 reasoning_content 思考内容）
            if event_type == "round_finish" and item.get("text"):
                full_text.append(item["text"])
            elif event_type == "answer" and item.get("text"):
                full_text.append(item["text"])

    # 运行异步收集器
    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(collect_result())
        else:
            thread_error: List[BaseException] = []

            def _run_in_thread() -> None:
                try:
                    asyncio.run(collect_result())
                except BaseException as exc:
                    thread_error.append(exc)

            thread = threading.Thread(target=_run_in_thread)
            thread.start()
            thread.join()
            if thread_error:
                raise thread_error[0]
    except Exception as e:
        print(f"收集消息结果失败: {e}")
        return None

    # MCP 只需要正文（text），返回完整的 text
    result_text = "\n".join(full_text)
    return result_text if result_text else None


def delete_talk(talk_id: str, token: Optional[str] = None) -> bool:
    """
    删除对话
    :param talk_id: 对话 ID
    :param token: 可选，Bearer Token
    :return: 是否成功
    """
    token = _get_token(token)
    url = f"{BASE_URL}/api/v1/talk/{talk_id}"
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}"}

    try:
        response = httpx.delete(url, headers=headers, timeout=30)
        return response.status_code < 300
    except httpx.RequestError as e:
        print(f"删除对话网络请求失败: {e}")
        return False


def chat_with_ai(
    repo_url_or_path: str,
    query: str,
    token: Optional[str] = None,
    model: str = "glm-4.7",
    lang: str = "zh",
) -> str:
    """
    完整的 AI 对话流程
    :param repo_url_or_path: 支持多种格式: owner/repo 或完整 URL
    :param query: 用户问题
    :param token: 可选，Bearer Token
    :param model: 模型，默认 'glm-4.7'
    :param lang: 语言，默认 'zh'
    :return: AI 回复文本
    """
    token = _get_token(token)

    wiki_id, page_id, repo_id, error_message = _get_repo_ai_context(
        repo_url_or_path, lang
    )
    if error_message:
        return error_message.replace("错误: ", "", 1)

    talk_id = create_talk(token=token, lang=lang)
    if not talk_id:
        return "创建对话失败"

    try:
        answer = send_message(
            talk_id,
            query,
            wiki_id,
            page_id,
            repo_id,
            token=token,
            model=model,
            lang=lang,
        )
        return answer if answer else "未获取到 AI 回复"
    finally:
        delete_talk(talk_id, token=token)


def recommend_repos(topic: str = "", lang: str = "zh") -> Optional[Dict[str, Any]]:
    """
    随机推荐仓库 (按 GitHub topic 标签筛选)
    :param topic: 可选的 GitHub topic 标签，如 "awesome-list", "agent-skills", "python", "rust"
    :param lang: 语言，可选 "zh" 或 "en"
    :return: dict 包含 topics 和 repos，或 None
    """
    url = f"{BASE_URL}/api/v1/repo/recommend"
    params = {"topic": topic} if topic else {}
    headers = {**DEFAULT_HEADERS, "X-Locale": lang}
    cookies = {"X-Locale": lang}

    try:
        response = httpx.get(
            url, headers=headers, cookies=cookies, params=params, timeout=30
        )
        response.raise_for_status()
        result = response.json()
        if result.get("code") == 0:
            return result.get("data")
        else:
            print(
                tr(
                    "errors.recommend_failed_with_reason",
                    lang,
                    detail=result.get("msg", _unknown_error(lang)),
                )
            )
            return None
    except httpx.RequestError as e:
        print(tr("errors.recommend_network_failed", lang, error=e))
        return None
    except json.JSONDecodeError as e:
        print(tr("errors.recommend_parse_failed", lang, error=e))
        return None


def search_repos(query: str, lang: str = "zh") -> Optional[List[Dict[str, Any]]]:
    """
    模糊搜索仓库
    :param query: 搜索词
    :param lang: 语言，默认 'zh'
    :return: list 仓库列表，或 None
    """
    url = f"{BASE_URL}/api/v1/repo"
    params = {"q": query}
    headers = {**DEFAULT_HEADERS, "x-locale": lang}

    try:
        response = httpx.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        result = response.json()
        if result.get("code") == 0:
            return result.get("data", [])
        else:
            print(
                tr(
                    "errors.search_repo_failed_with_reason",
                    lang,
                    detail=result.get("msg", _unknown_error(lang)),
                )
            )
            return None
    except httpx.RequestError as e:
        print(tr("errors.search_repo_network_failed", lang, error=e))
        return None
    except json.JSONDecodeError as e:
        print(tr("errors.search_repo_parse_failed", lang, error=e))
        return None


def get_trending_repos(lang: str = "zh") -> Optional[List[Dict[str, Any]]]:
    """
    获取每周热榜（按周分组返回）
    :param lang: 语言，可选 "zh" 或 "en"
    :return: list 分组数组，每项包含 title/time_span/repos
    """
    url = f"{BASE_URL}/api/v1/public/repo/trending"
    headers = {**DEFAULT_HEADERS, "X-Locale": lang}
    cookies = {"X-Locale": lang}

    try:
        response = httpx.get(url, headers=headers, cookies=cookies, timeout=30)
        response.raise_for_status()
        result = response.json()
        if result.get("code") == 0:
            return result.get("data", [])
        else:
            print(f"获取热榜失败: {result.get('msg', '未知错误')}")
            return None
    except httpx.RequestError as e:
        print(f"获取热榜网络请求失败: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"获取热榜响应解析失败: {e}")
        return None


def get_repo_info(owner_or_path: str, lang: str = "zh") -> Optional[Dict[str, Any]]:
    """
    查看仓库信息和状态
    :param owner_or_path: 仓库路径 (owner/repo 格式)
    :param lang: 语言，可选 "zh" 或 "en"
    :return: dict 仓库信息，或 None
    """
    # 解析 owner/repo 格式
    if "/" not in owner_or_path:
        raise ValueError(tr("errors.invalid_repo_format"))

    parts = owner_or_path.split("/")
    owner = parts[0]
    name = parts[1]

    url = f"{BASE_URL}/api/v1/repo/github/{owner}/{name}"
    headers = {**DEFAULT_HEADERS, "X-Locale": lang}
    cookies = {"X-Locale": lang}

    try:
        response = httpx.get(url, headers=headers, cookies=cookies, timeout=30)
        response.raise_for_status()
        result = response.json()
        if result.get("code") == 0:
            return result.get("data")
        else:
            print(
                tr(
                    "errors.get_repo_info_failed_with_reason",
                    lang,
                    detail=result.get("msg", _unknown_error(lang)),
                )
            )
            return None
    except httpx.RequestError as e:
        print(tr("errors.get_repo_info_network_failed", lang, error=e))
        return None
    except json.JSONDecodeError as e:
        print(tr("errors.get_repo_info_parse_failed", lang, error=e))
        return None


def submit_repo(
    name_or_path: str, notification_email: str = "example@zread.ai"
) -> Optional[Dict[str, Any]]:
    """
    提交索引
    :param name_or_path: 仓库 URL 或路径（支持 github.com/owner/repo 或 owner/repo）
    :param notification_email: 可选的通知邮箱
    :return: dict 提交结果，或 None
    """
    url = f"{BASE_URL}/api/v1/public/repo/submit"
    headers = {**DEFAULT_HEADERS, "Content-Type": "application/json"}
    data = {"name_or_path": name_or_path}
    if notification_email:
        data["notification_email"] = notification_email

    try:
        response = httpx.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        if result.get("code") == 0:
            return result.get("data")
        else:
            print(
                tr(
                    "errors.submit_repo_failed_with_reason",
                    detail=result.get("msg", _unknown_error()),
                )
            )
            return None
    except httpx.RequestError as e:
        print(tr("errors.submit_repo_network_failed", error=e))
        return None
    except json.JSONDecodeError as e:
        print(tr("errors.submit_repo_parse_failed", error=e))
        return None


def refresh_repo(repo_id: str, token: Optional[str] = None) -> bool:
    """
    请求刷新索引
    :param repo_id: 仓库 ID
    :param token: 可选，Bearer Token
    :return: 是否成功
    """
    token = _get_token(token)
    url = f"{BASE_URL}/api/v1/repo/{repo_id}/refresh"
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}"}

    try:
        response = httpx.post(url, headers=headers, timeout=30)
        return response.status_code < 300
    except httpx.RequestError as e:
        print(tr("errors.refresh_repo_network_failed", error=e))
        return False


def fetch_repo_files_with_meta(
    repo_path: str,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    获取仓库内的文件内容及其元数据

    :return: 包含 content, total_lines, size 等信息的字典，失败返回 None
    """
    # 通过 repo_path 获取 repo_id
    parsed = parse_repo_url(repo_path)
    owner, repo = parsed["owner"], parsed["repo"]
    repo_info = get_repo_info(f"{owner}/{repo}")
    if not repo_info:
        print(tr("errors.fetch_repo_info_for_file_failed", repo=repo_path))
        return None

    repo_id = repo_info.get("repo_id")
    if not repo_id:
        print(tr("errors.repo_info_missing_repo_id"))
        return None

    token = _get_token(token, required=False)
    url = f"{BASE_URL}/api/v1/repo/{repo_id}/files"
    headers = {
        **DEFAULT_HEADERS,
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    file_item = {"path": file_path}
    if start_line is not None:
        file_item["start_line"] = start_line
    if end_line is not None:
        file_item["end_line"] = end_line
    data = {"files": [file_item]}

    try:
        response = httpx.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()

        if result.get("code") != 0:
            print(
                tr(
                    "errors.fetch_file_failed_with_reason",
                    detail=result.get("msg", _unknown_error()),
                )
            )
            return None

        files_data = result.get("data", [])
        if not files_data:
            print(tr("errors.file_not_found_or_inaccessible"))
            return None

        file_info = files_data[0]

        # 获取元数据
        total_size = file_info.get("size", 0)
        full_content = file_info.get("content", "")
        total_lines = len(full_content.split("\n")) if full_content else 0

        # 如果有 snippet 字段，优先使用 snippet 的内容
        snippet = file_info.get("snippet")
        if snippet and isinstance(snippet, dict):
            snippet_content = snippet.get("content")
            if snippet_content is not None:
                return {
                    "content": snippet_content,
                    "total_lines": total_lines,
                    "size": total_size,
                    "file_path": file_path,
                    "start_line": snippet.get("start_line"),
                    "end_line": snippet.get("end_line"),
                    "is_snippet": True,
                }

        # 回退：使用 content 字段自行切割
        content = full_content

        # 如果没有指定行号范围，返回完整内容
        if start_line is None and end_line is None:
            return {
                "content": content,
                "total_lines": total_lines,
                "size": total_size,
                "file_path": file_path,
                "start_line": 1,
                "end_line": total_lines,
                "is_snippet": False,
            }

        # 按行分割
        lines = content.split("\n")

        # 处理行号参数（转换为 0-based 索引）
        # 注意：end_line 是包含的（inclusive）
        start_idx = 0
        end_idx = len(lines)

        if start_line is not None:
            start_idx = max(0, start_line - 1)

        if end_line is not None:
            end_idx = min(len(lines), end_line)

        # 确保范围有效
        if start_idx >= end_idx:
            selected_content = ""
            actual_end_line = start_line
        else:
            selected_lines = lines[start_idx:end_idx]
            selected_content = "\n".join(selected_lines)
            actual_end_line = end_line if end_line else len(lines)

        return {
            "content": selected_content,
            "total_lines": total_lines,
            "size": total_size,
            "file_path": file_path,
            "start_line": start_line if start_line else 1,
            "end_line": actual_end_line,
            "is_snippet": False,
        }

    except httpx.RequestError as e:
        print(tr("errors.fetch_file_network_failed", error=e))
        return None
    except json.JSONDecodeError as e:
        print(tr("errors.fetch_file_parse_failed", error=e))
        return None
    except (KeyError, IndexError) as e:
        print(tr("errors.fetch_file_data_parse_failed", error=e))
        return None


def fetch_repo_files(
    repo_path: str,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    token: Optional[str] = None,
) -> Optional[str]:
    """
    获取仓库内的文件内容（兼容 MCP 的简化接口）

    :param repo_path: 仓库路径，支持格式: owner/repo, https://zread.ai/owner/repo, https://github.com/owner/repo
    :param file_path: 文件路径，如 "src/config.ts"
    :param start_line: 可选，开始行号（包含），从 1 开始计数
    :param end_line: 可选，结束行号（包含）
    :param token: 可选，Bearer Token
    :return: 指定行范围的纯文本内容，失败返回 None

    示例:
        # 获取完整文件
        content = fetch_repo_files("openclaw/openclaw", "src/config.ts")

        # 获取前 50 行
        content = fetch_repo_files("openclaw/openclaw", "src/config.ts", start_line=1, end_line=50)

        # 从第 100 行到文件末尾
        content = fetch_repo_files("openclaw/openclaw", "src/config.ts", start_line=100)
    """
    result = fetch_repo_files_with_meta(
        repo_path, file_path, start_line, end_line, token
    )
    return result["content"] if result else None


# ==========================================
# 测试代码
# ==========================================


def run_tests():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("开始测试所有功能")
    print("=" * 70)

    # 测试仓库路径
    TEST_REPO = "openclaw/openclaw"

    # 1. 测试 URL 解析
    print("\n[测试 1/13] URL 解析 (_parse_repo_url)")
    try:
        test_urls = [
            "https://zread.ai/openclaw/openclaw",
            "https://github.com/openclaw/openclaw",
            "openclaw/openclaw",
        ]
        for url in test_urls:
            parsed = parse_repo_url(url)
            assert parsed["owner"] == "openclaw" and parsed["repo"] == "openclaw", (
                f"解析失败: {url}"
            )
        print("  ✓ 通过 - 所有 URL 格式解析正确")
    except Exception as e:
        print(f"  ✗ 失败 - {e}")

    # 2. 测试获取 outline
    print("\n[测试 2/13] 获取文档目录 (fetch_repo_outline)")
    try:
        outline = fetch_repo_outline(TEST_REPO)
        if outline:
            print(f"  ✓ 通过 - 获取到 {len(outline)} 个页面")
            if outline:
                print(f"    第一个页面: {outline[0].get('title', 'N/A')}")
        else:
            print("  ✗ 失败 - 无法获取文档目录（请检查 start_marker 和 end_marker）")
    except Exception as e:
        print(f"  ✗ 失败 - {e}")

    # 3. 测试获取 Markdown
    print("\n[测试 3/13] 获取 Markdown (fetch_markdown)")
    try:
        md = fetch_markdown(TEST_REPO, "1-overview")
        if md and len(md) > 100:
            print(f"  ✓ 通过 - 获取到 {len(md)} 字符")
            print(f"    预览: {md[:50].replace(chr(10), ' ')}...")
        else:
            print("  ✗ 失败 - 未获取到内容")
    except Exception as e:
        print(f"  ✗ 失败 - {e}")

    # 4. 测试搜索 Wiki
    print("\n[测试 4/13] 搜索 Wiki (search_wiki)")
    try:
        result = search_wiki(TEST_REPO, "gateway")
        if result and result != "no result":
            print(f"  ✓ 通过 - 搜索到结果")
            print(f"    预览: {result[:100].replace(chr(10), ' ')}...")
        else:
            print("  ! 警告 - 未搜索到结果（可能是网络或索引问题）")
    except Exception as e:
        print(f"  ✗ 失败 - {e}")

    # 5. 测试推荐仓库
    print("\n[测试 5/13] 推荐仓库 (recommend_repos)")
    try:
        result = recommend_repos()
        if result and result.get("repos"):
            print(f"  ✓ 通过 - 获取到 {len(result.get('repos', []))} 个推荐仓库")
            print(f"    Topics: {', '.join(result.get('topics', [])[:5])}...")
        else:
            print("  ! 警告 - 未获取到推荐")
    except Exception as e:
        print(f"  ✗ 失败 - {e}")

    # 6. 测试搜索仓库
    print("\n[测试 6/13] 搜索仓库 (search_repos)")
    try:
        result = search_repos("openclaw")
        if result and len(result) > 0:
            print(f"  ✓ 通过 - 搜索到 {len(result)} 个仓库")
            print(
                f"    第一个: {result[0].get('owner', 'N/A')}/{result[0].get('name', 'N/A')}"
            )
        else:
            print("  ! 警告 - 未搜索到结果")
    except Exception as e:
        print(f"  ✗ 失败 - {e}")

    # 7. 测试热榜
    print("\n[测试 7/13] 每周热榜 (get_trending_repos)")
    try:
        result = get_trending_repos()
        if result and len(result) > 0:
            print(f"  ✓ 通过 - 获取到 {len(result)} 个热门仓库")
            print(
                f"    第一个: {result[0].get('owner', 'N/A')}/{result[0].get('name', 'N/A')}"
            )
        else:
            print("  ! 警告 - 未获取到热榜")
    except Exception as e:
        print(f"  ✗ 失败 - {e}")

    # 8. 测试获取仓库信息
    print("\n[测试 8/13] 获取仓库信息 (get_repo_info)")
    try:
        result = get_repo_info("openclaw/openclaw")
        if result:
            print(f"  ✓ 通过 - 获取到仓库信息")
            print(f"    Status: {result.get('status', 'N/A')}")
            print(f"    Stars: {result.get('star_count', 'N/A')}")
        else:
            print("  ! 警告 - 未获取到信息")
    except Exception as e:
        print(f"  ✗ 失败 - {e}")

    # 9. 测试提交索引
    print("\n[测试 9/13] 提交索引 (submit_repo)")
    try:
        # 测试已存在的仓库
        result = submit_repo("https://github.com/openclaw/openclaw")
        if result:
            print(f"  ✓ 通过 - 提交成功")
            print(f"    Status: {result.get('status', 'N/A')}")
        else:
            print("  ! 警告 - 提交返回空结果")
    except Exception as e:
        print(f"  ✗ 失败 - {e}")

    # 10. 检查 Token 相关功能
    print("\n[测试 10/13] Token 状态检查")
    if _DEFAULT_TOKEN:
        print(f"  ✓ Token 已设置 ({_DEFAULT_TOKEN[:20]}...)")

        # 11. 测试创建对话
        print("\n[测试 11/13] 创建对话 (create_talk)")
        try:
            # 先获取 repo_id
            repo_info = get_repo_info("openclaw/openclaw")
            if repo_info and repo_info.get("repo_id"):
                talk_id = create_talk()
                if talk_id:
                    print(f"  ✓ 通过 - 创建对话成功")
                    print(f"    talk_id: {talk_id[:30]}...")

                    # 12. 测试删除对话
                    print("\n[测试 12/13] 删除对话 (delete_talk)")
                    success = delete_talk(talk_id)
                    if success:
                        print("  ✓ 通过 - 删除对话成功")
                    else:
                        print("  ! 警告 - 删除对话可能失败")
                else:
                    print("  ! 警告 - 创建对话返回空")
            else:
                print("  ! 跳过 - 无法获取 repo_id")
        except Exception as e:
            print(f"  ✗ 失败 - {e}")

        # 13. 测试完整 AI 对话流程
        print("\n[测试 13/13] 完整 AI 对话 (chat_with_ai)")
        try:
            answer = chat_with_ai(
                TEST_REPO, "你好，简要介绍一下这个项目", model="glm-4.7"
            )
            if answer and len(answer) > 10:
                print(f"  ✓ 通过 - 获取到 AI 回复")
                print(f"    回复: {answer[:80].replace(chr(10), ' ')}...")
            else:
                print("  ! 警告 - AI 回复为空或太短")
        except Exception as e:
            print(f"  ✗ 失败 - {e}")
    else:
        print("  ! 跳过 - Token 未设置，跳过 AI 相关测试")
        print(
            "  设置方式: export ZREAD_TOKEN='your-token' 或 set_default_token('token')"
        )

    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


# ==========================================
# MCP 服务封装
# ==========================================


def _chat_with_repo_ai(
    repo_path: str, question: str, model: str = "glm-4.7", lang: str = "zh"
) -> str:
    """
    与仓库 AI 助手对话（内部完整流程）
    流程: 获取仓库元数据 → 创建会话 → 提问 → 删除会话
    """
    wiki_id, page_id, repo_id, error_message = _get_repo_ai_context(repo_path, lang)
    if error_message:
        return (
            f"❌ {error_message.replace(tr('errors.error_prefix', lang) + ' ', '', 1)}"
        )

    # 获取 token
    try:
        token = _get_token()
    except ValueError:
        return tr("messages.set_token_for_ai", lang)

    # 创建会话
    talk_id = create_talk(token=token, lang=lang)
    if not talk_id:
        return tr("errors.ai_session_create_failed", lang)

    try:
        # 发送消息
        answer = send_message(
            talk_id=talk_id,
            query=question,
            wiki_id=wiki_id,
            page_id=page_id,
            repo_id=repo_id,
            token=token,
            model=model,
            lang=lang,
        )
        return answer if answer else tr("messages.ai_no_valid_reply", lang)
    finally:
        # 清理会话
        try:
            delete_talk(talk_id, token=token)
        except:
            pass


def _fetch_repo_outline(repo_path: str, lang: str = "zh") -> str:
    """
    获取仓库文档目录结构（内部完整流程）
    流程: 获取仓库元数据 → 获取目录
    返回文本格式: wiki_id, repo_id 和目录结构列表（纯文本，用于 MCP）
    """
    # 获取仓库元数据（内部会处理索引提交和刷新）
    data = fetch_repo_metadata(repo_path)
    if not data:
        return tr("errors.fetch_repo_info_retry", lang)
    unavailable_message = _get_ai_unavailable_message(repo_path, data)
    if unavailable_message:
        return f"❌ {unavailable_message.replace(tr('errors.error_prefix', lang) + ' ', '', 1)}"

    repo_id = data.get("repo_id")
    wiki_id = data.get("wiki_id")

    # 获取目录
    outline = fetch_repo_outline(repo_path, lang=lang)
    if not outline:
        return tr("errors.fetch_repo_outline_failed", lang)

    # 解析仓库路径
    parsed = parse_repo_url(repo_path)
    owner, repo = parsed["owner"], parsed["repo"]

    # 使用纯文本格式化（MCP 用纯文本）
    outline_text = _format_outline_plain({"pages": outline}, owner, repo)

    # 添加 wiki_id 和 repo_id 信息
    header = f"wiki_id: {wiki_id or 'N/A'}\nrepo_id: {repo_id or 'N/A'}\n\n"
    return header + outline_text


# ==========================================
# MCP Tools: 文档查询
# ==========================================


def read_doc(repo: str, slug: str) -> str:
    """读取仓库文档页面内容

    根据页面 slug 获取该页面的完整 Markdown 文档内容。

    页面内容中可能包含两种链接：
    - 仓库文件链接: `[文件名](文件路径#L开始行号-L结束行号)`
      使用 `read_source_file(repo, file_path, start_line, end_line)` 获取文件内容
    - 文档导航链接: `[标题](页面slug)`
      使用 `read_doc(repo, slug)` 获取其他页面内容

    Args:
        repo: 仓库路径，格式: owner/repo
        slug: 页面 slug，如 "1-overview", "quick-start"

    Returns:
        页面的 Markdown 格式内容

    Examples:
        read_doc("openclaw/openclaw", "1-overview")
        read_doc("vuejs/vue", "guide-introduction")
    """
    result = fetch_markdown(repo, slug, lang=_DEFAULT_LANG)
    if result:
        return result
    return tr("errors.fetch_page_for_slug_failed", slug=slug)


def search_wiki(repo: str, query: str) -> str:
    """在仓库文档中搜索

    全文搜索指定仓库的文档内容，返回匹配的页面和内容片段。

    Args:
        repo: 仓库路径，格式: owner/repo
        query: 搜索关键词，如 "install", "config", "API"

    Returns:
        纯文本搜索结果，包含页面标题、slug 和内容片段

    Examples:
        search_wiki("python/cpython", "GIL")
        search_wiki("reactjs/react", "hooks")
    """
    return search_wiki(repo, query, lang=_DEFAULT_LANG)


def get_doc_outline(repo: str) -> str:
    """读取仓库文档目录结构

    获取仓库的完整文档大纲，包含所有页面的标题、slug 和层级关系。
    首次调用会自动提交索引请求。
    其中 https://zread.ai/owner/repo/{slug} 路径里的 slug 可直接用于 read_doc(repo, slug)。

    Args:
        repo: 仓库路径，格式: owner/repo

    Returns:
        纯文本目录结构，包含 wiki 信息和页面列表

    Examples:
        get_doc_outline("golang/go")
        get_doc_outline("microsoft/vscode")
    """
    return _fetch_repo_outline(repo, lang=_DEFAULT_LANG)


# ==========================================
# MCP Tools: AI 智能问答
# ==========================================


def ask_ai(repo: str, question: str, model: str = "glm-4.7") -> str:
    """
    向仓库 AI 助手提问（AI 调用 AI）

    此工具让当前的 AI 通过 MCP 协议调用另一个专门的仓库 AI 助手来回答问题。
    被调用的 AI 助手基于仓库文档内容进行分析，并回答你的问题。

    被调用的 AI 助手拥有的工具：
    - search_docs: 文档搜索，查找指南教程文档中的相关页面
    - read_page: 获取指定页面的完整文档内容
    - read_outline: 获取仓库文档的大纲结构
    - read_file: 读取仓库文件的具体内容
    - web_search: 网络搜索，使用简洁的关键词检索相关信息
    - get_repo_structure: 分析并展示代码仓库的目录结构

    如果需要分析特定文件或目录结构，可以在问题中显式要求 AI 使用上述工具进行回复。

    对于仓库代码的复杂需求，应该优先使用此工具，如果有多个问题可并行调用。
    适用于理解项目架构、使用方法、代码示例等复杂问题。
    支持的 AI 模型: glm-4.7 (默认), claude-sonnet-4.5

    返回的 Markdown 回答内容中可能包含两种链接格式：

        1. **仓库文件链接** - 格式: `[文件名](文件路径#L开始行号-L结束行号)`
        例如: `[index.ts](index.ts#L1-L28)` `[package.json](package.json#L1-L77)`
        这类链接指向仓库内的源代码文件，可提取文件路径和行号范围，
        使用 `read_source_file(repo, file_path, start_line, end_line)` 获取具体内容。

        2. **文档导航链接** - 格式: `[标题](页面slug)`
        例如: `[概述](1-overview)` `[快速开始](2-quick-start)`
        这类链接指向文档的其他页面，使用 `read_doc(repo, slug)` 获取该页文档内容。

    Args:
        repo: 仓库路径，格式: owner/repo 或完整 URL
        question: 要向 AI 提问的问题，如 "这个项目是做什么的？"
        model: AI 模型选择，默认 "glm-4.7"，可选 "claude-sonnet-4.5"

    Returns:
        AI 助手的回答内容

    Example:
        ask_ai("openclaw/openclaw", "如何安装这个项目？")
        ask_ai("openclaw/openclaw", "这个项目的登录鉴权逻辑是怎么处理的？")
        ask_ai("openclaw/openclaw", "请使用 get_repo_structure 工具分析项目目录结构")
    """
    return _chat_with_repo_ai(repo, question, model=model, lang=_DEFAULT_LANG)


# ==========================================
# MCP Tools: 仓库发现
# ==========================================


def discover_repo(topic: str = "") -> str:
    """发现推荐仓库 (按 GitHub topic 标签筛选)

    获取 Zread.ai 推荐的优质代码仓库，可按 GitHub topic 标签筛选。

    Args:
        topic: GitHub topic 标签，如 "python", "awesome-list", "agent-skills"。
              不传则返回全部推荐。
              常用标签: awesome-list(精选资源), agent-skills(AI技能),
                      python, rust, machine-learning, javascript

    Returns:
        纯文本推荐结果，可能包含 topics 头信息和仓库列表

    Examples:
        discover_repo()
        discover_repo("python")
        discover_repo("awesome-list")
        discover_repo("agent-skills")
    """
    result = recommend_repos(topic=topic, lang=_DEFAULT_LANG)
    if result:
        repos = result.get("repos", []) if isinstance(result, dict) else []
        topics = result.get("topics", []) if isinstance(result, dict) else []

        lines = []
        if topics:
            lines.append("topics: " + ", ".join(topics))
            lines.append("")
        if repos:
            lines.append(_format_repo_list_plain(repos, _DEFAULT_LANG))
        return "\n".join(lines).strip()
    return tr("errors.fetch_recommend_repo_failed")


def search_repos(query: str) -> str:
    """搜索 GitHub 仓库

    根据关键词模糊搜索已索引的代码仓库。

    Args:
        query: 搜索关键词，如 "react", "http client", "machine learning"

    Returns:
        纯文本仓库列表

    Examples:
        search_repos("axios")
        search_repos("vue")
        search_repos("neural network")
    """
    result = search_repos(query, lang=_DEFAULT_LANG)
    if result:
        return _format_repo_list_plain(result, _DEFAULT_LANG)
    return tr("errors.search_repo_failed")


def get_trending(weeks: int = 1) -> str:
    """获取热门仓库榜单

    获取 GitHub 热门仓库榜单，按周返回。

    Args:
        weeks: 返回最近几周的数据，默认 1 周

    Returns:
        按周分组的纯文本热门仓库榜单

    Examples:
        get_trending()
        get_trending(4)
    """
    result = get_trending_repos(lang=_DEFAULT_LANG)
    if result:
        return _format_trending_plain(result[:weeks], _DEFAULT_LANG)
    return tr("errors.fetch_trending_repo_failed")


def get_repo_info(repo: str) -> str:
    """获取仓库信息

    查询指定仓库在 Zread.ai 的索引状态和基本信息。
    常见 status 字段:
    - "success": 已索引
    - "progress": 索引中
    - "inactive": 尚未收录

    Args:
        repo: 仓库路径，格式: owner/repo

    Returns:
        纯文本仓库信息和索引状态

    Examples:
        get_repo_info("golang/go")
        get_repo_info("torvalds/linux")
    """
    result = get_repo_info(repo, lang=_DEFAULT_LANG)
    if result:
        return _format_status_plain(result, _DEFAULT_LANG)
    return tr("errors.fetch_repo_info_failed")


def read_source_file(
    repo: str,
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> str:
    """读取仓库文件内容

    获取指定仓库中的源代码文件内容，支持按行号范围截取。

    Args:
        repo: 仓库路径，格式: owner/repo
        path: 文件在仓库中的路径，如 "src/config.ts", "README.md"
        start_line: 开始行号（从1开始，包含），不传则从第1行开始
        end_line: 结束行号（包含），不传则到文件末尾

    Returns:
        文件的纯文本内容

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
    )
    if content is None:
        return tr("errors.fetch_file_failed_for_path", path=path)
    return content


# ==========================================
# MCP Resources: 资源访问
# ==========================================


def documentation_page_resource(owner: str, repo: str, page_slug: str) -> str:
    """文档页面资源"""
    return read_doc(f"{owner}/{repo}", page_slug)


def documentation_catalog_resource(owner: str, repo: str) -> str:
    """文档目录资源"""
    return get_doc_outline(f"{owner}/{repo}")


def weekly_trending_resource() -> str:
    """本周热门仓库资源"""
    result = get_trending_repos()
    if result:
        return json.dumps(result, ensure_ascii=False, indent=2)
    return "❌ 获取热门仓库失败"


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


# ==========================================
# 主程序入口
# ==========================================


def _register_tools(mcp: Any, has_token: bool) -> None:
    """
    动态注册 MCP 工具

    Args:
        has_token: 是否有 token，决定注册哪些工具
    """
    # ==========================================
    # 基础工具（不需要 token）
    # ==========================================

    # 文档查询工具
    mcp.tool()(read_doc)
    mcp.tool()(search_wiki)
    mcp.tool()(get_doc_outline)

    # 仓库发现工具
    mcp.tool()(discover_repo)
    mcp.tool()(search_repos)
    mcp.tool()(get_trending)
    mcp.tool()(get_repo_info)

    # 文件获取工具
    mcp.tool()(read_source_file)

    # ==========================================
    # 高级工具（需要 token）
    # ==========================================
    # AI 对话工具 - 仅在 has_token 为 True 时注册
    if has_token:
        mcp.tool()(ask_ai)


def _register_resources(mcp: Any) -> None:
    """注册 MCP 资源（都不需要 token）"""
    mcp.resource("docs://{owner}/{repo}/{page_slug}")(documentation_page_resource)
    mcp.resource("catalog://{owner}/{repo}")(documentation_catalog_resource)
    mcp.resource("trending://weekly")(weekly_trending_resource)


def _register_prompts(mcp: Any) -> None:
    """注册 MCP 提示模板"""
    mcp.prompt()(analyze_project)
    mcp.prompt()(compare_projects)
    mcp.prompt()(learn_project)


def _get_mcp(has_token: bool) -> Any:
    """按需创建并缓存 MCP 实例，避免普通 CLI 启动时导入 fastmcp。"""
    global _MCP_INSTANCE
    if _MCP_INSTANCE is None:
        from fastmcp import FastMCP

        mcp = FastMCP("zread-ai")
        _register_tools(mcp, has_token)
        _register_resources(mcp)
        _register_prompts(mcp)
        _MCP_INSTANCE = mcp
    return _MCP_INSTANCE


# 创建 Typer CLI app
cli_app = typer.Typer(
    help=tr("cli.app_help"),
    add_completion=False,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _set_token(token: Optional[str]) -> None:
    """设置全局 token"""
    global _DEFAULT_TOKEN
    if token:
        _DEFAULT_TOKEN = token


def _print_help_with_env(ctx: typer.Context) -> None:
    """打印帮助信息并附加环境变量面板"""
    # 先打印标准帮助
    typer.echo(ctx.get_help())

    # 添加环境变量面板
    console = Console()
    env_table = Table(show_header=False, box=None, padding=(0, 2))
    env_table.add_row("[green]ZREAD_TOKEN[/green]", tr("cli.env_var_token_desc"))
    env_table.add_row("[green]ZREAD_LANG[/green]", tr("cli.env_var_lang_desc"))

    env_panel = Panel(
        env_table,
        title=f"[bold cyan]{tr('cli.env_vars_title')}[/bold cyan]",
        border_style="blue",
        padding=(1, 2),
    )
    console.print(env_panel)

    # 添加配置文件路径面板
    config_path = _get_config_path()
    config_table = Table(show_header=False, box=None, padding=(0, 2))
    if sys.platform == "darwin":
        config_table.add_row("[cyan]~/.config/zread/zread.toml[/cyan]", tr("config.macos"))
    elif sys.platform == "win32":
        config_table.add_row("[cyan]%APPDATA%\\zread\\zread.toml[/cyan]", tr("config.windows"))
    else:
        config_table.add_row("[cyan]~/.config/zread/zread.toml[/cyan]", tr("config.linux"))
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


def _cli_http_get(
    url: str,
    lang: str = "zh",
    error_msg: str = "请求失败",
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    cookies: Optional[dict] = None,
    timeout: int = 30,
) -> dict:
    """CLI 命令中执行 HTTP GET 请求（基于 _http_get，失败时退出）

    Args:
        url: 请求 URL
        lang: 语言，自动添加 x-locale header 和 cookie
        error_msg: 错误提示信息
        params: URL 查询参数
        headers: 额外的请求头
        cookies: 额外的 cookies
        timeout: 超时时间（秒）

    Returns:
        API 响应的 data 字段

    Raises:
        typer.Exit: 请求失败时退出
    """
    result = _http_get(
        url=url,
        lang=lang,
        error_msg=error_msg,
        params=params,
        headers=headers,
        cookies=cookies,
        timeout=timeout,
    )
    if result is None:
        raise typer.Exit(1)
    return result


def _run_with_cli_status(
    enabled: bool, message: str, fn: Callable[..., Any], *args, **kwargs
) -> Any:
    """在 Rich 渲染路径下为数据获取阶段显示等待动画。"""
    if not enabled:
        return fn(*args, **kwargs)

    console = Console()
    from rich.status import Status

    status = Status(message, spinner="dots", console=console)
    status._live.start(refresh=True)
    try:
        return fn(*args, **kwargs)
    finally:
        status.stop()


@cli_app.command(name="mcp", help=tr("cli.commands.mcp"))
def cmd_mcp(
    transport: Annotated[str, typer.Argument(help=tr("cli.args.transport"))] = "stdio",
    address: Annotated[
        Optional[str],
        typer.Argument(help=tr("cli.args.address")),
    ] = None,
    token: Annotated[
        Optional[str], typer.Option("--token", "-t", help=tr("cli.options.token"))
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

    # 解析地址参数
    host, port, path = _parse_address(transport, address)

    _run_mcp_server(transport, host, port, path, token)


@cli_app.command(name="ls", help=tr("cli.commands.ls"))
def cmd_get_outline(
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
    ] = False,
) -> None:
    """获取文档目录结构

    示例:
        ls golang/go
        ls python/cpython -p
        ls rust-lang/rust
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
    )
    if not outline:
        typer.echo(tr("errors.fetch_outline", lang), err=True)
        raise typer.Exit(1)

    # 解析仓库路径
    parsed = parse_repo_url(repo)
    owner, repo_name = parsed["owner"], parsed["repo"]

    if json_output:
        typer.echo(json.dumps({"pages": outline}, ensure_ascii=False, indent=2))
    elif plain:
        output = _format_outline_plain({"pages": outline}, owner, repo_name)
        typer.echo(output)
    else:
        _format_outline_rich({"pages": outline}, owner, repo_name)


# zread slug 模式: 纯数字序号 或 数字前缀 slug
ZREAD_SLUG_PATTERN = re.compile(r"^(?:\d+|\d+-[a-z][a-z-]*)$")


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
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help=tr("cli.options.json"))
    ] = False,
    plain: Annotated[
        bool, typer.Option("--plain", "-p", help=tr("cli.options.plain"))
    ] = False,
) -> None:
    """查看仓库内容（支持 zread 文档或 GitHub 文件）

    自动识别参数类型:
    - zread slug 格式(如: 1-overview, 1): 读取 zread 文档页面
    - 其他格式: 读取 GitHub 文件内容

    示例:
        cat vuejs/vue                          # 默认读取 zread 首页
        cat vuejs/vue 1-overview               # zread 文档页面
        cat golang/go README.md                # GitHub 文件
        cat python/cpython Lib/http/client.py  # GitHub 文件
        cat facebook/react README.md 5:20      # 指定行号范围
        cat facebook/react/README.md 5:20      # repo包含文件路径+行号
    """
    if not repo_or_url:
        typer.echo(ctx.get_help())
        typer.echo(f"\n❌ {tr('errors.missing_repo_or_url')}", err=True)
        raise typer.Exit(1)
    lang = _resolve_lang(lang)

    # 收集所有位置参数
    all_args = [repo_or_url]
    # 使用 ctx.params 来检查参数是否被用户显式提供
    # typer 会将用户提供的参数设置为具体的值，未提供则为 None
    if path_or_slug is not None:
        all_args.append(path_or_slug)
    if arg3:
        all_args.append(arg3)
    # 添加 extra_args
    all_args.extend(ctx.args)

    # 按顺序解析参数: repo[/path], [slug_or_path], [line_range], [end_line]
    owner_repo, file_path, start_line, end_line, is_zread_page = _parse_cat_args(
        all_args
    )

    if is_zread_page:
        _cat_zread_page(owner_repo, file_path or "1-overview", lang, json_output, plain)
    else:
        _cat_github_file_parsed(
            owner_repo, file_path, start_line, end_line, json_output, plain
        )


def _is_zread_slug(value: str) -> bool:
    """判断参数是否为 zread 页面 slug。"""
    return ZREAD_SLUG_PATTERN.fullmatch(value.strip()) is not None


def _parse_cat_args(
    args: List[str],
) -> Tuple[str, Optional[str], Optional[int], Optional[int], bool]:
    """按顺序解析 cat 命令的参数

    参数顺序:
    - zread 文档: owner/repo [slug]
    - GitHub 文件: owner/repo[/path] [path] [start] [end]

    GitHub 文件模式支持示例:
    - github.com/owner/repo/README.md#L1-10
    - owner/repo README.md
    - owner/repo/README.md
    - owner/repo README.md 5 10
    - owner/repo README.md 5:10 / 5~10 / 5-10
    - owner/repo README.md 5 / 5: / 5~ / 5-
    - owner/repo README.md :10 / ~10 / -10

    返回: (owner_repo, file_path_or_slug, start_line, end_line, is_zread_page)
    """
    if not args:
        return ("", None, None, None, False)

    parsed = parse_repo_url(args[0])
    owner_repo = parsed["repo_path"]
    remaining_args = list(args[1:])

    embedded_path = parsed.get("file_path")
    source = parsed.get("source")
    start_line = parsed.get("start_line")
    end_line = parsed.get("end_line")

    # zread 文档模式要求第一个参数只包含 repo，不带文件路径
    if embedded_path is None:
        if not remaining_args:
            return (owner_repo, "1-overview", None, None, True)
        if _is_zread_slug(remaining_args[0]):
            return (owner_repo, remaining_args[0], None, None, True)

    # zread 页面 URL：如 https://zread.com/owner/repo/1-overview
    if (
        source == "zread"
        and embedded_path is not None
        and _is_zread_slug(embedded_path)
        and start_line is None
        and end_line is None
        and not remaining_args
    ):
        return (owner_repo, embedded_path, None, None, True)

    file_path = embedded_path
    if file_path is None:
        if not remaining_args:
            return (owner_repo, None, start_line, end_line, False)
        file_path = remaining_args.pop(0)

    if remaining_args and start_line is None:
        parsed_start, parsed_end = _parse_line_range(remaining_args[0])
        if parsed_start is not None:
            start_line = parsed_start
            end_line = parsed_end
            remaining_args.pop(0)

    if remaining_args and end_line is None and remaining_args[0].isdigit():
        end_line = int(remaining_args.pop(0))

    return (owner_repo, file_path, start_line, end_line, False)


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
    # 5:20 或 5-20 格式
    range_match = re.match(r"^(?:#L)?(\d+)[:~-]L?(\d+)$", arg)
    if range_match:
        return (int(range_match.group(1)), int(range_match.group(2)))

    # 5: 或 5- 格式（仅起始行）
    start_only_match = re.match(r"^(?:#L)?(\d+)[:~-]$", arg)
    if start_only_match:
        return (int(start_only_match.group(1)), None)

    # :10, -10, ~10 格式（前N行）
    prefix_match = re.match(r"^[:~-](\d+)$", arg)
    if prefix_match:
        return (1, int(prefix_match.group(1)))

    # #L5、L5 或 5 格式（仅起始行）
    single_match = re.match(r"^(?:#L|L)?(\d+)$", arg)
    if single_match:
        return (int(single_match.group(1)), None)

    return (None, None)


def _cat_zread_page(
    repo: str,
    slug: str,
    lang: str,
    json_output: bool,
    plain: bool,
) -> None:
    """读取 zread 文档页面"""
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
    )
    if not content and slug == "1-overview":
        pages = pages or _run_with_cli_status(
            use_status,
            f"[dim]{tr('status.locate_default_page', lang)}[/dim]",
            fetch_repo_outline,
            repo,
            lang=lang,
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
        page_url = f"https://zread.ai/{parsed['repo_path']}/{actual_slug}"

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

    # 使用 Rich 渲染 Markdown（除非指定 --plain 或未安装 Rich）
    if json_output:
        typer.echo(json.dumps({"content": content}, ensure_ascii=False, indent=2))
    elif not plain:
        console = Console()
        # 预加载图片
        _preload_images_sync(content)
        # 根据系统主题选择代码高亮主题
        theme = _get_syntax_theme()
        md = ImageAwareMarkdown(content, code_theme=theme)
        console.print(md)
    else:
        typer.echo(content)


def _process_markdown_links(content: str, repo: str) -> str:
    """处理 markdown 中的链接

    - slug 格式链接: [xxx](slug) -> [🔗xxx](https://zread.ai/owner/repo/slug)
    - 代码文件链接: [xxx](path/file.py) -> [🐙xxx](path/file.py)
    """
    import re

    parsed = parse_repo_url(repo)
    repo_path = parsed["repo_path"]

    # 匹配 markdown 链接: [text](url)，排除图片 ![text](url)
    # 使用递归方式处理嵌套的 []，如 [🐙来源: [README.md](/README.md#L1-L6)]
    link_pattern = re.compile(
        r"(?<!!)\[(?:[^\[\]]|\[(?:[^\[\]]|\[[^\[\]]*\])*\])*\]\(([^)]+)\)"
    )

    # slug 格式: 数字-名称
    slug_pattern = re.compile(r"^\d+-[a-zA-Z0-9-]+(?<!-)$")

    def _prefix_slug_text(text: str, slug: str) -> str:
        slug_num_match = re.match(r"^(\d+)-", slug)
        if not slug_num_match:
            return text
        prefix = f"{slug_num_match.group(1)}."
        return text if text.startswith(prefix) else f"{prefix}{text}"

    def _rewrite_markdown_link(full_match: str, text: str, url: str) -> str:
        url_path = url.split("#")[0]
        last_segment = url_path.split("/")[-1] if "/" in url_path else url_path
        last_segment = last_segment.lstrip("/")

        if slug_pattern.match(last_segment):
            link_text = _prefix_slug_text(text, last_segment)
            if url.startswith(("http://", "https://")):
                full_url = url
            elif url.startswith("/"):
                full_url = f"https://zread.ai{url}"
            else:
                full_url = f"https://zread.ai/{repo_path}/{url}"
            return f"[🔗{link_text}]({full_url})"

        if "." in last_segment:
            if url.startswith(("http://", "https://")):
                full_url = url
            else:
                file_path = url.lstrip("/")
                full_url = f"https://github.com/{repo_path}/blob/main/{file_path}"
            return f"[🐙{text}]({full_url})"

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
            json.dumps(
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


def _cat_github_file_parsed(
    owner_repo: str,
    file_path: Optional[str],
    start_line: Optional[int],
    end_line: Optional[int],
    json_output: bool,
    plain: bool,
) -> None:
    """读取 GitHub 文件内容（已解析参数）"""
    if not owner_repo or not file_path:
        typer.echo(tr("errors.parse_repo_and_file_failed"), err=True)
        raise typer.Exit(1)

    # 获取文件内容及元数据
    file_meta = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.fetch_file_content')}[/dim]",
        fetch_repo_files_with_meta,
        owner_repo,
        file_path,
        start_line,
        end_line,
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


def _cat_github_file(
    ctx: typer.Context,
    repo_or_url: str,
    path_or_range: str,
    json_output: bool,
    plain: bool,
) -> None:
    """读取 GitHub 文件内容（兼容旧版本，使用新的解析逻辑）"""
    # 收集所有参数
    all_args = [repo_or_url, path_or_range]
    all_args.extend(ctx.args if ctx.args else [])

    # 使用统一的解析函数
    owner_repo, file_path, start_line, end_line, _ = _parse_cat_args(all_args)

    # 调用新的实现
    _cat_github_file_parsed(
        owner_repo, file_path, start_line, end_line, json_output, plain
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
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help=tr("cli.options.json"))
    ] = False,
    plain: Annotated[
        bool, typer.Option("--plain", "-p", help=tr("cli.options.plain"))
    ] = False,
) -> None:
    """搜索仓库或文档关键词

    用法:
        find <query>                      # 搜索 GitHub 仓库
        find <repo> <query>               # 在指定仓库文档内搜索

    示例:
        find axios
        find python http client
        find machine learning library
        find facebook/react context api
        find golang/go goroutine scheduler
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
        # query 是有效的仓库路径
        if repo:
            # 有第二个参数，在仓库文档内搜索
            keyword = repo
            # 检查是否还有更多参数，合并到关键词
            if ctx.args:
                keyword += " " + " ".join(ctx.args)
            _search_in_repo(query, keyword, lang, json_output, plain)
        else:
            # 只有一个参数且是 owner/repo 格式，获取该仓库信息
            # 或者显示仓库列表
            _search_repos(query, lang, json_output, plain)
    except ValueError:
        # query 不是有效的仓库路径，在 GitHub 上搜索
        full_query = query
        if repo:
            full_query += " " + repo
        if ctx.args:
            full_query += " " + " ".join(ctx.args)
        _search_repos(full_query, lang, json_output, plain)


def _search_in_repo(
    repo: str, keyword: str, lang: str, json_output: bool, plain: bool = False
) -> None:
    """在仓库文档内搜索关键词"""
    status = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.fetch_repo_info', lang)}[/dim]",
        fetch_repo_metadata,
        repo,
    )
    if not status or not status.get("wiki_id"):
        typer.echo(tr("errors.fetch_repo_metadata", lang), err=True)
        raise typer.Exit(1)

    wiki_id = status["wiki_id"]
    search_url = f"{BASE_URL}/api/v1/wiki/{wiki_id}/search"

    results = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.search_docs', lang)}[/dim]",
        _cli_http_get,
        search_url,
        lang=lang,
        error_msg=tr("errors.search_failed", lang),
        params={"q": keyword},
    )

    if json_output:
        typer.echo(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if not results:
        typer.echo(tr("messages.no_results", lang))
        return

    if plain:
        output = _format_search_results_plain(results)
        typer.echo(output)
    else:
        _format_search_results_rich(results, repo)


def _search_repos(
    query: str, lang: str, json_output: bool, plain: bool = False
) -> None:
    """搜索 GitHub 仓库"""
    data = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.search_repos', lang)}[/dim]",
        _cli_http_get,
        f"{BASE_URL}/api/v1/repo?q={urllib.parse.quote(query)}",
        lang=lang,
        error_msg=tr("errors.search_failed", lang),
    )
    if isinstance(data, dict):
        data = data.get("list", [])

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
    ] = False,
) -> None:
    """获取热门仓库榜单

    示例:
        top
        top 4
        top 2 --json
        top --plain
    """
    lang = _resolve_lang(lang)
    result = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.fetch_trending', lang)}[/dim]",
        _cli_http_get,
        f"{BASE_URL}/api/v1/public/repo/trending",
        lang=lang,
        error_msg=tr("errors.fetch_trending", lang),
    )
    # 限制显示最近 weeks 周的榜单
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
    ] = False,
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
    url = f"{BASE_URL}/api/v1/repo/recommend"
    if topic:
        url += f"?topic={urllib.parse.quote(topic)}"
    data = _run_with_cli_status(
        not (json_output or plain),
        f"[dim]{tr('status.fetch_recommend', lang)}[/dim]",
        _cli_http_get,
        url,
        lang=lang,
        error_msg=tr("errors.fetch_recommend", lang),
    )

    if json_output:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    repos = data.get("repos", []) if isinstance(data, dict) else data
    if plain:
        output = _format_repo_list_plain(repos or [], lang)
        typer.echo(output)
    else:
        _format_repo_list_rich(repos or [], lang)


def _background_submit_repo(repo_path: str) -> None:
    """后台异步提交仓库索引（不阻塞主流程）"""

    def _submit():
        try:
            submit_repo(repo_path)
        except Exception:
            pass  # 后台任务不抛出错误

    threading.Thread(target=_submit, daemon=True).start()


def _background_refresh_repo(repo_id: str) -> None:
    """后台异步刷新仓库索引（不阻塞主流程）"""

    def _refresh():
        try:
            refresh_repo(repo_id)
        except Exception:
            pass  # 后台任务不抛出错误

    threading.Thread(target=_refresh, daemon=True).start()


def fetch_repo_metadata(repo_url_or_path: str) -> Optional[Dict[str, Any]]:
    """
    获取仓库元数据

    如果仓库状态为 inactive（未收录）或超过5天未更新，会触发后台异步任务。

    :param repo_url_or_path: 支持多种格式:
        - https://zread.ai/owner/repo
        - https://github.com/owner/repo
        - owner/repo
    :return: API 返回的完整 data 字段，失败返回 None
    """
    parsed = parse_repo_url(repo_url_or_path)
    repo_path = parsed["repo_path"]
    owner, name = parsed["owner"], parsed["repo"]
    try:
        response = httpx.get(
            f"{BASE_URL}/api/v1/repo/github/{owner}/{name}",
            headers=DEFAULT_HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("code") != 0:
            return None
        data = result.get("data", {})

        # 检查状态，触发后台异步任务
        status = data.get("status", "")
        repo_id = data.get("repo_id", "")
        updated_at = data.get("updated_at", 0)

        if status == "inactive":
            # 仓库未收录，后台提交索引
            _background_submit_repo(repo_path)
        elif status == "success" and repo_id and updated_at:
            # 已收录，检查是否超过5天未更新
            days_since_update = (time.time() - updated_at) / (24 * 3600)
            if days_since_update > 5:
                _background_refresh_repo(repo_id)

        return data
    except httpx.RequestError:
        return None


def _get_ai_unavailable_message(
    repo_path: str, metadata: Optional[Dict[str, Any]]
) -> str:
    """根据仓库状态生成 AI 不可用提示。"""
    if not metadata:
        return tr("errors.fetch_repo_status")

    if metadata.get("wiki_id"):
        return ""

    status = metadata.get("status", "")
    if status == "inactive":
        return tr("errors.repo_not_indexed", repo=repo_path)
    if status == "progress":
        return tr("errors.repo_indexing", repo=repo_path)
    if not metadata.get("wiki_id"):
        return tr("errors.repo_missing_docs")
    return tr("errors.repo_ai_unavailable")


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
    ] = False,
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

    if json_output:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
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


def _ai_help() -> str:
    """Get AI command help with dynamic token status."""
    help_text = tr("cli.commands.ai")
    if os.environ.get("ZREAD_TOKEN") or _CONFIG_FROM_FILE.get("token"):
        return help_text.replace(" (token required)", " (token ready)")
    return help_text


@cli_app.command(
    name="ai",
    help=_ai_help(),
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def cmd_ai(
    ctx: typer.Context,
    repo: Annotated[Optional[str], typer.Argument(help=tr("cli.args.repo"))] = None,
    question: Annotated[
        Optional[str], typer.Argument(help=tr("cli.args.question_optional"))
    ] = None,
    lang: Annotated[
        Optional[str], typer.Option("--lang", "-l", help=tr("cli.options.lang"))
    ] = None,
    token: Annotated[
        Optional[str], typer.Option("--token", "-t", help=tr("cli.options.token"))
    ] = None,
    plain: Annotated[
        bool, typer.Option("--plain", "-p", help=tr("cli.options.ai_plain"))
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help=tr("cli.options.ai_json"))
    ] = False,
    model: Annotated[
        str, typer.Option("--model", "-m", help=tr("cli.options.model"))
    ] = "glm-4.7",
) -> None:
    """向仓库 AI 提问 (需要 token)

    示例:
        ai golang/go                           # 进入交互对话模式
        ai golang/go "channel 和 mutex 怎么选择"
        ai python/cpython "GIL 机制和并发优化" --plain
        ai rust-lang/rust "所有权规则" -t your_token
        ai facebook/react "hooks原理" --model claude-sonnet-4.5
    """
    if not repo:
        typer.echo(ctx.get_help())
        typer.echo(f"\n❌ {tr('errors.missing_repo')}", err=True)
        raise typer.Exit(1)
    if ctx.args:
        question_parts = [question] if question else []
        question_parts.extend(ctx.args)
        question = " ".join(part for part in question_parts if part).strip() or None

    import asyncio

    _set_token(token)
    if not _DEFAULT_TOKEN:
        typer.echo(tr("errors.ai_requires_token"), err=True)
        raise typer.Exit(1)
    lang = _resolve_lang(lang)

    try:
        if question:
            _, _, _, error_message = _get_repo_ai_context(repo, lang)
            if error_message:
                typer.echo(error_message, err=True)
                raise typer.Exit(1)

            talk_id = create_talk(_DEFAULT_TOKEN, lang)
            if not talk_id:
                typer.echo(tr("errors.create_talk", lang), err=True)
                raise typer.Exit(1)

            asyncio.run(
                _ask_single_turn(
                    talk_id, repo, question, lang, plain, json_output, model
                )
            )
            delete_talk(talk_id, _DEFAULT_TOKEN)
        else:
            # 进入交互模式（所有初始化在内部异步进行，立即显示提示）
            asyncio.run(_ask_interactive(repo, lang, plain, model, _DEFAULT_TOKEN))
    except KeyboardInterrupt:
        pass


async def _ask_single_turn(
    talk_id: str,
    repo_path: str,
    question: str,
    lang: str,
    plain: bool,
    json_output: bool,
    model: str = "glm-4.7",
) -> None:
    """单轮对话"""
    if json_output:
        full_reasoning = []
        full_text = []

        async for chunk in send_repo_message_async(
            talk_id, repo_path, question, None, model, lang
        ):
            error_message = _collect_ai_chunk(
                chunk, full_reasoning, full_text, include_round_finish=False
            )
            if error_message:
                typer.echo(
                    json.dumps(
                        {
                            "reasoning_content": "".join(full_reasoning),
                            "text": "".join(full_text),
                            "error": error_message,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return

        result = {
            "reasoning_content": "".join(full_reasoning),
            "text": "".join(full_text),
        }
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    elif plain:
        # 只流式打印正文（只处理 answer 事件，避免 round_finish 重复）
        async for chunk in send_repo_message_async(
            talk_id, repo_path, question, None, model, lang
        ):
            if chunk and isinstance(chunk, dict) and "event" in chunk:
                # 只处理 answer 事件，跳过 round_finish 避免重复
                if chunk.get("event") == "answer":
                    text = chunk.get("text", "")
                    if text:
                        typer.echo(text, nl=False)
                elif chunk.get("event") == "error":
                    typer.echo(
                        f"\n{tr('errors.error_prefix', lang)} {chunk.get('text', tr('messages.unknown_error', lang))}",
                        err=True,
                    )
                    return
        typer.echo("")
    else:
        from rich.console import Console

        console = Console()
        wiki_id, page_id, repo_id, error_message = await _await_with_status(
            console,
            f"[dim]{tr('status.preparing', lang)}[/dim]",
            asyncio.to_thread(_get_repo_ai_context, repo_path, lang),
        )
        if error_message:
            console.print(
                f"[red]❌ {error_message.replace(tr('errors.error_prefix', lang) + ' ', '', 1)}[/]"
            )
            return

        await _ask_with_live(
            talk_id,
            repo_path,
            question,
            lang,
            model,
            wiki_id,
            page_id,
            repo_id,
            console,
        )


async def _init_chat_session(
    repo_path: str, lang: str, token: str
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """后台初始化：创建对话并获取仓库信息
    返回: (talk_id, wiki_id, page_id, repo_id)
    """
    talk_id = create_talk(token, lang)
    wiki_id, page_id, repo_id, error_message = _get_repo_ai_context(repo_path, lang)
    if error_message:
        return talk_id, None, None, None
    return talk_id, wiki_id, page_id, repo_id


async def _async_input(prompt: str = "") -> str:
    """异步获取用户输入，避免 input() 在复杂终端渲染下触发解码异常。"""

    def _read_line() -> str:
        sys.stdout.write(prompt)
        sys.stdout.flush()

        raw = sys.stdin.buffer.readline()
        if not raw:
            return "exit"

        raw = raw.rstrip(b"\r\n")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="ignore")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _read_line)


async def _ask_interactive(
    repo_path: str, lang: str, plain: bool, model: str, token: str
) -> None:
    """交互式多轮对话 - 启动即刻输入，支持双重加载动画"""
    from rich.console import Console

    console = Console()
    console.print(
        f"\n[bold green]🤖 {tr('messages.ai_mode_title', lang)}[/] ([cyan]{tr('messages.repo_label', lang)}: {repo_path}[/])"
    )
    console.print(f"[dim]{tr('messages.ai_mode_hint', lang)}[/]\n")

    # 立即后台异步初始化（创建对话 + 获取仓库信息）
    init_task = asyncio.create_task(_init_chat_session(repo_path, lang, token))

    talk_id: Optional[str] = None
    wiki_id: Optional[str] = None
    page_id: Optional[str] = None
    repo_id: Optional[str] = None

    try:
        while True:
            try:
                # 异步获取用户输入（不会阻塞事件循环，后台任务可以继续执行）
                print()
                user_input = await _async_input("✨ ")

                if user_input.strip().lower() in ("/exit", "exit", "quit"):
                    break
                if not user_input.strip():
                    continue

                if not init_task.done():
                    talk_id, wiki_id, page_id, repo_id = await _await_with_status(
                        console,
                        f"[dim]{tr('status.preparing', lang)}[/dim]",
                        init_task,
                    )
                elif talk_id is None:
                    talk_id, wiki_id, page_id, repo_id = await init_task

                if talk_id is None:
                    typer.echo(f"❌ {tr('errors.create_talk', lang)}", err=True)
                    continue
                if wiki_id is None:
                    typer.echo(f"❌ {tr('errors.fetch_repo_metadata', lang)}", err=True)
                    continue

                # 准备生成器
                gen = send_repo_message_async(
                    talk_id,
                    repo_path,
                    user_input,
                    None,
                    model,
                    lang,
                    wiki_id,
                    page_id,
                    repo_id,
                )

                if plain:
                    it, first_chunk = await _get_first_async_chunk_with_status(
                        console, f"[dim]{tr('status.thinking', lang)}[/dim]", gen
                    )

                    # 渲染首包及后续包
                    if first_chunk:
                        if first_chunk.get("event") == "answer":
                            print(first_chunk.get("text", ""), end="", flush=True)
                        async for chunk in it:  # 继续迭代
                            if chunk.get("event") == "answer":
                                print(chunk.get("text", ""), end="", flush=True)
                    print()  # 确保最后有换行
                else:
                    # --- 动画 2: 等待 AI 首包响应 (Rich Live 模式) ---
                    await _ask_with_live(
                        talk_id,
                        repo_path,
                        user_input,
                        lang,
                        model,
                        wiki_id,
                        page_id,
                        repo_id,
                        console,
                    )
                    print()  # 确保最后有换行

            except EOFError:
                break
    finally:
        if talk_id:
            delete_talk(talk_id, token)


async def _ask_with_live(
    talk_id: str,
    repo_path: str,
    question: str,
    lang: str,
    model: str,
    wiki_id: Optional[str],
    page_id: Optional[str],
    repo_id: Optional[str],
    console: Console,
) -> None:
    """优化版的 Live 渲染，处理首包加载"""
    from rich.console import Group

    gen = send_repo_message_async(
        talk_id, repo_path, question, None, model, lang, wiki_id, page_id, repo_id
    )
    it, first_chunk = await _get_first_async_chunk_with_status(
        console, f"[dim]{tr('status.thinking', lang)}[/dim]", gen
    )
    if first_chunk is None:
        return

    # 进入 Live 渲染循环
    reasoning_text = ""
    answer_text = ""

    # 辅助函数：处理 chunk 数据
    def process_chunk(chunk):
        nonlocal reasoning_text, answer_text
        reasoning_text, answer_text = _merge_live_ai_chunk(
            chunk, reasoning_text, answer_text
        )

    # 处理首个 chunk
    process_chunk(first_chunk)

    with Live(console=console, refresh_per_second=12, transient=False) as live:

        def update_display():
            panels = []
            if reasoning_text:
                panels.append(
                    Panel(
                        Text(reasoning_text.replace("\n", "  "), style="dim"),
                        title=tr("messages.reasoning_title", lang),
                        box=SIMPLE_HEAD,
                        title_align="left",
                    )
                )
            if answer_text:
                text_display = _process_markdown_links(answer_text, repo_path)
                panels.append(
                    Panel(
                        Markdown(text_display),
                        title="🤖",
                        border_style="green",
                        title_align="left",
                    )
                )
            if panels:
                live.update(Group(*panels))

        update_display()  # 渲染第一帧

        async for chunk in it:
            process_chunk(chunk)
            update_display()


# ==========================================
# Export 功能：导出仓库文档到本地
# ==========================================


async def _fetch_page_async(
    client: httpx.AsyncClient,
    repo: str,
    page: Dict[str, Any],
    lang: str,
    output_dir: Path,
    progress_cb: Optional[Callable[[], None]] = None,
) -> Dict[str, Any]:
    """异步获取单个页面内容并保存"""
    slug = page.get("slug", "")
    topic = page.get("topic", "")
    group = page.get("group", "")
    section = page.get("section", "")

    if not slug:
        return {"success": False, "page": page, "error": "no slug"}

    try:
        # 获取 markdown 内容
        parsed = parse_repo_url(repo)
        zread_url = parsed["zread_url"]
        url = f"{zread_url}/{slug}"
        response = await client.get(
            url,
            cookies={"X-Locale": lang},
            headers={**DEFAULT_HEADERS, "RSC": "1"},
            timeout=30.0,
        )
        response.raise_for_status()
        content = response.content

        # 解析 markdown 内容（复用 fetch_markdown 的逻辑）
        marker = b",---"
        end_pos = content.rfind(marker)
        if end_pos == -1:
            raise ValueError("Invalid response format: marker not found")

        line_start = content.rfind(b"\n", 0, end_pos)
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1

        header_line = content[line_start : end_pos + 1].decode("latin-1")
        head_pattern = re.compile(r"^([0-9a-f]+):T([0-9a-f]+),")
        match = head_pattern.match(header_line)
        if not match:
            raise ValueError(f"Invalid header format: {header_line[:50]}")

        byte_length = int(match.group(2), 16)
        header_end = line_start + match.end()
        md_content = content[header_end : header_end + byte_length].decode("utf-8")

        # 保存到文件（直接放在 repo_dir 下）
        file_path = output_dir / f"{slug}.md"
        file_path.write_text(md_content, encoding="utf-8")

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


async def _export_repo_async(
    repo: str,
    output_dir: Path,
    lang: str,
    concurrency: int,
    progress: Optional[Progress] = None,
    task_id: Optional[int] = None,
    pages: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """异步导出仓库文档"""
    # 获取目录结构（如果未提供）
    if pages is None:
        pages = fetch_repo_outline(repo, lang=lang)
    if not pages:
        return {"success": False, "error": "无法获取文档大纲"}

    parsed = parse_repo_url(repo)
    owner, repo_name = parsed["owner"], parsed["repo"]

    # 创建输出目录
    repo_dir = output_dir / f"{owner}-{repo_name}"
    repo_dir.mkdir(parents=True, exist_ok=True)

    # 并发下载所有页面
    results = []
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

        async def fetch_with_limit(page):
            async with semaphore:
                return await _fetch_page_async(
                    client, repo, page, lang, repo_dir, make_progress_cb()
                )

        tasks = [fetch_with_limit(page) for page in pages]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # 处理结果
    successful = []
    failed = []
    for r in results:
        if isinstance(r, Exception):
            failed.append({"error": str(r)})
        elif r.get("success"):
            successful.append(r)
        else:
            failed.append(r)

    # 获取仓库信息
    repo_info = fetch_repo_metadata(repo)

    # 生成 llms-full.txt（完整内容，远程链接）
    llms_full_file = _generate_llms_full_txt(
        repo_dir, owner, repo_name, pages, successful, repo_info
    )

    # 生成 llms.txt（目录结构，本地相对链接）
    llms_file = _generate_llms_txt(
        repo_dir, owner, repo_name, pages, successful, repo_info
    )

    return {
        "success": True,
        "repo_dir": repo_dir,
        "total": len(pages),
        "successful": len(successful),
        "failed": len(failed),
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

    # 构建 slug -> content 的映射
    content_map = {r["page"]["slug"]: r["content"] for r in results if r.get("content")}

    # 按 section -> group 组织页面
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

    # 生成内容
    lines = []
    github_url = f"https://github.com/{owner}/{repo_name}"
    zread_url = f"https://zread.ai/{owner}/{repo_name}"

    lines.append(github_url)
    lines.append(zread_url)
    lines.append("")

    # 添加 GitHub 仓库信息
    if repo_info:
        repo_info_text = _format_repo_info_for_llms(repo_info)
        if repo_info_text:
            lines.append(repo_info_text)
            lines.append("")

    lines.append("")

    for section_name, groups in sections.items():
        lines.append(f"# {section_name}")
        lines.append("")

        # 默认组（没有 group 的页面）
        if "_default" in groups:
            for page_info in groups["_default"]:
                slug = page_info["slug"]
                topic = page_info["topic"]
                if slug in content_map:
                    lines.append(f"- [{slug}]({zread_url}/{slug})")
                    lines.append("")
                    lines.append(content_map[slug])
                    lines.append("")
                    lines.append("---")
                    lines.append("")

        # 有 group 的页面
        for group_name, group_pages in groups.items():
            if group_name == "_default":
                continue
            lines.append(f"## {group_name}")
            lines.append("")

            for page_info in group_pages:
                slug = page_info["slug"]
                topic = page_info["topic"]
                if slug in content_map:
                    lines.append(f"- [{slug}]({zread_url}/{slug})")
                    lines.append("")
                    lines.append(content_map[slug])
                    lines.append("")
                    lines.append("---")
                    lines.append("")

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
) -> Path:
    """生成 llms.txt 文件（包含目录结构，使用本地相对链接）"""
    llms_file = repo_dir / "llms.txt"

    # 构建 slug -> content 的映射
    content_map = {r["page"]["slug"]: r["content"] for r in results if r.get("content")}

    # 按 section -> group 组织页面
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

    # 生成内容
    lines = []
    github_url = f"https://github.com/{owner}/{repo_name}"
    zread_url = f"https://zread.ai/{owner}/{repo_name}"

    lines.append(github_url)
    lines.append(zread_url)
    lines.append("")

    # 添加 GitHub 仓库信息
    if repo_info:
        repo_info_text = _format_repo_info_for_llms(repo_info)
        if repo_info_text:
            lines.append(repo_info_text)
            lines.append("")

    lines.append("")

    for section_name, groups in sections.items():
        lines.append(f"# {section_name}")
        lines.append("")

        # 默认组（没有 group 的页面）
        if "_default" in groups:
            for page_info in groups["_default"]:
                slug = page_info["slug"]
                topic = page_info["topic"]
                if slug in content_map:
                    # 使用本地相对路径
                    lines.append(f"- [{slug}](./{slug}.md)")

        # 有 group 的页面
        for group_name, group_pages in groups.items():
            if group_name == "_default":
                continue
            lines.append(f"## {group_name}")
            lines.append("")

            for page_info in group_pages:
                slug = page_info["slug"]
                topic = page_info["topic"]
                if slug in content_map:
                    # 使用本地相对路径
                    lines.append(f"- [{slug}](./{slug}.md)")

            lines.append("")

        lines.append("")

    llms_file.write_text("\n".join(lines), encoding="utf-8")
    return llms_file


@cli_app.command(name="cp", help=tr("cli.commands.cp"))
def cmd_cp(
    ctx: typer.Context,
    repo: Annotated[Optional[str], typer.Argument(help=tr("cli.args.repo"))] = None,
    output_dir: Annotated[
        Optional[Path],
        typer.Argument(help=tr("cli.args.output_dir")),
    ] = None,
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
    """
    if not repo:
        typer.echo(ctx.get_help())
        typer.echo(f"\n❌ {tr('errors.missing_repo')}", err=True)
        raise typer.Exit(1)
    lang = _resolve_lang(lang)

    # 默认输出到当前目录
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
    pages = fetch_repo_outline(repo, lang=lang)
    if not pages:
        typer.echo(f"❌ {tr('errors.fetch_outline', lang)}", err=True)
        raise typer.Exit(1)

    try:
        # 使用 Rich 进度条
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
                    repo, output_dir, lang, concurrency, progress, task_id, pages
                )
            )

        if not result.get("success"):
            typer.echo(
                tr("errors.export_failed_with_reason", lang, error=result.get("error")),
                err=True,
            )
            raise typer.Exit(1)

        # 显示结果
        typer.echo(tr("messages.export_complete", lang))
        typer.echo(tr("messages.export_total", lang, count=result["total"]))
        typer.echo(tr("messages.export_success", lang, count=result["successful"]))
        typer.echo(tr("messages.export_failed", lang, count=result["failed"]))
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

    except Exception as e:
        typer.echo(tr("errors.export_failed_with_reason", lang, error=e), err=True)
        raise typer.Exit(1)


# CLI 子命令列表（用于判断运行模式）
CLI_COMMANDS = [
    "mcp",
    "outline",
    "page",
    "search",
    "trending",
    "discover",
    "find",
    "ask",
    "info",
    "export",
]

# MCP 相关库的名称列表（用于日志级别控制）
_MCP_LOGGER_NAMES = ["fastmcp", "mcp", "uvicorn", "starlette", "anyio"]


def _parse_address(transport: str, address: Optional[str]) -> tuple[str, int, str]:
    """解析地址参数

    支持格式:
        - host
        - host:port
        - :port
        - host:port/path
        - :port/path

    返回: (host, port, path)
    """
    if transport == "stdio" or not address:
        # stdio 模式或没有地址，使用默认值
        default_path = "/sse" if transport == "sse" else "/mcp"
        return "127.0.0.1", 8708, default_path

    # 分离路径部分
    if "/" in address:
        addr_part, path_part = address.split("/", 1)
        path = "/" + path_part
    else:
        addr_part = address
        path = "/sse" if transport == "sse" else "/mcp"

    # 解析 host:port
    if ":" in addr_part:
        host, port_str = addr_part.rsplit(":", 1)
        port = int(port_str) if port_str else 8708
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
    token: Optional[str] = None,
) -> None:
    """运行 MCP 服务器"""
    # 如果命令行提供了 token，设置为全局 token
    if token:
        set_default_token(token)

    # 确定是否有 token
    has_token = bool(_DEFAULT_TOKEN)

    mcp = _get_mcp(has_token)

    # 打印启动信息到 stderr
    if has_token:
        print(tr("mcp.token_enabled"), file=sys.stderr)
    else:
        print(tr("mcp.token_missing"), file=sys.stderr)

    if transport == "stdio":
        # stdio 模式：完全禁用所有日志输出，避免污染 stdout
        # 配置 root logger 输出到 stderr
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.ERROR)  # 只显示 ERROR 及以上级别

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.ERROR)
        root_logger.handlers = []
        root_logger.addHandler(handler)

        # 禁用所有相关库的日志
        for name in _MCP_LOGGER_NAMES:
            logging.getLogger(name).setLevel(logging.ERROR)
            logging.getLogger(name).propagate = False

        mcp.run(transport="stdio", show_banner=False)
    else:
        # HTTP/SSE 模式：显示传输模式信息
        if transport == "sse":
            print(
                tr("mcp.sse_started", url=f"http://{host}:{port}{path}"),
                file=sys.stderr,
            )
            mcp.run(transport="sse", host=host, port=port, path=path)
        elif transport == "http":
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


def main():
    """主入口函数"""
    cli_app()


if __name__ == "__main__":
    main()
