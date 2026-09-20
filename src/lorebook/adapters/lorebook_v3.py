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
        known_entry = {
            "id", "uid", "name", "comment", "content", "keys", "key", "secondary_keys", "keysecondary", "enabled", "constant",
            "selective", "selective_logic", "selectiveLogic", "case_sensitive", "use_regex", "match_whole_words",
            "scan_depth", "depth", "priority", "insertion_order", "order", "position", "probability", "groups",
            "group", "group_weight", "prioritize_inclusion", "group_scoring", "recursion_flags",
            "non_recursable", "prevent_further_recursion", "delay_until_recursion", "recursion_level",
            "sticky", "cooldown", "delay", "vector_activation", "prompt_slot", "extensions",
        }
        unknown_entry = {k: v for k, v in row.items() if k not in known_entry}
        extensions = dict(row.get("extensions", {})) if isinstance(row.get("extensions"), dict) else {}
        if unknown_entry:
            extensions.setdefault("_external_raw", {}).update(unknown_entry)
        entries.append(LoreEntryDraft(
            name=str(row.get("name") or row.get("comment") or row.get("uid") or ""), content=str(row.get("content", "") or ""),
            keys=_strings(row.get("keys", row.get("key", []))), secondary_keys=_strings(row.get("secondary_keys", row.get("keysecondary", []))),
            enabled=bool(row.get("enabled", True)), constant=bool(row.get("constant", False)),
            selective_logic=str(row.get("selective_logic", row.get("selectiveLogic", "any")) or "any"),
            case_sensitive=bool(row.get("case_sensitive", False)), use_regex=bool(row.get("use_regex", False)),
            match_whole_words=bool(row.get("match_whole_words", False)),
            insertion_order=int(row.get("insertion_order", row.get("order", row.get("position", 100))) or 100), priority=int(row.get("priority", 0) or 0),
            scan_depth=int(row.get("scan_depth", row.get("depth", book.get("scan_depth", 0))) or 0), external_id=str(row.get("id", row.get("uid", "")) or ""),
            groups=_strings(row.get("groups", row.get("group", []))),
            group_weight=int(row.get("group_weight", 1) or 1),
            prioritize_inclusion=bool(row.get("prioritize_inclusion", False)),
            group_scoring=str(row.get("group_scoring", "") or ""),
            recursion_flags={
                key: value for key, value in {
                    "non_recursable": bool(row.get("non_recursable", False)),
                    "prevent_further_recursion": bool(row.get("prevent_further_recursion", False)),
                    "delay_until_recursion": bool(row.get("delay_until_recursion", False)),
                    "recursion_level": int(row.get("recursion_level", 0) or 0),
                }.items() if value
            },
            timed={k: int(row[k]) for k in ("sticky", "cooldown", "delay") if isinstance(row.get(k), (int, float))},
            vector_activation=str(row.get("vector_activation", "off") or "off"),
            prompt_slot=str(row.get("prompt_slot", "") or ""),
            extensions=extensions,
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
