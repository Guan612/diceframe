from __future__ import annotations
from typing import Any

def export_lorebook_v3(store: Any, book_id: str) -> dict[str, Any]:
    book = store.get_lorebook(book_id) or {}
    entries = store.list_book_entries(book_id)
    return {"spec": "lorebook_v3", "data": {"lorebook": {"name": book.get("name", ""), "description": book.get("description", ""), **book.get("settings", {}), "entries": [{"id": row.get("id"), "name": row.get("name"), "content": row.get("content", ""), "keys": row.get("keywords", []), "secondary_keys": row.get("secondary_keys", []), "enabled": bool(row.get("enabled", True)), "constant": bool(row.get("is_constant", False)), "insertion_order": row.get("order", 100), "priority": row.get("priority", 0), "extensions": row.get("extensions", {})} for row in entries]}}}
