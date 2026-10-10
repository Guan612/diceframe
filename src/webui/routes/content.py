"""Content sync routes: ``/api/content/import/preview|commit`` and ``/api/content/export``.

Thin transport layer. It owns what only the request knows:

- owner-only access (master password or paired-device token);
- the paired-device identity rule: a request authenticated by a paired
  device may declare only that device's install id (bound at pairing, or on
  first use for devices paired earlier); the master-password owner may
  declare any device;
- size limits, checked before any parsing or planning work.

Everything else is delegated to the content sync use cases.
"""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from src.engine.world.contracts import CANONICAL_ID_PATTERN
from src.webui.access_control import PAIRED_DEVICE_ID_KEY
from src.webui.device_tokens import DEVICE_TOKENS_KEY
from src.webui.routes._common import _get_api
from src.webui.routes.auth import ACCESS_PASSWORD_CONFIGURED_KEY
from src.webui.server_identity import server_instance_id

MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_ITEMS = 50
MAX_ENTRIES_PER_BOOK = 2000
MAX_ENTRY_BYTES = 32 * 1024

BODY_TOO_LARGE = "BODY_TOO_LARGE"
TOO_MANY_ITEMS = "TOO_MANY_ITEMS"
TOO_MANY_ENTRIES = "TOO_MANY_ENTRIES"
ENTRY_TOO_LARGE = "ENTRY_TOO_LARGE"
OWNER_REQUIRED = "OWNER_REQUIRED"
SOURCE_NOT_THIS_DEVICE = "SOURCE_NOT_THIS_DEVICE"

_CONFLICT_CODES = frozenset({"PLAN_STALE", "CARD_IDENTITY_CONFLICT", "LOREBOOK_IDENTITY_CONFLICT"})


def _error(status: int, code: str, message: str, **extra: Any) -> web.Response:
    return web.json_response({"ok": False, "error_code": code, "error": message, **extra}, status=status)


def _owner_denied(request: web.Request) -> web.Response | None:
    """The library is the owner's: share, bot and plugin callers are refused.

    Without an access password there is no authentication boundary at all,
    exactly as for the rest of the owner API.
    """

    if request.get("bot_authenticated", False):
        return _error(403, OWNER_REQUIRED, "content sync is owner-only")
    if request.get(ACCESS_PASSWORD_CONFIGURED_KEY, True) and not request.get("owner_authenticated", False):
        return _error(403, OWNER_REQUIRED, "content sync is owner-only")
    return None


async def _read_json(request: web.Request) -> tuple[Any, web.Response | None]:
    if request.content_length is not None and request.content_length > MAX_BODY_BYTES:
        return None, _error(413, BODY_TOO_LARGE, f"request body exceeds {MAX_BODY_BYTES} bytes")
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await request.content.read(64 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            return None, _error(413, BODY_TOO_LARGE, f"request body exceeds {MAX_BODY_BYTES} bytes")
        chunks.append(chunk)
    try:
        body = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, _error(400, "REQUEST_INVALID", "request must be JSON")
    if not isinstance(body, dict):
        return None, _error(400, "REQUEST_INVALID", "request must be an object")
    return body, None


def _entry_lists(document: Any) -> list[Any]:
    """Every lorebook entry collection in a portable document."""

    if not isinstance(document, dict):
        return []
    data = document.get("data")
    if not isinstance(data, dict):
        return []
    found = []
    for book in (data.get("lorebook"), data.get("character_book")):
        if isinstance(book, dict) and isinstance(book.get("entries"), (list, dict)):
            entries = book["entries"]
            found.append(list(entries.values()) if isinstance(entries, dict) else entries)
    return found


def _limit_denied(body: dict[str, Any]) -> web.Response | None:
    items = body.get("items")
    if isinstance(items, list) and len(items) > MAX_ITEMS:
        return _error(413, TOO_MANY_ITEMS, f"at most {MAX_ITEMS} items per request")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        for entries in _entry_lists(item.get("document")):
            if len(entries) > MAX_ENTRIES_PER_BOOK:
                return _error(
                    413, TOO_MANY_ENTRIES, f"at most {MAX_ENTRIES_PER_BOOK} entries per book",
                    client_ref=str(item.get("client_ref") or ""),
                )
            for entry in entries:
                size = len(json.dumps(entry, ensure_ascii=False).encode("utf-8"))
                if size > MAX_ENTRY_BYTES:
                    return _error(
                        413, ENTRY_TOO_LARGE, f"an entry exceeds {MAX_ENTRY_BYTES} bytes",
                        client_ref=str(item.get("client_ref") or ""),
                    )
    return None


def _device_denied(request: web.Request, body: dict[str, Any]) -> web.Response | None:
    """A paired device may declare only its own install id."""

    device_id = str(request.get(PAIRED_DEVICE_ID_KEY, "") or "")
    if not device_id:
        return None  # master-password owner (or no password): any device
    source = body.get("source")
    declared = source.get("id") if isinstance(source, dict) else None
    if not isinstance(declared, str) or not CANONICAL_ID_PATTERN.fullmatch(declared):
        return None  # malformed source: the use case rejects it
    devices = request.app.get(DEVICE_TOKENS_KEY)
    bound = devices.bind_install_id(device_id, declared) if devices is not None else ""
    if bound != declared:
        return _error(403, SOURCE_NOT_THIS_DEVICE, "this device may only push its own install id")
    return None


def _respond(result: dict[str, Any]) -> web.Response:
    if result.get("ok"):
        return web.json_response(result)
    code = str(result.get("error_code") or "")
    failed_items = [row for row in result.get("items") or [] if row.get("status") == "error"]
    if code in _CONFLICT_CODES or any(row.get("error_code") in _CONFLICT_CODES for row in failed_items):
        return web.json_response(result, status=409)
    if code == "NOT_FOUND":
        return web.json_response(result, status=404)
    return web.json_response(result, status=400)


async def _import_request(request: web.Request) -> tuple[dict[str, Any] | None, web.Response | None]:
    if denied := _owner_denied(request):
        return None, denied
    body, denied = await _read_json(request)
    if denied is not None:
        return None, denied
    if denied := _limit_denied(body):
        return None, denied
    if denied := _device_denied(request, body):
        return None, denied
    return body, None


async def api_content_import_preview(request: web.Request) -> web.Response:
    body, denied = await _import_request(request)
    if denied is not None or body is None:
        return denied or _error(400, "REQUEST_INVALID", "request must be an object")
    return _respond(_get_api(request).preview_content_import(
        body, pushed_by_device=str(request.get(PAIRED_DEVICE_ID_KEY, "") or ""),
    ))


async def api_content_import_commit(request: web.Request) -> web.Response:
    body, denied = await _import_request(request)
    if denied is not None or body is None:
        return denied or _error(400, "REQUEST_INVALID", "request must be an object")
    return _respond(_get_api(request).commit_content_import(
        body, pushed_by_device=str(request.get(PAIRED_DEVICE_ID_KEY, "") or ""),
    ))


async def api_content_export(request: web.Request) -> web.Response:
    if denied := _owner_denied(request):
        return denied
    body, denied = await _read_json(request)
    if denied is not None or body is None:
        return denied or _error(400, "REQUEST_INVALID", "request must be an object")
    if denied := _limit_denied(body):
        return denied
    return _respond(_get_api(request).export_content(
        body, server_instance_id=server_instance_id(request.app) or "",
    ))


def register_content(app: web.Application) -> None:
    app.router.add_post("/api/content/import/preview", api_content_import_preview)
    app.router.add_post("/api/content/import/commit", api_content_import_commit)
    app.router.add_post("/api/content/export", api_content_export)
