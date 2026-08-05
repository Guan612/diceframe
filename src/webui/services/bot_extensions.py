"""Bot Bridge extension protocol backed by managed process plugins."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.webui.api import WebAPI

from src.bots.bridge_core.card_renderer import BRAND_FOOTER, render_card_png

logger = logging.getLogger("trpg")

BRIDGE_EXTENSION_PROTOCOL_VERSION = 1
BRIDGE_EXTENSION_STAGES = ("before_message", "after_result", "render")
MAX_BRIDGE_PAYLOAD_BYTES = 192 * 1024
_BRIDGE_CARD_NAME_RE = re.compile(r"^card_[0-9a-f]{8,64}\.png$")


def capabilities(api: "WebAPI") -> dict[str, Any]:
    extensions = api._plugins.list_bridge_extensions() if api._plugins else []
    return {
        "protocol_version": BRIDGE_EXTENSION_PROTOCOL_VERSION,
        "stages": list(BRIDGE_EXTENSION_STAGES),
        "extensions": len(extensions),
    }


async def apply(
    api: "WebAPI",
    stage: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    stage = str(stage or "").strip()
    if stage not in BRIDGE_EXTENSION_STAGES:
        return {"ok": False, "error": f"不支持的 Bot Bridge 扩展阶段：{stage}"}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "payload 必须是对象"}
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        return {"ok": False, "error": "payload 不是有效 JSON"}
    if len(encoded) > MAX_BRIDGE_PAYLOAD_BYTES:
        return {"ok": False, "error": "Bot Bridge 扩展 payload 不能超过 192 KB"}
    if not api._plugins:
        return {
            "ok": True,
            "handled": False,
            "payload": payload,
            "outputs": [],
            "applied": [],
        }
    result = await api._plugins.apply_bridge_extensions(stage, payload)
    outputs = result.get("outputs") if isinstance(result.get("outputs"), list) else []
    if outputs:
        result["outputs"] = _materialize_cards(api, outputs)
    return {"ok": True, **result}


def bridge_card_dir(api: "WebAPI") -> Path:
    """卡片渲染输出目录（data/bot/cards），与清缓存按钮一致。"""
    data_dir = Path(api._plugins.data_dir).resolve()
    return (data_dir / "bot" / "cards").resolve()


def _materialize_cards(api: "WebAPI", outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把服务端收到的 card 输出渲染成 PNG，转成可下载的 image 输出。

    渲染失败（如 PIL 缺失）时保留原 card 输出并记 warning，让渠道走自己的降级路径。
    """
    materialized: list[dict[str, Any]] = []
    for output in outputs:
        if not isinstance(output, dict) or output.get("type") != "card":
            materialized.append(output)
            continue
        title = str(output.get("title") or "").strip()
        subtitle = str(output.get("subtitle") or "").strip()
        lines = output.get("lines") if isinstance(output.get("lines"), list) else []
        try:
            png = render_card_png(
                bridge_card_dir(api),
                title=title,
                subtitle=subtitle,
                lines=lines,
                footer=BRAND_FOOTER,
            )
        except Exception as exc:
            logger.warning("Bot Bridge 卡片渲染失败，保留原 card 输出: %s", exc)
            materialized.append(output)
            continue
        fallback = str(output.get("fallback_text") or "").strip()
        if not fallback:
            fallback = "\n".join([title, subtitle, *[str(x) for x in lines]]).strip()
        materialized.append({
            "type": "image",
            "asset_url": f"/api/bot/bridge-cards/{png.name}",
            "alt": title,
            "fallback_text": fallback,
        })
    return materialized


def bridge_card_path(api: "WebAPI", name: str) -> Path:
    """解析卡片渲染输出文件路径；非法或不存在时抛异常。"""
    if not _BRIDGE_CARD_NAME_RE.match(str(name or "")):
        raise ValueError("卡片文件名非法")
    root = bridge_card_dir(api)
    target = (root / str(name)).resolve()
    if root not in target.parents:
        raise ValueError("卡片文件路径非法")
    if not target.is_file():
        raise KeyError("卡片文件不存在")
    return target


def asset_path(api: "WebAPI", plugin_id: str, relative_path: str) -> Path:
    if not api._plugins:
        raise KeyError("插件宿主未启用")
    return api._plugins.bridge_asset_path(plugin_id, relative_path)
