"""Confirmable Lorebook import plans: update / duplicate / skip.

``plan_lorebook_import`` shows what a commit would do against the current
store; ``execute_lorebook_plan`` carries out one confirmed item atomically.
The caller (the Lorebook service) revalidates ``plan_digest`` between the two.

Semantics per matched Book:

- update: full mirror. Book metadata and settings are overwritten, entries
  are upserted by their import id and entries the pushed Book no longer has
  are deleted. Bindings and ``enabled`` are server-side setup and are kept.
- duplicate: a new Book takes over the import identity (tracked); the old
  one is kept and detached, with its provenance intact.
- skip: nothing is written; the existing Book id is returned.
- unchanged: the draft equals what was last imported and the server copy was
  not edited since; nothing is written.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from src.content_modules.plan import Decision, ExistingMatch, PlanItem, content_digest
from src.content_modules.refs import ContentDraft
from src.lorebook.domain import LorebookDraft
from src.lorebook.importer import (
    DeclaredSource,
    book_settings,
    draft_lorebook_import,
    import_entry_id,
    in_import_transaction,
    legacy_book_id,
    lorebook_content_draft,
    write_import_entries,
)

#: Book fields that make up its content for ``server_modified`` detection.
#: ``enabled`` and bindings are server-side table setup, not imported content.
_STATE_BOOK_FIELDS = (
    "name", "description", "language", "scan_depth", "token_budget",
    "recursive_scanning", "settings",
)
_STATE_ENTRY_IGNORED = frozenset({"created_at", "updated_at", "book_id", "world_id"})


def book_state_digest(store: Any, book_id: str) -> str:
    """Digest of a stored Book's imported content (metadata + entries)."""

    book = store.get_lorebook(book_id) or {}
    entries = sorted(
        (
            {key: value for key, value in row.items() if key not in _STATE_ENTRY_IGNORED}
            for row in store.list_book_entries(book_id)
        ),
        key=lambda row: str(row.get("id") or ""),
    )
    return content_digest({
        "book": {key: book.get(key) for key in _STATE_BOOK_FIELDS},
        "entries": entries,
    })


@dataclass(frozen=True)
class LorebookImportPlan:
    draft: LorebookDraft
    content_draft: ContentDraft
    declared: DeclaredSource | None
    item: PlanItem


def tracked_book(
    store: Any, content_draft: ContentDraft, declared: DeclaredSource | None,
) -> dict[str, Any] | None:
    """The one Book currently following this draft's identity, if any.

    A declared (device) draft follows a Book by its external id. A legacy
    draft is identified by its source alone and matches only Books written
    without an external id. Detached Books never match.
    """

    for book in store.list_lorebooks():
        if str(book.get("import_link") or "") == "detached":
            continue
        if str(book.get("source_kind") or "") != content_draft.source_kind:
            continue
        if str(book.get("source_id") or "") != content_draft.source_id:
            continue
        external = str(book.get("external_id") or "")
        if declared is not None and external == content_draft.external_id:
            return book
        if declared is None and not external:
            return book
    return None


def plan_lorebook_import(
    store: Any, payload: dict[str, Any], *, declared: DeclaredSource | None = None,
) -> LorebookImportPlan:
    """What a commit of ``payload`` would do against the current store."""

    draft = draft_lorebook_import(payload)
    content_draft = lorebook_content_draft(payload, declared=declared)
    book = tracked_book(store, content_draft, declared)
    existing: ExistingMatch | None = None
    unchanged = False
    if book is not None:
        book_id = str(book["id"])
        recorded = str(book.get("import_state_digest") or "")
        # Books imported before plans existed carry no recorded state, so
        # whether they were edited since is unknown rather than "no".
        server_modified = (book_state_digest(store, book_id) != recorded) if recorded else None
        planned = {
            import_entry_id(store, draft, book_id, index, entry)
            for index, entry in enumerate(draft.entries)
        }
        current = {str(row.get("id") or "") for row in store.list_book_entries(book_id)}
        existing = ExistingMatch(
            canonical_id=book_id,
            state_token=str(int(book.get("revision") or 0)),
            server_modified=server_modified,
            details={
                "name": str(book.get("name") or ""),
                "entries_add": len(planned - current),
                "entries_update": len(planned & current),
                "entries_remove": len(current - planned),
            },
        )
        unchanged = (
            server_modified is False
            and str(book.get("source_digest") or "") == content_draft.digest
        )
    item = PlanItem(
        client_ref=content_draft.ref.canonical(),
        kind="lorebook",
        draft_digest=content_draft.digest,
        action="create" if existing is None else ("unchanged" if unchanged else "update"),
        existing=existing,
    )
    return LorebookImportPlan(draft=draft, content_draft=content_draft, declared=declared, item=item)


