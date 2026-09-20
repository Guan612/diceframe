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


async def api_lorebook_entries(request: web.Request) -> web.Response:
    return web.json_response(_get_api(request).list_lorebook_entries(request.match_info["book_id"]))


async def api_lorebook_entry_save(request: web.Request) -> web.Response:
    body = await request.json()
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "entry must be an object"}, status=400)
    return web.json_response(_get_api(request).save_lorebook_entry(request.match_info["book_id"], body))


async def api_lorebook_entry_update(request: web.Request) -> web.Response:
    body = await request.json()
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "entry must be an object"}, status=400)
    body["id"] = request.match_info["entry_id"]
    return web.json_response(_get_api(request).save_lorebook_entry(request.match_info["book_id"], body))


async def api_lorebook_entry_delete(request: web.Request) -> web.Response:
    return web.json_response(_get_api(request).delete_lorebook_entry(request.match_info["entry_id"]))


async def api_lorebook_export(request: web.Request) -> web.Response:
    return web.json_response(_get_api(request).export_lorebook(request.match_info["book_id"]))


async def api_lorebook_activation_preview(request: web.Request) -> web.Response:
    body = await request.json()
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "request must be an object"}, status=400)
    result = await _get_api(request).lorebook_activation_preview(body)
    return web.json_response(result, status=200 if result.get("ok") else 400)


def register_lorebooks(app: web.Application) -> None:
    app.router.add_get("/api/lorebooks", api_lorebooks)
    app.router.add_post("/api/lorebooks/import/preview", api_lorebook_import_preview)
    app.router.add_post("/api/lorebooks/import", api_lorebook_import_commit)
    app.router.add_get("/api/lorebooks/{book_id}/entries", api_lorebook_entries)
    app.router.add_post("/api/lorebooks/{book_id}/entries", api_lorebook_entry_save)
    app.router.add_put("/api/lorebooks/{book_id}/entries/{entry_id}", api_lorebook_entry_update)
    app.router.add_delete("/api/lorebooks/{book_id}/entries/{entry_id}", api_lorebook_entry_delete)
    app.router.add_get("/api/lorebooks/{book_id}/export", api_lorebook_export)
    app.router.add_post("/api/lorebooks/activation-preview", api_lorebook_activation_preview)
