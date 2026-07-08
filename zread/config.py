# -*- coding: utf-8 -*-
"""全局配置：路径、常量、语言 / i18n、GitHub 端点与 token。"""

import locale
import os
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import i18n

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

APP_NAME = "zread"

# 版本号：从包元数据获取，本地开发时从 _version.py 获取
try:
    from importlib.metadata import PackageNotFoundError, version

    APP_VERSION = version("zread")
except PackageNotFoundError:
    try:
        from zread_version import __version__ as APP_VERSION
    except (ImportError, ModuleNotFoundError):
        APP_VERSION = "0.0.0"

USER_AGENT = (
    f"Mozilla/5.0 (compatible; {APP_NAME}/{APP_VERSION};"
    " +https://github.com/valeriikot/zread)"
)
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}
LOCALES_DIR = Path(__file__).resolve().parent / "locales"

# 检测是否在交互式终端运行（非交互式自动降级为 plain 模式）
_IS_INTERACTIVE = sys.stdin.isatty() and sys.stdout.isatty()

# 配置文件中允许的键（zread config set 也以此为准）
CONFIG_KEYS = ("lang", "github_token", "github_api_url", "github_raw_url")


def config_file_location() -> Path:
    """配置文件应有的路径（无论是否存在）。

    - macOS: ~/.config/zread/zread.toml
    - Linux: $XDG_CONFIG_HOME/zread/zread.toml（默认 ~/.config/zread/zread.toml）
    - Windows: %APPDATA%/zread/zread.toml
    """
    home = Path.home()
    if sys.platform == "win32":
        return (
            Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
            / "zread"
            / "zread.toml"
        )
    if sys.platform != "darwin":
        xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
        if xdg_config:
            return Path(xdg_config) / "zread" / "zread.toml"
    return home / ".config" / "zread" / "zread.toml"


def existing_config_path() -> Optional[Path]:
    """配置文件路径（仅当文件存在时）。"""
    path = config_file_location()
    return path if path.exists() else None


def config_from_file() -> Dict[str, Any]:
    """读取配置文件的 [zread] 表（每次读取最新内容，文件不存在返回空表）。"""
    path = existing_config_path()
    if not path:
        return {}
    try:
        with open(path, "rb") as f:
            config = tomllib.load(f)
        return config.get("zread", {}) if isinstance(config, dict) else {}
    except Exception:
        return {}


def github_token() -> str:
    """GitHub API Token（可选）。优先级：ZREAD_GITHUB_TOKEN > GITHUB_TOKEN > 配置文件。"""
    return (
        os.environ.get("ZREAD_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or str(config_from_file().get("github_token", "") or "")
    )


def github_api_url() -> str:
    """GitHub REST API 地址（GitHub Enterprise 可通过环境变量 / 配置覆盖）。"""
    return (
        os.environ.get("ZREAD_GITHUB_API_URL")
        or str(config_from_file().get("github_api_url", "") or "")
        or "https://api.github.com"
    ).rstrip("/")


def github_raw_url() -> str:
    """raw 文件下载地址（GitHub Enterprise 可通过环境变量 / 配置覆盖）。"""
    return (
        os.environ.get("ZREAD_GITHUB_RAW_URL")
        or str(config_from_file().get("github_raw_url", "") or "")
        or "https://raw.githubusercontent.com"
    ).rstrip("/")


def cache_dir() -> Path:
    """磁盘缓存目录（$XDG_CACHE_HOME/zread，Windows 为 %LOCALAPPDATA%/zread）。"""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", "") or (Path.home() / ".cache"))
    return base / "zread"


def cache_disabled() -> bool:
    """ZREAD_NO_CACHE=1 时禁用磁盘缓存。"""
    return os.environ.get("ZREAD_NO_CACHE", "") not in ("", "0", "false")


# ==========================================
# 语言 / i18n
# ==========================================


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

    config_lang = config_from_file().get("lang", "")
    if config_lang in ("zh", "en"):
        return config_lang

    return _detect_lang_with_pylocale()


def _configure_i18n(lang: str) -> None:
    """初始化 i18n 配置。"""
    locale_path = str(LOCALES_DIR)
    if locale_path not in i18n.load_path:
        i18n.load_path.append(locale_path)
    i18n.set("file_format", "yml")
    i18n.set("filename_format", "{namespace}.{locale}.{format}")
    # 缺失键回退到英文（面向国际用户；此前回退中文会把中文串漏给英文用户）
    i18n.set("fallback", "en")
    i18n.set("locale", lang)


# 全局默认语言，可通过 set_default_lang() 修改
_DEFAULT_LANG: str = _get_default_lang()
_configure_i18n(_DEFAULT_LANG)


def default_lang() -> str:
    """当前全局默认语言。"""
    return _DEFAULT_LANG


def set_default_lang(lang: str) -> None:
    """设置全局默认语言"""
    global _DEFAULT_LANG
    if lang in ("zh", "en"):
        _DEFAULT_LANG = lang
        i18n.set("locale", lang)


def _resolve_lang(lang: Optional[str]) -> str:
    """解析本次调用使用的语言，未显式指定时回退到全局默认语言。"""
    return lang if lang in ("zh", "en") else _DEFAULT_LANG


def tr(key: str, lang: Optional[str] = None, **kwargs: Any) -> str:
    """读取翻译文本。"""
    use_locale = lang if lang in ("zh", "en") else _DEFAULT_LANG
    return i18n.t(f"messages.{key}", locale=use_locale, default=key, **kwargs)


def _unknown_error(lang: Optional[str] = None) -> str:
    return tr("messages.unknown_error", lang)
