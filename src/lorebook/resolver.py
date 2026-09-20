from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class BookRef:
    book_id: str
    order: int = 100
    binding_id: str = ""
    role: str = ""
    scan_depth: int = 0
    token_budget: int = 0
    recursive_scanning: bool = False
    settings: dict[str, Any] | None = None
    updated_at: str = ""

def resolve_active_books(instance: Any, viewer_kind: str = "gm", viewer_uid: str = "", action_actor_uids: list[str] | None = None, *, store: Any | None = None) -> list[BookRef]:
    store = store or getattr(instance, "lorebook_store", None) or getattr(instance, "lorebook", None)
    world_id = str(getattr(instance, "world_id", "") or "")
    if not store:
        return []
    bindings = store.list_bindings()
    actors = set(str(uid) for uid in action_actor_uids or [])
    refs = []
    books = {}
    if hasattr(store, "get_lorebook"):
        for binding in bindings:
            book_id = str(binding.get("book_id") or "")
            if book_id and book_id not in books:
                books[book_id] = store.get_lorebook(book_id) or {}
    for binding in bindings:
        if not binding.get("enabled", True):
            continue
        kind, scope = str(binding.get("scope_kind", "")), str(binding.get("scope_id", ""))
        book = books.get(str(binding.get("book_id") or ""), {})
        settings = book.get("settings") if isinstance(book.get("settings"), dict) else {}
        common = dict(
            scan_depth=int(book.get("scan_depth", 0) or 0),
            token_budget=int(book.get("token_budget", 0) or 0),
            recursive_scanning=bool(book.get("recursive_scanning", False)),
            settings=settings,
            updated_at=str(book.get("updated_at") or ""),
        )
        if kind == "global":
            refs.append(BookRef(str(binding["book_id"]), int(binding.get("order", 100)), str(binding.get("id", "")), str(binding.get("role", "")), **common))
        elif kind == "world" and scope == world_id:
            refs.append(BookRef(str(binding["book_id"]), int(binding.get("order", 100)), str(binding.get("id", "")), str(binding.get("role", "")), **common))
        elif kind == "game" and scope in {str(getattr(instance, "game_id", "") or ""), str(getattr(instance, "game_key", "") or "")}:
            refs.append(BookRef(str(binding["book_id"]), int(binding.get("order", 100)), str(binding.get("id", "")), str(binding.get("role", "")), **common))
        elif kind == "character" and viewer_kind != "party" and (scope == viewer_uid or scope in actors):
            refs.append(BookRef(str(binding["book_id"]), int(binding.get("order", 100)), str(binding.get("id", "")), str(binding.get("role", "")), **common))
    return sorted({ref.book_id: ref for ref in refs}.values(), key=lambda ref: (ref.order, ref.book_id, ref.binding_id))
