"""Room password entry: verify a share-link player's password, issue a room token.

The room password and room tokens are owned by ``room_access``; this service
only adds the transport-side policy (token lifetime, running the slow hash
check off the event loop).
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from src.engine.modules import room_access

logger = logging.getLogger("trpg")

ROOM_TOKEN_TTL_ENV = "TRPG_ROOM_TOKEN_TTL_DAYS"
MAX_ROOM_TOKEN_TTL_DAYS = 365


def room_token_ttl_seconds(environ: Mapping[str, str] | None = None) -> int:
    """Room token lifetime: ``TRPG_ROOM_TOKEN_TTL_DAYS`` (default 30, max 365)."""
    raw = str((os.environ if environ is None else environ).get(ROOM_TOKEN_TTL_ENV, "") or "").strip()
    if not raw:
        return room_access.DEFAULT_ROOM_TOKEN_TTL_SECONDS
    try:
        days = float(raw)
    except ValueError:
        days = math.nan
    if not math.isfinite(days) or days <= 0:
        logger.warning("%s=%r 无效，使用默认房间令牌有效期", ROOM_TOKEN_TTL_ENV, raw)
        return room_access.DEFAULT_ROOM_TOKEN_TTL_SECONDS
    return max(60, int(min(days, MAX_ROOM_TOKEN_TTL_DAYS) * 86400))


async def verify_and_issue_room_token(
    instance: Any,
    password: str,
    save: Callable[[Any], Awaitable[None]],
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], int]:
    """Return ``(response body, HTTP status)`` for a room password attempt."""
    if not room_access.has_room_password(instance):
        return {"ok": False, "error": "该游戏未设置房间密码"}, 400
    # PBKDF2 is deliberately slow; keep it off the event loop.
    matched = await asyncio.to_thread(room_access.verify_room_password, instance, password)
    if not matched:
        return {"ok": False, "error": "房间密码错误"}, 403
    token, expires_at = room_access.issue_room_token(
        instance, ttl_seconds=room_token_ttl_seconds(environ),
    )
    await save(instance)
    return {"ok": True, "room_token": token, "expires_at": expires_at}, 200
