"""Canonical Lorebook v2 import routes; legacy world routes remain façades."""
from __future__ import annotations

from aiohttp import web

from src.webui.routes._common import _get_api


async def api_lorebooks(request: web.Request) -> web.Response:
    return web.json_response(_get_api(request).list_lorebooks(request.query.get("world_id", "")))


async def api_lorebook_import_preview(request: web.Request) -> web.Response:
    body = await request.json()
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "Lorebook payload must be an object"}, status=400)
    return web.json_response(_get_api(request).preview_lorebook_import(body))


async def api_lorebook_import_commit(request: web.Request) -> web.Response:
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("payload"), dict):
        return web.json_response({"ok": False, "error": "payload must be an object"}, status=400)
    result = _get_api(request).commit_lorebook_import(
        body["payload"], body.get("binding"), body.get("book_id"),
    )
    return web.json_response(result, status=200 if result.get("ok") else 400)


def register_lorebooks(app: web.Application) -> None:
    app.router.add_get("/api/lorebooks", api_lorebooks)
    app.router.add_post("/api/lorebooks/import/preview", api_lorebook_import_preview)
    app.router.add_post("/api/lorebooks/import", api_lorebook_import_commit)
