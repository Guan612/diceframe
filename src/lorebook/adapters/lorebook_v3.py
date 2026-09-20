from __future__ import annotations

from typing import Any

from src.lorebook.domain import LoreEntryDraft, LorebookDraft


def from_lorebook_v3(payload: dict[str, Any]) -> LorebookDraft:
    root = payload.get("data", payload)
    book = root.get("lorebook", root) if isinstance(root, dict) else {}
    raw_entries = book.get("entries", []) if isinstance(book, dict) else []
    entries: list[LoreEntryDraft] = []
    for raw in raw_entries if isinstance(raw_entries, list) else []:
        row = raw if isinstance(raw, dict) else {}
        entries.append(LoreEntryDraft(
            name=str(row.get("name", "") or ""), content=str(row.get("content", "") or ""),
            keys=_strings(row.get("keys", [])), secondary_keys=_strings(row.get("secondary_keys", [])),
            enabled=bool(row.get("enabled", True)), constant=bool(row.get("constant", False)),
            case_sensitive=bool(row.get("case_sensitive", False)), use_regex=bool(row.get("use_regex", False)),
            insertion_order=int(row.get("insertion_order", 100) or 100), priority=int(row.get("priority", 0) or 0),
            scan_depth=int(row.get("scan_depth", book.get("scan_depth", 0)) or 0), external_id=str(row.get("id", "") or ""),
            extensions=dict(row.get("extensions", {})) if isinstance(row.get("extensions"), dict) else {},
        ))
    known = {"name", "description", "scan_depth", "token_budget", "recursive_scanning", "entries", "extensions"}
    unknown = {k: v for k, v in book.items() if k not in known}
    warnings = [f"preserved unknown field: {k}" for k in sorted(unknown)]
    settings = {k: book[k] for k in ("scan_depth", "token_budget", "recursive_scanning") if k in book}
    return LorebookDraft(name=str(book.get("name", "Lorebook v3") or "Lorebook v3"), description=str(book.get("description", "") or ""), settings=settings, entries=entries, source={"kind": "lorebook_v3"}, warnings=warnings, preserved_extensions={"raw": unknown, "extensions": book.get("extensions", {})})


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(item).strip() for item in value or [] if str(item).strip()] if isinstance(value, list) else []
