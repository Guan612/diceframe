"""Content sync use cases behind ``/api/content/*``.

Parses the request shape and delegates to the kind-neutral orchestrator in
``src.content_modules.sync`` with the importers/exporters the facade injects
(one per portable schema). Authentication, the paired-device identity rule
and size limits are transport concerns and live in the route.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from src.content_modules import sync
from src.content_modules.plan import declared_source_ref

IMPORT_SOURCE_INVALID = "IMPORT_SOURCE_INVALID"


@dataclass(frozen=True)
class ContentSyncDependencies:
    #: Importers keyed by portable schema, built for one request (they may
    #: carry request context such as the pushing device).
    importers: Callable[[str], Mapping[str, sync.KindImporter]]
    exporters: Callable[[], Mapping[str, sync.KindExporter]]


def _failure(exc: sync.SyncItemError) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "error_code": exc.code, "error": str(exc)}
    if exc.client_ref:
        result["client_ref"] = exc.client_ref
    return result


def parse_import_request(body: dict[str, Any]) -> tuple[sync.SyncSource, list[sync.SyncItem]]:
    try:
        kind, source_id = declared_source_ref(body.get("source"))
    except ValueError as exc:
        raise sync.SyncItemError(IMPORT_SOURCE_INVALID, str(exc)) from exc
    raw_items = body.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise sync.SyncItemError(sync.REQUEST_INVALID, "items must be a non-empty list")
    items: list[sync.SyncItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise sync.SyncItemError(sync.REQUEST_INVALID, "every item must be an object")
        hint = raw.get("canonical_hint")
        if hint is not None and not isinstance(hint, str):
            raise sync.SyncItemError(sync.REQUEST_INVALID, "canonical_hint must be a string")
        items.append(sync.SyncItem(
            client_ref=str(raw.get("client_ref") or ""),
            kind=str(raw.get("kind") or ""),
            format=str(raw.get("format") or ""),
            document=raw.get("document"),
            canonical_hint=str(hint or ""),
        ))
    return sync.SyncSource(kind, source_id), items


def preview_import(
    dependencies: ContentSyncDependencies, body: dict[str, Any], *, pushed_by_device: str = "",
) -> dict[str, Any]:
    try:
        source, items = parse_import_request(body)
        return sync.preview(dependencies.importers(pushed_by_device), source, items)
    except sync.SyncItemError as exc:
        return _failure(exc)


def commit_import(
    dependencies: ContentSyncDependencies, body: dict[str, Any], *, pushed_by_device: str = "",
) -> dict[str, Any]:
    decisions = body.get("decisions") or {}
    if not isinstance(decisions, dict):
        return {"ok": False, "error_code": sync.REQUEST_INVALID, "error": "decisions must be an object"}
    digest = body.get("plan_digest")
    if not isinstance(digest, str) or not digest:
        return {"ok": False, "error_code": "PLAN_DIGEST_REQUIRED", "error": "commit needs the previewed plan_digest"}
    try:
        source, items = parse_import_request(body)
        return sync.commit(
            dependencies.importers(pushed_by_device), source, items,
            confirmed_digest=digest, decisions=decisions,
        )
    except sync.SyncItemError as exc:
        return _failure(exc)


def export_content(
    dependencies: ContentSyncDependencies, body: dict[str, Any], *, server_instance_id: str,
) -> dict[str, Any]:
    raw_items = body.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return {"ok": False, "error_code": sync.REQUEST_INVALID, "error": "items must be a non-empty list"}
    requested: list[tuple[str, str]] = []
    for raw in raw_items:
        if not isinstance(raw, dict) or not isinstance(raw.get("canonical_id"), str):
            return {"ok": False, "error_code": sync.REQUEST_INVALID, "error": "every item needs kind and canonical_id"}
        requested.append((str(raw.get("kind") or ""), raw["canonical_id"]))
    try:
        return sync.export(dependencies.exporters(), requested, server_instance_id=server_instance_id)
    except sync.SyncItemError as exc:
        return _failure(exc)


__all__ = [
    "ContentSyncDependencies",
    "commit_import",
    "export_content",
    "parse_import_request",
    "preview_import",
]
