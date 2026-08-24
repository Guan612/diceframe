"""Optional CORS boundary for independently hosted WebUI builds."""

from __future__ import annotations

from urllib.parse import urlsplit

from aiohttp import web


def _origin_from_candidate(candidate: str) -> str | None:
    parsed = urlsplit(candidate)
    if parsed.scheme in {"http", "https"} and parsed.netloc and not parsed.path and not parsed.query and not parsed.fragment:
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


def _origin_candidates(value: str | None) -> list[str]:
    text = str(value or "").replace(";", ",").replace("\r", "\n").replace("\n", ",")
    return [raw.strip().rstrip("/") for raw in text.split(",") if raw.strip()]


def parse_cors_origins(value: str | None) -> frozenset[str]:
    origins: set[str] = set()
    for candidate in _origin_candidates(value):
        origin = _origin_from_candidate(candidate)
        if origin:
            origins.add(origin)
    return frozenset(origins)


def invalid_cors_origins(value: str | None) -> tuple[str, ...]:
    invalid: list[str] = []
    for candidate in _origin_candidates(value):
        if not _origin_from_candidate(candidate):
            invalid.append(candidate)
    return tuple(invalid)


def normalize_cors_origins(value: str | None) -> str:
    return ", ".join(sorted(parse_cors_origins(value)))


def is_allowed_cors_origin(request: web.Request) -> bool:
    origin = str(request.headers.get("Origin") or "").strip().rstrip("/")
    return bool(origin and origin in request.app.get("cors_origins", frozenset()))


def apply_cors_headers(request: web.Request, response: web.StreamResponse) -> None:
    origin = str(request.headers.get("Origin") or "").strip().rstrip("/")
    if not origin or origin not in request.app.get("cors_origins", frozenset()):
        return
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = (
        "Authorization, Content-Type, X-TRPG-Confirm, X-Bot-Token, X-Bot-Actor"
    )
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Max-Age"] = "600"
    response.headers.add("Vary", "Origin")


async def cors_response_prepare(request: web.Request, response: web.StreamResponse) -> None:
    apply_cors_headers(request, response)


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
        apply_cors_headers(request, response)
    return response