def _new_book_id(store: Any, plan: LorebookImportPlan) -> str:
    if plan.declared is None:
        base = legacy_book_id(plan.draft)
    else:
        key = f"{plan.declared.source_id}/{plan.declared.external_id}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        base = f"import:{plan.declared.source_kind}:{digest}"
    book_id = base
    while store.get_lorebook(book_id) is not None:
        book_id = f"{base}:{uuid.uuid4().hex[:8]}"
    return book_id


def _book_fields(draft: LorebookDraft) -> dict[str, Any]:
    return {
        "name": draft.name,
        "description": draft.description,
        "language": draft.language,
        "scan_depth": draft.settings.get("scan_depth", 0),
        "token_budget": draft.settings.get("token_budget", 0),
        "recursive_scanning": draft.settings.get("recursive_scanning", False),
    }


def execute_lorebook_plan(
    store: Any,
    plan: LorebookImportPlan,
    decision: Decision | None,
    *,
    binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Carry out one confirmed plan item atomically.

    ``decision`` is ``None`` only when nothing matched (create).
    """

    item, draft, content = plan.item, plan.draft, plan.content_draft
    existing = item.existing
    if existing is not None and decision == "skip":
        return {"status": "skipped", "book_id": existing.canonical_id, "entries_removed": 0}
    if existing is not None and decision == "update" and item.action == "unchanged":
        return {"status": "unchanged", "book_id": existing.canonical_id, "entries_removed": 0}

    def _bind(book_id: str) -> None:
        if binding:
            store.bind_lorebook({
                "id": binding.get("id", f"binding:{book_id}"), "book_id": book_id,
                **{key: value for key, value in binding.items() if key != "id"},
            })

    def _record(book_id: str) -> None:
        store.record_lorebook_import(
            book_id,
            source_kind=content.source_kind,
            source_id=content.source_id,
            external_id=plan.declared.external_id if plan.declared else "",
            source_digest=content.digest,
            import_link="tracked",
            import_state_digest=book_state_digest(store, book_id),
        )

    if existing is not None and decision == "update":
        book_id = existing.canonical_id
        removed: list[str] = []

        def _mirror() -> None:
            store.update_lorebook(book_id, {**_book_fields(draft), "settings_json": book_settings(draft)})
            _bind(book_id)
            written = set(write_import_entries(store, draft, book_id, binding))
            # Full mirror: an entry the pushed Book no longer has is removed.
            for row in store.list_book_entries(book_id):
                entry_id = str(row.get("id") or "")
                if entry_id not in written:
                    store.delete_book_entry(book_id, entry_id)
                    removed.append(entry_id)
            _record(book_id)

        in_import_transaction(store, _mirror)
        return {"status": "updated", "book_id": book_id, "entries_removed": len(removed)}

    book_id = _new_book_id(store, plan)
    detached = existing.canonical_id if existing is not None else ""

    def _create() -> None:
        if detached:
            # "Keep both": the old copy stops following the source (its
            # provenance stays) and the new copy takes over the identity.
            store.detach_lorebook(detached)
        store.create_lorebook({
            "id": book_id, **_book_fields(draft), "settings": book_settings(draft),
            "source_kind": content.source_kind, "source_id": content.source_id,
        })
        _bind(book_id)
        write_import_entries(store, draft, book_id, binding)
        _record(book_id)

    in_import_transaction(store, _create)
    result: dict[str, Any] = {
        "status": "duplicated" if detached else "created", "book_id": book_id, "entries_removed": 0,
    }
    if detached:
        result["detached_book_id"] = detached
    return result


__all__ = [
    "LorebookImportPlan",
    "book_state_digest",
    "execute_lorebook_plan",
    "plan_lorebook_import",
    "tracked_book",
]
