"""Preview-first import service for all Lorebook formats."""
from __future__ import annotations

from typing import Any

from src.lorebook.adapters import from_legacy_entries, from_lorebook_v3, from_sillytavern
from src.lorebook.domain import LorebookDraft


def detect_lorebook_format(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return "diceframe_legacy"
    if payload.get("spec") == "lorebook_v3" or "lorebook" in payload and isinstance(payload.get("lorebook"), dict):
        return "lorebook_v3"
    inner = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if isinstance(inner.get("character_book"), dict):
        return "character_card_v3"
    rows = payload.get("entries", [])
    if isinstance(rows, list) and any(isinstance(row, dict) and any(k in row for k in ("key", "keysecondary", "selectiveLogic", "uid")) for row in rows):
        return "sillytavern"
    return "diceframe_legacy"


def draft_lorebook_import(payload: dict[str, Any]) -> LorebookDraft:
    fmt = detect_lorebook_format(payload)
    if fmt == "lorebook_v3":
        return from_lorebook_v3(payload)
    if fmt == "sillytavern":
        return from_sillytavern(payload)
    if fmt == "character_card_v3":
        book = payload.get("character_book", {})
        return from_lorebook_v3({"spec": "lorebook_v3", "data": {"lorebook": book}})
    return from_legacy_entries(payload)


def preview_lorebook_import(payload: dict[str, Any]) -> dict[str, Any]:
    fmt = detect_lorebook_format(payload)
    draft = draft_lorebook_import(payload)
    unsupported = sum(1 for warning in draft.warnings if "unsupported" in warning.lower())
    return {"format": fmt, "book": draft, "counts": {"entries": len(draft.entries), "mapped": len(draft.entries), "warnings": len(draft.warnings), "unsupported": unsupported}, "warnings": draft.warnings, "features": {"timed": any(bool(e.timed) for e in draft.entries), "recursive": any(bool(e.recursion_flags) for e in draft.entries)}}


def commit_lorebook_import(store: Any, draft: LorebookDraft, binding: dict[str, Any] | None = None, *, book_id: str | None = None) -> str:
    book_id = book_id or str(draft.source.get("id") or f"import:{draft.name}")
    store.create_lorebook({"id": book_id, "name": draft.name, "description": draft.description, "language": draft.language, "settings": draft.settings, "source_kind": draft.source.get("kind", "import")})
    if binding:
        store.bind_lorebook({"id": binding.get("id", f"binding:{book_id}"), "book_id": book_id, **{k: v for k, v in binding.items() if k != "id"}})
    for index, entry in enumerate(draft.entries):
        store.add_entry({"id": entry.external_id or f"{book_id}:entry:{index}", "book_id": book_id, "name": entry.name, "content": entry.content, "keywords": entry.keys, "secondary_keys": entry.secondary_keys, "enabled": entry.enabled, "is_constant": entry.constant, "match_mode": entry.selective_logic, "use_regex": entry.use_regex, "case_sensitive": entry.case_sensitive, "match_whole_words": entry.match_whole_words, "scan_depth": entry.scan_depth, "priority": entry.priority, "order": entry.insertion_order, "probability": entry.probability, "groups": entry.groups, "group_weight": entry.group_weight, "sticky": entry.timed.get("sticky", 0), "cooldown": entry.timed.get("cooldown", 0), "delay": entry.timed.get("delay", 0), "prompt_slot": entry.prompt_slot, "provenance": draft.source, "extensions": entry.extensions})
    return book_id
