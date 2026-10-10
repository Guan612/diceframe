"""Confirmable character card imports: preview -> plan_digest -> commit.

A client pushes one portable card (``chara_card_v3`` envelope, DiceFrame body
in ``data.extensions.diceframe``) under its declared device identity. The card
and its embedded ``character_book`` are two plan items; the book is a Lorebook
item with the external id ``<card external id>.book`` and is left unbound.

Per matched card:

- update: portable fields are overwritten; server-side fields (id, plugin
  provenance, ruleset revision/log) are kept, and so is the server portrait
  when the push carries no portable one;
- duplicate: a new card takes over the identity (tracked) and the old one is
  kept, detached;
- skip / unchanged: nothing is written.

Plugin cards, cards tracked by another source and rules-aware server cards are
offered duplicate/skip only. Rules-aware (D&D) pushes are ``unsupported`` in
this version. Portraits that point at server-local assets are dropped with a
warning.

``cards.json`` has no storage-level uniqueness, so planning and writing run
under the library lock: one identity is tracked by at most one card.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.content_modules.adapters.character_card_v3 import CardV3FormatError, read_card_v3
from src.content_modules.plan import (
    PLAN_STALE,
    Decision,
    DeclaredSource,
    ExistingMatch,
    PlanDecisionError,
    PlanItem,
    content_digest,
    declared_import_source,
    plan_digest,
    resolve_decision,
)
from src.content_modules.refs import ContentDraft
from src.engine.world.contracts import canonical_id
from src.lorebook.import_plan import (
    LorebookImportPlan,
    execute_lorebook_plan,
    plan_lorebook_import,
)
from src.lorebook.store import LorebookIdentityConflict
from src.webui.character_card_projection import (
    CARD_PROVENANCE_KEY,
    card_provenance,
    is_plugin_card,
    is_tracked_card,
)

CARD_KIND = "character_template"

IMPORT_SOURCE_INVALID = "IMPORT_SOURCE_INVALID"
CARD_IDENTITY_CONFLICT = "CARD_IDENTITY_CONFLICT"
RULESET_CARD_UNSUPPORTED = "RULESET_CARD_UNSUPPORTED"
PORTRAIT_NOT_PORTABLE = "PORTRAIT_NOT_PORTABLE"
BOOK_NOT_IMPORTED = "BOOK_NOT_IMPORTED"

#: Why a matched card cannot be updated by this push.
LOCKED_PLUGIN_CARD = "PLUGIN_CARD"
LOCKED_TRACKED_BY_OTHER_SOURCE = "TRACKED_BY_OTHER_SOURCE"
LOCKED_RULESET_CARD = "RULESET_CARD"

#: Never taken from a pushed body: server ids, plugin ownership and the rules
#: runtime's own bookkeeping.
_SERVER_ONLY_FIELDS = (
    "id", "card_id", CARD_PROVENANCE_KEY, "source_plugin", "plugin_content_id",
    "raw_sillytavern", "ruleset_revision", "ruleset_operation_log", "ruleset_runtime",
)
#: Kept from the server copy when a push updates it.
_PRESERVED_ON_UPDATE = (
    "id", "source_plugin", "plugin_content_id", "ruleset_revision", "ruleset_operation_log",
)
#: A body carrying rules-runtime authority is a rules-aware card.
_RULESET_FIELDS = ("ruleset_character", "rule_binding")


class CardIdentityConflict(ValueError):
    code = CARD_IDENTITY_CONFLICT


@dataclass(frozen=True)
class CardImportDependencies:
    read_cards: Callable[[], list[dict[str, Any]]]
    write_cards: Callable[[list[dict[str, Any]]], None]
    lock: Callable[[], AbstractContextManager[Any]]
    to_card: Callable[[dict[str, Any], str], dict[str, Any]]
    new_card_id: Callable[[], str]
    is_ruleset_card: Callable[[dict[str, Any]], bool] | None = None
    lorebook: Any | None = None


@dataclass(frozen=True)
class CardImportPlan:
    declared: DeclaredSource
    draft: ContentDraft
    card: dict[str, Any]
    item: PlanItem
    matched: dict[str, Any] | None
    book: LorebookImportPlan | None
    warnings: tuple[dict[str, str], ...] = field(default_factory=tuple)

    @property
    def items(self) -> list[PlanItem]:
        return [self.item, *([self.book.item] if self.book is not None else [])]

    def digest(self) -> str:
        return plan_digest(self.items)

    def view(self) -> dict[str, Any]:
        return {
            "ok": True,
            "card": copy.deepcopy(self.card),
            "warnings": list(self.warnings),
            "plan": {
                "plan_digest": self.digest(),
                "items": [item.to_portable_dict() for item in self.items],
            },
        }


class _ImportRequestError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _without_provenance(card: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in card.items() if key != CARD_PROVENANCE_KEY}


def _state_token(card: dict[str, Any]) -> str:
    return content_digest(card)


def _portable_portrait(value: Any, warnings: list[dict[str, str]]) -> dict[str, str] | None:
    if value in (None, {}):
        return None
    if isinstance(value, dict) and value.get("kind") == "builtin":
        portrait_id = str(value.get("id") or "")
        if portrait_id and len(portrait_id) <= 100:
            return {"kind": "builtin", "id": portrait_id}
    warnings.append({
        "code": PORTRAIT_NOT_PORTABLE,
        "message": "the portrait refers to an image stored on another device or server and was not imported",
    })
    return None


def _portable_card(
    dependencies: CardImportDependencies, body: dict[str, Any], warnings: list[dict[str, str]],
) -> dict[str, Any]:
    cleaned = {key: value for key, value in body.items() if key not in _SERVER_ONLY_FIELDS}
    sheet = cleaned.get("character_sheet")
    if isinstance(sheet, dict):
        cleaned["character_sheet"] = {
            key: value for key, value in sheet.items() if key not in _SERVER_ONLY_FIELDS
        }
    portrait = _portable_portrait(cleaned.pop("portrait", None), warnings)
    card = dependencies.to_card(cleaned, str(cleaned.get("source") or "device"))
    for key in _SERVER_ONLY_FIELDS:
        card.pop(key, None)
    card["portrait"] = portrait or {}
    return card


def _is_rules_aware(dependencies: CardImportDependencies, card: dict[str, Any]) -> bool:
    if any(isinstance(card.get(key), dict) for key in _RULESET_FIELDS):
        return True
    return bool(dependencies.is_ruleset_card and dependencies.is_ruleset_card(card))


def _tracks(card: dict[str, Any], declared: DeclaredSource) -> bool:
    provenance = card_provenance(card)
    return bool(
        provenance is not None
        and provenance["link"] == "tracked"
        and (provenance["source_kind"], provenance["source_id"], provenance["external_id"])
        == (declared.source_kind, declared.source_id, declared.external_id)
    )


def _parse_request(body: dict[str, Any]) -> tuple[DeclaredSource, dict[str, Any], str]:
    try:
        declared = declared_import_source(body.get("source"), body.get("external_id"))
    except ValueError as exc:
        raise _ImportRequestError(IMPORT_SOURCE_INVALID, str(exc)) from exc
    if declared is None:
        raise _ImportRequestError(IMPORT_SOURCE_INVALID, "a card push must declare its source and external_id")
    document = body.get("document")
    hint = body.get("canonical_hint")
    if hint is not None and not isinstance(hint, str):
        raise _ImportRequestError(IMPORT_SOURCE_INVALID, "canonical_hint must be a card id")
    return declared, document, str(hint or "")


def _book_plan(
    dependencies: CardImportDependencies,
    declared: DeclaredSource,
    character_book: dict[str, Any] | None,
    name: str,
    warnings: list[dict[str, str]],
) -> LorebookImportPlan | None:
    if character_book is None:
        return None
    if dependencies.lorebook is None:
        warnings.append({"code": BOOK_NOT_IMPORTED, "message": "lorebooks are disabled on this server"})
        return None
    try:
        external_id = canonical_id(f"{declared.external_id}.book", field="external id")
    except ValueError as exc:
        raise _ImportRequestError(IMPORT_SOURCE_INVALID, str(exc)) from exc
    book = dict(character_book)
    if not str(book.get("name") or "").strip():
        book["name"] = f"{name} lore" if name else "Imported character lore"
    return plan_lorebook_import(
        dependencies.lorebook,
        {"spec": "lorebook_v3", "data": {"lorebook": book}},
        declared=DeclaredSource(declared.source_kind, declared.source_id, external_id),
    )


def _match(
    dependencies: CardImportDependencies,
    cards: list[dict[str, Any]],
    declared: DeclaredSource,
    hint: str,
) -> tuple[dict[str, Any] | None, str]:
    tracked = sorted((card for card in cards if _tracks(card, declared)), key=lambda c: str(c.get("id") or ""))
    if tracked:
        return tracked[0], "identity"
    if hint:
        for card in cards:
            if str(card.get("id") or "") == hint:
                return card, "hint"
    return None, ""


def plan_card_import(dependencies: CardImportDependencies, body: dict[str, Any]) -> CardImportPlan:
    """What a commit of this push would do. Callers hold the library lock."""

    declared, document, hint = _parse_request(body)
    try:
        parsed = read_card_v3(document)
    except CardV3FormatError as exc:
        raise _ImportRequestError(exc.code, str(exc)) from exc
    warnings: list[dict[str, str]] = []
    card = _portable_card(dependencies, parsed.body, warnings)
    draft = ContentDraft(
        kind=CARD_KIND,
        source_kind=declared.source_kind,
        source_id=declared.source_id,
        external_id=declared.external_id,
        payload=card,
        provenance={"format": "chara_card_v3"},
        digest=content_digest(card),
    )
    client_ref = draft.ref.canonical()
    name = str(card.get("character_name") or "")
    book = _book_plan(dependencies, declared, parsed.character_book, name, warnings)

    if _is_rules_aware(dependencies, card):
        item = PlanItem(
            client_ref=client_ref, kind=CARD_KIND, draft_digest=draft.digest,
            action="unsupported", reason=RULESET_CARD_UNSUPPORTED,
        )
        return CardImportPlan(declared, draft, card, item, None, book, tuple(warnings))

    matched, matched_by = _match(dependencies, dependencies.read_cards(), declared, hint)
    if matched is None:
        item = PlanItem(client_ref=client_ref, kind=CARD_KIND, draft_digest=draft.digest, action="create")
        return CardImportPlan(declared, draft, card, item, None, book, tuple(warnings))

    provenance = card_provenance(matched) if matched_by == "identity" else None
    recorded = (provenance or {}).get("imported_state_digest", "")
    server_modified = (
        content_digest(_without_provenance(matched)) != recorded if recorded else None
    )
    lock_reason = ""
    if is_plugin_card(matched):
        lock_reason = LOCKED_PLUGIN_CARD
    elif is_tracked_card(matched) and not _tracks(matched, declared):
        lock_reason = LOCKED_TRACKED_BY_OTHER_SOURCE
    elif _is_rules_aware(dependencies, matched):
        lock_reason = LOCKED_RULESET_CARD
    unchanged = (
        server_modified is False
        and (provenance or {}).get("source_digest") == draft.digest
    )
    item = PlanItem(
        client_ref=client_ref,
        kind=CARD_KIND,
        draft_digest=draft.digest,
        action="unchanged" if unchanged else "update",
        existing=ExistingMatch(
            canonical_id=str(matched.get("id") or ""),
            state_token=_state_token(matched),
            server_modified=server_modified,
            details={
                "name": str(matched.get("character_name") or ""),
                "matched_by": matched_by,
            },
        ),
        restricted_to=("duplicate", "skip") if lock_reason else None,
        reason=lock_reason,
    )
    return CardImportPlan(declared, draft, card, item, matched, book, tuple(warnings))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _execute_card(
    dependencies: CardImportDependencies,
    plan: CardImportPlan,
    decision: Decision | None,
    *,
    book_id: str,
    pushed_by_device: str,
) -> dict[str, Any]:
    item, matched = plan.item, plan.matched
    if matched is not None and decision == "skip":
        return {"status": "skipped", "card_id": str(matched.get("id") or "")}
    if matched is not None and decision == "update" and item.action == "unchanged":
        return {"status": "unchanged", "card_id": str(matched.get("id") or "")}

    cards = dependencies.read_cards()
    target_id = str(matched.get("id") or "") if matched is not None else ""
    if decision == "update" and matched is not None:
        card = copy.deepcopy(plan.card)
        for key in _PRESERVED_ON_UPDATE:
            if key in matched:
                card[key] = copy.deepcopy(matched[key])
        # A push without a portable portrait never removes the server's own.
        if not card.get("portrait") and matched.get("portrait"):
            card["portrait"] = copy.deepcopy(matched["portrait"])
        status, replaced, detached = "updated", target_id, ""
    else:
        card = {**copy.deepcopy(plan.card), "id": dependencies.new_card_id()}
        replaced = ""
        detached = target_id if matched is not None and _tracks(matched, plan.declared) else ""
        status = "duplicated" if matched is not None else "created"

    provenance: dict[str, str] = {
        "source_kind": plan.declared.source_kind,
        "source_id": plan.declared.source_id,
        "external_id": plan.declared.external_id,
        "link": "tracked",
        "source_digest": plan.draft.digest,
        "imported_at": _now(),
    }
    if pushed_by_device:
        provenance["pushed_by_device"] = pushed_by_device
    if book_id:
        provenance["book_id"] = book_id
    provenance["imported_state_digest"] = content_digest(_without_provenance(card))
    card[CARD_PROVENANCE_KEY] = provenance

    written: list[dict[str, Any]] = []
    for existing in cards:
        existing_id = str(existing.get("id") or "")
        if existing_id == replaced:
            continue
        if existing_id == detached:
            existing = copy.deepcopy(existing)
            existing[CARD_PROVENANCE_KEY] = {**existing[CARD_PROVENANCE_KEY], "link": "detached"}
        elif _tracks(existing, plan.declared):
            # The plan was revalidated under the lock, so this is a broken
            # invariant rather than a race: refuse instead of tracking twice.
            raise CardIdentityConflict("this identity is already tracked by another card")
        written.append(existing)
    if replaced:
        index = next(i for i, existing in enumerate(cards) if str(existing.get("id") or "") == replaced)
        written.insert(min(index, len(written)), card)
    else:
        written.append(card)
    dependencies.write_cards(written)
    result = {"status": status, "card_id": str(card["id"]), "state_token": _state_token(card)}
    if detached:
        result["detached_card_id"] = detached
    return result


def preview_card_import(dependencies: CardImportDependencies, body: dict[str, Any]) -> dict[str, Any]:
    try:
        with dependencies.lock():
            return plan_card_import(dependencies, body).view()
    except _ImportRequestError as exc:
        return {"ok": False, "error_code": exc.code, "error": str(exc)}


def commit_card_import(
    dependencies: CardImportDependencies,
    body: dict[str, Any],
    *,
    pushed_by_device: str = "",
) -> dict[str, Any]:
    """Revalidate the confirmed plan and apply the user's decisions.

    Decisions are keyed by plan item ``client_ref``. Every decision is
    validated before anything is written; the embedded book is written first
    so the card can link to it.
    """

    decisions = body.get("decisions") or {}
    if not isinstance(decisions, dict):
        return {"ok": False, "error_code": "DECISIONS_INVALID", "error": "decisions must be an object"}
    with dependencies.lock():
        try:
            plan = plan_card_import(dependencies, body)
        except _ImportRequestError as exc:
            return {"ok": False, "error_code": exc.code, "error": str(exc)}
        if str(body.get("plan_digest") or "") != plan.digest():
            return {
                "ok": False, "error_code": PLAN_STALE,
                "error": "the server state changed since the preview; review the new plan",
                "preview": plan.view(),
            }
        try:
            card_decision = resolve_decision(plan.item, decisions.get(plan.item.client_ref))
            book_decision = (
                resolve_decision(plan.book.item, decisions.get(plan.book.item.client_ref))
                if plan.book is not None else None
            )
        except PlanDecisionError as exc:
            return {"ok": False, "error_code": exc.code, "error": str(exc)}

        items: list[dict[str, Any]] = []
        book_id = ""
        try:
            if plan.book is not None:
                book_result = execute_lorebook_plan(dependencies.lorebook, plan.book, book_decision)
                book_id = str(book_result["book_id"])
                items.append({"client_ref": plan.book.item.client_ref, "kind": "lorebook", **book_result})
            card_result = _execute_card(
                dependencies, plan, card_decision,
                book_id=book_id, pushed_by_device=pushed_by_device,
            )
        except (CardIdentityConflict, LorebookIdentityConflict) as exc:
            return {"ok": False, "error_code": exc.code, "error": str(exc), "items": items}
        items.insert(0, {"client_ref": plan.item.client_ref, "kind": CARD_KIND, **card_result})
    return {
        "ok": True,
        "card_id": card_result["card_id"],
        "book_id": book_id,
        "items": items,
        "warnings": list(plan.warnings),
    }


__all__ = [
    "CardImportDependencies",
    "CardImportPlan",
    "commit_card_import",
    "plan_card_import",
    "preview_card_import",
]
