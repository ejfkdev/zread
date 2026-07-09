# -*- coding: utf-8 -*-
"""缓存层：进程内 TTL-LRU 缓存 + 磁盘 ETag 缓存（条件请求，304 不消耗 API 配额）。"""

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from zread.config import cache_dir, cache_disabled

# get() 的未命中哨兵（缓存值本身可能是 None，表示"已知不存在"）
MISSING = object()


class TTLCache:
    """线程安全的 TTL-LRU 缓存，防止长驻 MCP 服务内存无限增长 / 数据永不过期。"""

    def __init__(self, maxsize: int = 256, ttl: float = 900.0):
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: "OrderedDict[Any, Tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Any, default: Any = MISSING) -> Any:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return default
            expires_at, value = item
            if time.monotonic() > expires_at:
                del self._data[key]
                return default
            self._data.move_to_end(key)
            return value

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + self.ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


class HTTPDiskCache:
    """按 URL 保存 ETag + 响应体；命中时发送 If-None-Match，304 直接复用本地内容。

    GitHub 对返回 304 的条件请求不计入速率限制，这让匿名配额（60 次/小时）
    大幅提效。所有写入都是尽力而为：磁盘异常绝不影响请求本身。
    """

    def __init__(self, root: Optional[Path] = None):
        self.root = root if root is not None else cache_dir() / "http"

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
        return self.root / digest[:2] / f"{digest}.json"

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """返回 {"etag": str, "body": str} 或 None。"""
        try:
            path = self._path(key)
            with open(path, encoding="utf-8") as f:
                entry = json.load(f)
            if not isinstance(entry, dict) or entry.get("key") != key:
                return None
            if not entry.get("etag"):
                return None
            return entry
        except Exception:
            return None

    # 每个两位十六进制分片目录允许的最大条目数（约束整体磁盘占用：
    # 256 个分片 × 64 条 ≈ 1.6 万条上限，超出时按 mtime 淘汰最旧的）
    _SHARD_LIMIT = 64

    def store(self, key: str, etag: str, body: str) -> None:
        try:
            path = self._path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(
                json.dumps(
                    {"key": key, "etag": etag, "body": body, "saved_at": time.time()},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            os.replace(tmp, path)
            self._prune_shard(path.parent)
        except Exception:
            pass

    def _prune_shard(self, shard_dir: Path) -> None:
        """分片目录超限时删除最旧的条目，保证磁盘缓存不会无限增长。"""
        try:
            entries = [p for p in shard_dir.iterdir() if p.suffix == ".json"]
            if len(entries) <= self._SHARD_LIMIT:
                return
            entries.sort(key=lambda p: p.stat().st_mtime)
            for stale in entries[: len(entries) - self._SHARD_LIMIT]:
                stale.unlink(missing_ok=True)
        except Exception:
            pass


def http_cache() -> Optional[HTTPDiskCache]:
    """磁盘缓存实例；ZREAD_NO_CACHE=1 时返回 None。"""
    if cache_disabled():
        return None
    return HTTPDiskCache()
