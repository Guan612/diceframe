"""Read-only adventure catalogue routes."""

from __future__ import annotations

from aiohttp import web


def _get_api(request: web.Request):
    return request.app["api"]


async def api_adventures(request: web.Request) -> web.Response:
    result = _get_api(request).list_adventures(
        rule_id=request.query.get("rule_id", ""),
        world_id=request.query.get("world_id", ""),
        language=request.query.get("language", ""),
    )
    return web.json_response(result)


def register_adventures(app: web.Application) -> None:
    app.router.add_get("/api/adventures", api_adventures)
