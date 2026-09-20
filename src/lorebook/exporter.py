from __future__ import annotations
from typing import Any


def export_lorebook_v3(store: Any, book_id: str) -> dict[str, Any]:
    """Export a canonical book using the stable ``lorebook_v3`` shape."""
    book = store.get_lorebook(book_id) or {}
    settings = dict(book.get("settings") or {})
    portable_book = {
        "name": book.get("name", ""), "description": book.get("description", ""),
        **settings,
        "scan_depth": book.get("scan_depth", settings.get("scan_depth", 0)),
        "token_budget": book.get("token_budget", settings.get("token_budget", 0)),
        "recursive_scanning": bool(book.get("recursive_scanning", settings.get("recursive_scanning", False))),
        "entries": [_v3_entry(row) for row in store.list_book_entries(book_id)],
    }
    return {"spec": "lorebook_v3", "data": {"lorebook": portable_book}}


def export_lorebook_native(store: Any, book_id: str) -> dict[str, Any]:
    """Export a lossless DiceFrame-native backup of one canonical book."""
    book = dict(store.get_lorebook(book_id) or {})
    entries = [dict(row) for row in store.list_book_entries(book_id)]
    bindings = [dict(row) for row in store.list_bindings() if row.get("book_id") == book_id]
    provenance = {
        "book": {key: book.get(key, "") for key in ("source_kind", "source_id", "source_version", "source_digest")},
        "entries": {str(row.get("id")): row.get("provenance", {}) for row in entries},
    }
    return {"spec": "diceframe_lorebook_native", "version": 1, "data": {
        "book": book, "bindings": bindings, "entries": entries,
        "provenance": provenance, "settings": dict(book.get("settings") or {}),
    }}


def _v3_entry(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"), "name": row.get("name"), "content": row.get("content", ""),
        "keys": row.get("keywords", []), "secondary_keys": row.get("secondary_keys", []),
        "enabled": bool(row.get("enabled", True)), "constant": bool(row.get("is_constant", False)),
        "insertion_order": row.get("order", 100), "priority": row.get("priority", 0),
        "extensions": row.get("extensions", {}), "provenance": row.get("provenance", {}),
    }
