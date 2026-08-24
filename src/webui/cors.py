"""Optional CORS boundary for independently hosted WebUI builds."""

from __future__ import annotations

from urllib.parse import urlsplit

from aiohttp import web


def parse_cors_origins(value: str | None) -> frozenset[str]:
    origins: set[str] = set()
    for raw in str(value or "").replace(";", ",").split(","):
        candidate = raw.strip().rstrip("/")
        if not candidate:
            continue
        parsed = urlsplit(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc and not parsed.path and not parsed.query and not parsed.fragment:
            origins.add(f"{parsed.scheme}://{parsed.netloc}")
    return frozenset(origins)


def is_allowed_cors_origin(request: web.Request) -> bool:
    origin = str(request.headers.get("Origin") or "").strip().rstrip("/")
    return bool(origin and origin in request.app.get("cors_origins", frozenset()))


@web.middleware
async def cors_middleware(request: web.Request, handler) -> web.StreamResponse:
    origin = str(request.headers.get("Origin") or "").strip().rstrip("/")
    allowed = bool(origin and origin in request.app.get("cors_origins", frozenset()))
    if request.method == "OPTIONS" and origin:
        if not allowed:
            return web.json_response({"ok": False, "error": "CORS origin is not allowed"}, status=403)
        response: web.StreamResponse = web.Response(status=204)
    else:
        response = await handler(request)
    if allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = (
            "Authorization, Content-Type, X-TRPG-Confirm, X-Bot-Token, X-Bot-Actor"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Max-Age"] = "600"
        response.headers.add("Vary", "Origin")
    return response
