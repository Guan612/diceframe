"""System metadata routes."""

from __future__ import annotations

from aiohttp import web

from src.webui.routes._common import _get_api


async def api_update_check(request: web.Request) -> web.Response:
    raw = request.query.get("prerelease")
    override = raw.strip().lower() in {"1", "true", "yes"} if raw is not None else None
    return web.json_response(await _get_api(request).check_updates(override))


def register_system(app: web.Application) -> None:
    app.router.add_get("/api/system/update-check", api_update_check)
