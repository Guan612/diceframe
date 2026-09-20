from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class BookRef:
    book_id: str
    order: int = 100
    binding_id: str = ""
    role: str = ""

def resolve_active_books(instance: Any, viewer_kind: str = "gm", viewer_uid: str = "", action_actor_uids: list[str] | None = None) -> list[BookRef]:
    store = getattr(instance, "lorebook_store", None) or getattr(instance, "lorebook", None)
    world_id = str(getattr(instance, "world_id", "") or "")
    if not store:
        return []
    bindings = store.list_bindings()
    actors = set(str(uid) for uid in action_actor_uids or [])
    refs = []
    for binding in bindings:
        if not binding.get("enabled", True):
            continue
        kind, scope = str(binding.get("scope_kind", "")), str(binding.get("scope_id", ""))
        if kind == "world" and scope == world_id:
            refs.append(BookRef(str(binding["book_id"]), int(binding.get("order", 100)), str(binding.get("id", "")), str(binding.get("role", ""))))
        elif kind in {"viewer", "character"} and scope == viewer_uid and viewer_kind != "party":
            refs.append(BookRef(str(binding["book_id"]), int(binding.get("order", 100)), str(binding.get("id", "")), str(binding.get("role", ""))))
        elif kind in {"actor", "character"} and scope in actors:
            refs.append(BookRef(str(binding["book_id"]), int(binding.get("order", 100)), str(binding.get("id", "")), str(binding.get("role", ""))))
    return sorted({ref.book_id: ref for ref in refs}.values(), key=lambda ref: (ref.order, ref.book_id, ref.binding_id))
