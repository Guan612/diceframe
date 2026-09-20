"""Preview-first import service for all Lorebook formats."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from src.lorebook.adapters import from_legacy_entries, from_lorebook_v3, from_sillytavern
from src.lorebook.adapters.legacy import diceframe_compat_fields
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
        inner = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        book = inner.get("character_book", {}) if isinstance(inner, dict) else {}
        return from_lorebook_v3({"spec": "lorebook_v3", "data": {"lorebook": book}})
    return from_legacy_entries(payload)


def preview_lorebook_import(payload: dict[str, Any]) -> dict[str, Any]:
    fmt = detect_lorebook_format(payload)
    draft = draft_lorebook_import(payload)
    unsupported = sum(1 for warning in draft.warnings if "unsupported" in warning.lower())
    return {"format": fmt, "book": draft, "counts": {"entries": len(draft.entries), "mapped": len(draft.entries), "warnings": len(draft.warnings), "unsupported": unsupported}, "warnings": draft.warnings, "features": {"timed": any(bool(e.timed) for e in draft.entries), "recursive": any(bool(e.recursion_flags) for e in draft.entries)}}


def commit_lorebook_import(store: Any, draft: LorebookDraft, binding: dict[str, Any] | None = None, *, book_id: str | None = None) -> str:
    if not book_id:
        fingerprint = hashlib.sha256(json.dumps({"source": draft.source, "name": draft.name, "entries": [entry.external_id for entry in draft.entries]}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        book_id = str(draft.source.get("id") or f"import:{draft.source.get('kind', 'external')}:{fingerprint}")
    store.create_lorebook({"id": book_id, "name": draft.name, "description": draft.description, "language": draft.language, "settings": draft.settings, "source_kind": draft.source.get("kind", "import")})
    if binding:
        store.bind_lorebook({"id": binding.get("id", f"binding:{book_id}"), "book_id": book_id, **{k: v for k, v in binding.items() if k != "id"}})
    for index, entry in enumerate(draft.entries):
        entry_key = entry.external_id or str(index)
        entry_id = f"{book_id}:entry:{hashlib.sha256(entry_key.encode('utf-8')).hexdigest()[:16]}"
        provenance = {**draft.source, "external_id": entry.external_id} if entry.external_id else dict(draft.source)
        selective_logic = str(entry.selective_logic or "any").lower()
        match_mode = {"and": "all", "or": "any", "0": "any", "1": "all", "2": "not_all", "3": "not_any"}.get(selective_logic, selective_logic)
        if match_mode not in {"any", "all", "not_any", "not_all"}:
            match_mode = "any"
        payload = {"id": entry_id, "book_id": book_id, "name": entry.name, "content": entry.content, "keywords": entry.keys, "secondary_keys": entry.secondary_keys, "enabled": entry.enabled, "is_constant": entry.constant, "match_mode": match_mode, "selective_logic": selective_logic, "use_regex": entry.use_regex, "case_sensitive": entry.case_sensitive, "match_whole_words": entry.match_whole_words, "scan_depth": entry.scan_depth, "priority": entry.priority, "order": entry.insertion_order, "probability": entry.probability, "groups": entry.groups, "group_weight": entry.group_weight, "sticky": entry.timed.get("sticky", 0), "cooldown": entry.timed.get("cooldown", 0), "delay": entry.timed.get("delay", 0), "prompt_slot": entry.prompt_slot, "prioritize_inclusion": entry.prioritize_inclusion, "group_scoring": entry.group_scoring, "vector_activation": entry.vector_activation, "non_recursable": entry.recursion_flags.get("non_recursable", False), "prevent_further_recursion": entry.recursion_flags.get("prevent_further_recursion", False), "delay_until_recursion": entry.recursion_flags.get("delay_until_recursion", False), "recursion_level": int(entry.recursion_flags.get("recursion_level", 0) or 0), "provenance": provenance, "extensions": entry.extensions}
        payload.update(diceframe_compat_fields(entry))
        store.add_entry(payload)
    return book_id
