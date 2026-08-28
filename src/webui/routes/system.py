"""System metadata routes."""

from __future__ import annotations

from datetime import datetime, timezone

from aiohttp import web

from src.webui.routes._common import _get_api, _require_confirmed_request


async def api_update_check(request: web.Request) -> web.Response:
    raw = request.query.get("prerelease")
    override = raw.strip().lower() in {"1", "true", "yes"} if raw is not None else None
    return web.json_response(await _get_api(request).check_updates(override))


async def api_runtime_log_status(request: web.Request) -> web.Response:
    return web.json_response(_get_api(request).runtime_log_status())


async def api_clear_runtime_logs(request: web.Request) -> web.Response:
    if denied := _require_confirmed_request(request):
        return denied
    return web.json_response(_get_api(request).clear_runtime_logs())


async def api_export_runtime_logs(request: web.Request) -> web.Response:
    try:
        payload, _file_count = _get_api(request).export_runtime_logs()
    except FileNotFoundError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=404)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"DiceFrame-runtime-logs-{timestamp}.zip"
    return web.Response(
        body=payload,
        content_type="application/zip",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


def register_system(app: web.Application) -> None:
    app.router.add_get("/api/system/update-check", api_update_check)
    app.router.add_get("/api/system/runtime-logs", api_runtime_log_status)
    app.router.add_get("/api/system/runtime-logs/export", api_export_runtime_logs)
    app.router.add_post("/api/system/runtime-logs/clear", api_clear_runtime_logs)
