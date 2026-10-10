"""Multi-kind content sync: one request, many items, one confirmable plan.

A client pushes several portable items from one declared source. Each item is
routed through ``CONTENT_KIND_REGISTRY`` to the importer that owns its
portable schema; the importer plans it (one or more plan items, e.g. a card
and its embedded book) and later executes the confirmed decisions.

Commit holds every involved importer's lock while it re-plans, compares the
``plan_digest``, validates every decision and only then writes, item by item.

This module knows no concrete kind. Importers and exporters are injected.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import AbstractContextManager, ExitStack
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Protocol

from src.content_modules.plan import (
    PLAN_STALE,
    Decision,
    PlanDecisionError,
    PlanItem,
    plan_digest,
    resolve_decision,
)
from src.content_modules.refs import CONTENT_KIND_REGISTRY, ContentRefError
from src.engine.world.contracts import canonical_id

logger = logging.getLogger("trpg")

KIND_NOT_SUPPORTED = "KIND_NOT_SUPPORTED"
TOO_MANY_ENTRIES = "TOO_MANY_ENTRIES"
ENTRY_TOO_LARGE = "ENTRY_TOO_LARGE"
IMPORT_FAILED = "IMPORT_FAILED"
NOT_ATTEMPTED = "not_attempted"

#: Per-book limits, enforced on the adapter's parsed draft so that every
#: document shape the adapter accepts is counted the same way.
MAX_ENTRIES_PER_BOOK = 2000
MAX_ENTRY_BYTES = 32 * 1024
CLIENT_REF_INVALID = "CLIENT_REF_INVALID"
DUPLICATE_CLIENT_REF = "DUPLICATE_CLIENT_REF"
REQUEST_INVALID = "REQUEST_INVALID"
NOT_FOUND = "NOT_FOUND"


class SyncItemError(ValueError):
    """One request item cannot be planned; the whole request fails closed."""

    def __init__(self, code: str, message: str, *, client_ref: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.client_ref = client_ref


@dataclass(frozen=True)
class SyncSource:
    kind: str
    id: str


@dataclass(frozen=True)
class SyncItem:
    client_ref: str
    kind: str
    format: str
    document: Any
    canonical_hint: str = ""


@dataclass
class KindPlan:
    """What one importer plans for one request item."""

    #: ``(client_ref, plan item)``; the first entry is the request item itself.
    entries: list[tuple[str, PlanItem]]
    #: Carries out resolved decisions (keyed by client_ref); returns one result
    #: per written/answered entry, each with ``client_ref``.
    execute: Callable[[Mapping[str, Decision | None]], list[dict[str, Any]]]
    warnings: list[dict[str, str]] = field(default_factory=list)


class KindImporter(Protocol):
    def lock(self) -> AbstractContextManager[Any]: ...

    def plan(self, source: SyncSource, item: SyncItem) -> KindPlan: ...


class KindExporter(Protocol):
    def export(self, canonical_id: str) -> dict[str, Any] | None:
        """``{format, document, state_token, provenance, warnings}`` or ``None``."""
        ...

    def status(self, canonical_id: str) -> dict[str, Any] | None:
        """``{state_token, provenance}`` without building the document, or ``None``."""
        ...


def check_book_limits(entries: Sequence[Any], *, client_ref: str) -> None:
    """Refuse a parsed book above the per-book entry count or entry size."""

    if len(entries) > MAX_ENTRIES_PER_BOOK:
        raise SyncItemError(
            TOO_MANY_ENTRIES, f"at most {MAX_ENTRIES_PER_BOOK} entries per book", client_ref=client_ref,
        )
    for entry in entries:
        row = asdict(entry) if is_dataclass(entry) and not isinstance(entry, type) else entry
        size = len(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8"))
        if size > MAX_ENTRY_BYTES:
            raise SyncItemError(
                ENTRY_TOO_LARGE, f"an entry exceeds {MAX_ENTRY_BYTES} bytes", client_ref=client_ref,
            )


def _schema(kind: str) -> str:
    try:
        return CONTENT_KIND_REGISTRY.spec(kind).portable_schema
    except ContentRefError as exc:
        raise SyncItemError(KIND_NOT_SUPPORTED, str(exc)) from exc


def _importer(importers: Mapping[str, KindImporter], item: SyncItem) -> KindImporter:
    importer = importers.get(_schema(item.kind))
    if importer is None:
        raise SyncItemError(
            KIND_NOT_SUPPORTED, f"content kind cannot be imported here: {item.kind!r}",
            client_ref=item.client_ref,
        )
    return importer


def _plan_all(
    importers: Mapping[str, KindImporter], source: SyncSource, items: Iterable[SyncItem],
) -> list[KindPlan]:
    plans: list[KindPlan] = []
    seen: set[str] = set()
    for item in items:
        try:
            canonical_id(item.client_ref, field="client_ref")
        except ValueError as exc:
            raise SyncItemError(CLIENT_REF_INVALID, str(exc), client_ref=str(item.client_ref)) from exc
        try:
            plan = _importer(importers, item).plan(source, item)
        except SyncItemError as exc:
            exc.client_ref = exc.client_ref or item.client_ref
            raise
        for client_ref, _entry in plan.entries:
            if client_ref in seen:
                raise SyncItemError(
                    DUPLICATE_CLIENT_REF, f"client_ref used twice: {client_ref!r}",
                    client_ref=client_ref,
                )
            seen.add(client_ref)
        plans.append(plan)
    return plans


def _entries(plans: list[KindPlan]) -> list[tuple[str, PlanItem]]:
    return [entry for plan in plans for entry in plan.entries]


def _view(plans: list[KindPlan]) -> dict[str, Any]:
    items = []
    for plan in plans:
        for index, (client_ref, item) in enumerate(plan.entries):
            row = {**item.to_portable_dict(), "client_ref": client_ref}
            if index == 0 and plan.warnings:
                row["warnings"] = list(plan.warnings)
            items.append(row)
    return {
        "ok": True,
        "plan_digest": plan_digest(item for _ref, item in _entries(plans)),
        "items": items,
    }


def _locks(importers: Mapping[str, KindImporter], items: list[SyncItem]) -> list[KindImporter]:
    involved: dict[str, KindImporter] = {}
    for item in items:
        involved[_schema(item.kind)] = _importer(importers, item)
    return [involved[key] for key in sorted(involved)]


def preview(importers: Mapping[str, KindImporter], source: SyncSource, items: list[SyncItem]) -> dict[str, Any]:
    with ExitStack() as stack:
        for importer in _locks(importers, items):
            stack.enter_context(importer.lock())
        return _view(_plan_all(importers, source, items))


def commit(
    importers: Mapping[str, KindImporter],
    source: SyncSource,
    items: list[SyncItem],
    *,
    confirmed_digest: str,
    decisions: Mapping[str, Any],
) -> dict[str, Any]:
    """Re-plan, refuse a stale plan, validate every decision, then write."""

    with ExitStack() as stack:
        for importer in _locks(importers, items):
            stack.enter_context(importer.lock())
        plans = _plan_all(importers, source, items)
        view = _view(plans)
        if confirmed_digest != view["plan_digest"]:
            return {
                "ok": False, "error_code": PLAN_STALE,
                "error": "the server state changed since the preview; review the new plan",
                "preview": view,
            }
        resolved: dict[str, Decision | None] = {}
        for client_ref, item in _entries(plans):
            try:
                resolved[client_ref] = resolve_decision(item, decisions.get(client_ref))
            except PlanDecisionError as exc:
                return {"ok": False, "error_code": exc.code, "error": str(exc), "client_ref": client_ref}
        results: list[dict[str, Any]] = []
        failed = False
        for index, plan in enumerate(plans):
            try:
                results.extend(plan.execute(resolved))
            except ValueError as exc:
                # An expected refusal (e.g. an identity conflict) for this
                # item only; it wrote nothing, the next items still run.
                failed = True
                results.append({
                    "client_ref": plan.entries[0][0], "status": "error",
                    "error_code": str(getattr(exc, "code", "") or IMPORT_FAILED),
                    "error": str(exc),
                })
            except Exception:
                # Unexpected: report exactly what was written so far and stop,
                # rather than keep writing on top of an unknown failure.
                logger.exception("content import item failed: %s", plan.entries[0][0])
                failed = True
                results.append({
                    "client_ref": plan.entries[0][0], "status": "error",
                    "error_code": IMPORT_FAILED, "error": "the server could not import this item",
                })
                for later in plans[index + 1:]:
                    results.extend(
                        {"client_ref": client_ref, "status": NOT_ATTEMPTED} for client_ref, _ in later.entries
                    )
                break
    return {"ok": not failed, "items": results}


def export(
    exporters: Mapping[str, KindExporter],
    requested: list[tuple[str, str]],
    *,
    server_instance_id: str,
) -> dict[str, Any]:
    """Portable documents plus an ``origin`` envelope per requested object."""

    rows: list[dict[str, Any]] = []
    for kind, canonical_id in requested:
        exporter = exporters.get(_schema(kind))
        if exporter is None:
            raise SyncItemError(KIND_NOT_SUPPORTED, f"content kind cannot be exported here: {kind!r}")
        exported = exporter.export(canonical_id)
        if exported is None:
            raise SyncItemError(NOT_FOUND, f"{kind} not found: {canonical_id!r}", client_ref=canonical_id)
        rows.append({
            "kind": kind,
            "format": exported["format"],
            "document": exported["document"],
            "warnings": list(exported.get("warnings") or []),
            "origin": {
                "server_instance_id": server_instance_id,
                "canonical_id": canonical_id,
                "state_token": exported["state_token"],
                "provenance": exported.get("provenance"),
            },
        })
    return {"ok": True, "items": rows}


def status(exporters: Mapping[str, KindExporter], requested: list[tuple[str, str]]) -> dict[str, Any]:
    """Cheap change detection: state token and provenance per object.

    A missing object is reported (``exists: false``), not an error, so a
    client can learn that the server copy was deleted.
    """

    rows: list[dict[str, Any]] = []
    for kind, canonical_id in requested:
        exporter = exporters.get(_schema(kind))
        if exporter is None:
            raise SyncItemError(KIND_NOT_SUPPORTED, f"content kind has no status here: {kind!r}")
        found = exporter.status(canonical_id)
        rows.append({
            "kind": kind,
            "canonical_id": canonical_id,
            "exists": found is not None,
            "state_token": (found or {}).get("state_token", ""),
            "provenance": (found or {}).get("provenance"),
        })
    return {"ok": True, "items": rows}


__all__ = [
    "CLIENT_REF_INVALID",
    "DUPLICATE_CLIENT_REF",
    "KIND_NOT_SUPPORTED",
    "KindExporter",
    "KindImporter",
    "KindPlan",
    "NOT_FOUND",
    "REQUEST_INVALID",
    "SyncItem",
    "SyncItemError",
    "SyncSource",
    "check_book_limits",
    "commit",
    "export",
    "preview",
    "status",
]
