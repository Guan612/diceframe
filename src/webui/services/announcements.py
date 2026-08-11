"""开发者公告拉取：复用公共内容服务的网络访问、磁盘缓存、单飞与失败退避。

公告不再维护独立的网络下载器；主机限制、大小限制、单飞、失败退避和磁盘缓存
全部由 `content.py` 经 `WebAPI.fetch_public_content_text()` 提供。本模块只保留
中英文文件选择、公告散列、短命中缓存和“缓存内容”标记。
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.webui.api import WebAPI

logger = logging.getLogger("trpg")

ANNOUNCEMENT_DIR = "content/announcements"
_SUCCESS_TTL = 600
_STALE_TTL = 86_400

_CACHE: dict[str, dict[str, Any]] = {}


def _file_for_language(language: str) -> str:
    return "zh.md" if (language or "").lower().startswith("zh") else "en.md"


def _payload(cached: dict[str, Any], *, stale: bool = False) -> dict[str, Any]:
    return {"content": cached["content"], "hash": cached["hash"], "fetched": True, "stale": stale}


def _stale_payload(key: str, now: float) -> dict[str, Any] | None:
    cached = _CACHE.get(key)
    if cached and now - float(cached["fetched_at"]) <= _STALE_TTL:
        return _payload(cached, stale=True)
    return None


async def fetch_official_announcement(api: "WebAPI", language: str) -> dict[str, Any]:
    """返回公告正文与散列；成功在线获取后 content.py 会更新磁盘缓存。

    失败时返回陈旧缓存并标记 stale；从未成功且离线时返回空公告，不弹错误死循环。
    """
    key = _file_for_language(language)
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and now - float(cached["fetched_at"]) < _SUCCESS_TTL:
        return _payload(cached)

    path = f"{ANNOUNCEMENT_DIR}/{key}"
    try:
        text = await api.fetch_public_content_text(path)
    except Exception:
        logger.exception("公告内容拉取异常")
        text = ""

    now = time.monotonic()
    if text:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        _CACHE[key] = {"content": text, "hash": digest, "fetched_at": now}
        return _payload(_CACHE[key], stale=_is_cached_served(api, path, text))

    return _stale_payload(key, now) or _empty()


def _is_cached_served(api: "WebAPI", path: str, text: str) -> bool:
    """判断返回正文是否来自 content.py 的磁盘缓存（例如重启后断网场景）。"""
    if not text:
        return False
    age = api.public_content_disk_age(path)
    if age is None:
        return False
    return age > _SUCCESS_TTL


def _empty() -> dict[str, Any]:
    return {"content": "", "hash": "", "fetched": False, "stale": False}
