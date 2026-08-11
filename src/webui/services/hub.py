"""DiceFrame Hub 偏好、详情和社区交互。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import aiohttp

from src.hub_client import HubUnavailable
from src.plugin_host.mirrors import parse_github_repository

if TYPE_CHECKING:
    from src.webui.api import WebAPI

# 作者 GitHub 仓库 Raw README 的大小上限（超出视为不可信，直接拒绝）。
_README_RAW_MAX_BYTES = 256 * 1024
# 只允许这些固定候选文件名；禁止请求任意模型提供的 URL（SSRF 防护）。
_README_CANDIDATES = ("README_CN.md", "README.md", "README_EN.md")


def _client(api: "WebAPI"):
    client = getattr(api, "_hub", None)
    if client is None:
        raise RuntimeError("DiceFrame Hub 当前未启用")
    return client


async def preferences(api: "WebAPI", language: str = "zh-CN") -> dict[str, Any]:
    state = getattr(api, "_config_state", {})
    client = getattr(api, "_hub", None)
    identity_exists = bool(client and client.identity_file.exists())
    documents = await api.current_legal_documents()
    return {
        "ok": True,
        "available": client is not None,
        "telemetry_enabled": bool(state.get("hub_telemetry_enabled", False)),
        "choice_made": bool(state.get("hub_telemetry_choice_made", False)),
        "identity_created": identity_exists,
        "legal_version": api.legal_bundle_version(documents),
        "legal_documents": api.legal_acceptance_payload(documents, language),
        "legal_accepted": api.legal_accepted(state, documents),
    }


async def update_preferences(
    api: "WebAPI",
    telemetry_enabled: bool,
    legal_acceptance: dict[str, Any] | None = None,
    language: str = "zh-CN",
) -> dict[str, Any]:
    state = api._config_state
    documents = await api.current_legal_documents()
    if telemetry_enabled and not (api.legal_accepted(state, documents) or legal_acceptance is not None):
        raise ValueError("启用匿名使用统计前必须先确认当前隐私政策")
    previous = {
        "hub_telemetry_enabled": state.get("hub_telemetry_enabled", False),
        "hub_telemetry_choice_made": state.get("hub_telemetry_choice_made", False),
        "legal_terms_accepted_updated_at": state.get("legal_terms_accepted_updated_at"),
        "legal_terms_accepted_version": state.get("legal_terms_accepted_version"),
        "legal_terms_accepted_hash": state.get("legal_terms_accepted_hash"),
        "legal_terms_accepted_language": state.get("legal_terms_accepted_language"),
        "legal_privacy_acknowledged_version": state.get("legal_privacy_acknowledged_version"),
        "legal_privacy_accepted_updated_at": state.get("legal_privacy_accepted_updated_at"),
        "legal_privacy_accepted_version": state.get("legal_privacy_accepted_version"),
        "legal_privacy_accepted_hash": state.get("legal_privacy_accepted_hash"),
        "legal_privacy_accepted_language": state.get("legal_privacy_accepted_language"),
        "legal_accepted_at": state.get("legal_accepted_at"),
    }
    if legal_acceptance is not None:
        api.record_legal_acceptance(
            state,
            acceptance=legal_acceptance,
            documents=documents,
            accepted_at=datetime.now(UTC).isoformat(),
        )
    state["hub_telemetry_enabled"] = bool(telemetry_enabled)
    state["hub_telemetry_choice_made"] = True
    try:
        api._save_config()
    except Exception:
        for key, value in previous.items():
            if value is None:
                state.pop(key, None)
            else:
                state[key] = value
        raise
    client = getattr(api, "_hub", None)
    if client is not None:
        await client.set_telemetry(bool(telemetry_enabled), choice_made=True)
    return await preferences(api, language)


async def delete_identity(api: "WebAPI") -> dict[str, Any]:
    client = _client(api)
    await client.delete_identity()
    return await preferences(api)


async def plugin_detail(api: "WebAPI", plugin_id: str) -> dict[str, Any]:
    return {"ok": True, **await _client(api).plugin_detail(plugin_id)}


async def plugin_readme(api: "WebAPI", plugin_id: str) -> dict[str, Any]:
    """插件详情 README 的三层兜底：Hub 已清洗 HTML → 本地磁盘缓存 → 作者 GitHub Raw。

    Hub 成功时把已清洗正文写入磁盘缓存；Hub 失败时先读缓存并标记 stale，
    无缓存时才按注册表中已经校验的 GitHub 仓库地址读取固定候选 README，
    禁止请求任意 URL。返回 `markdown`（Raw 原文）由前端用公共清洗器渲染。
    """
    client = _client(api)
    hub_error = ""
    try:
        payload = await client.plugin_readme(plugin_id)
        html = str(payload.get("html") or "")
        if html:
            meta = await _repository_meta(api, plugin_id)
            client.write_readme_cache(
                plugin_id,
                html=html,
                repository_url=meta["repository_url"],
                commit_sha=meta["commit_sha"],
            )
            return {
                "ok": True,
                "html": html,
                "source": {"hub": True, "github": False, "cached": False, "stale": False},
            }
        hub_error = "Hub 未提供 README"
    except (HubUnavailable, aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        hub_error = str(exc)

    cached = client.read_readme_cache(plugin_id)
    if cached is not None:
        return {
            "ok": True,
            "html": str(cached.get("html") or ""),
            "source": {
                "hub": True,
                "github": False,
                "cached": True,
                "stale": True,
                "error": hub_error,
            },
        }

    markdown = await _fetch_author_readme(api, plugin_id)
    if markdown:
        return {
            "ok": True,
            "html": "",
            "markdown": markdown,
            "source": {"hub": False, "github": True, "cached": False, "stale": False},
        }
    return {
        "ok": False,
        "html": "",
        "markdown": "",
        "error": hub_error or "README 暂不可用",
        "source": {"hub": False, "github": False, "cached": False, "stale": False, "error": hub_error},
    }


async def _repository_meta(api: "WebAPI", plugin_id: str) -> dict[str, str]:
    """从已校验的商店索引取插件仓库地址与最新提交版本。"""
    plugins = getattr(api, "_plugins", None)
    marketplace = getattr(plugins, "marketplace", None)
    if marketplace is None:
        return {"repository_url": "", "commit_sha": ""}
    try:
        listing = await marketplace.list_plugins()
    except Exception:
        return {"repository_url": "", "commit_sha": ""}
    items = listing.get("plugins") if isinstance(listing, dict) else None
    if not isinstance(items, list):
        return {"repository_url": "", "commit_sha": ""}
    item = next((entry for entry in items if isinstance(entry, dict) and entry.get("id") == plugin_id), None)
    if item is None:
        return {"repository_url": "", "commit_sha": ""}
    latest = item.get("latest") if isinstance(item.get("latest"), dict) else {}
    commit_sha = str(latest.get("commit_sha") or item.get("commit_sha") or "").strip().lower()
    return {
        "repository_url": str(item.get("repository_url") or "").strip(),
        "commit_sha": commit_sha,
    }


async def _fetch_author_readme(api: "WebAPI", plugin_id: str) -> str:
    """只在注册表仓库地址基础上读取固定候选 README；非 GitHub 或私网地址直接跳过。"""
    plugins = getattr(api, "_plugins", None)
    mirrors = getattr(plugins, "mirrors", None)
    if mirrors is None:
        return ""
    meta = await _repository_meta(api, plugin_id)
    repository_url = meta["repository_url"]
    if not repository_url:
        return ""
    try:
        owner, repo = parse_github_repository(repository_url)
    except ValueError:
        return ""
    commit_sha = meta["commit_sha"]
    ref = commit_sha if len(commit_sha) == 40 else "main"
    for candidate in _README_CANDIDATES:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{candidate}"
        try:
            result = await mirrors.fetch_github_url(url, max_bytes=_README_RAW_MAX_BYTES)
        except (ValueError, aiohttp.ClientError, asyncio.TimeoutError):
            continue
        if result.ok and isinstance(result.data, str) and result.data.strip():
            return result.data
    return ""


async def plugin_ratings(api: "WebAPI", plugin_id: str) -> dict[str, Any]:
    return {"ok": True, **await _client(api).plugin_ratings(plugin_id)}


async def set_plugin_like(api: "WebAPI", plugin_id: str, liked: bool) -> dict[str, Any]:
    return {"ok": True, **await _client(api).set_like(plugin_id, liked)}


async def set_plugin_rating(
    api: "WebAPI", plugin_id: str, stars: int | None, tags: list[str] | None = None
) -> dict[str, Any]:
    return {"ok": True, **await _client(api).set_rating(plugin_id, stars, tags)}
