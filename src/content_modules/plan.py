"""Confirmable import plans: per-item decisions and plan revalidation.

A preview shows the user, item by item, what a commit would do against the
server state *at preview time*. The commit request echoes ``plan_digest``; the
server recomputes the plan from the re-sent documents and the current state
and refuses to act on a plan the user did not see (``PLAN_STALE``).

The digest covers, per item, the draft digest, the matched canonical object
and that object's state token. Decisions are not part of it: they are the
user's answer to the plan, not part of the plan.

This module owns only the kind-neutral vocabulary. Each content kind owns its
matching, its state token and its writes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

PlanAction = Literal["create", "update", "unchanged"]
Decision = Literal["update", "duplicate", "skip"]

DECISIONS: tuple[Decision, ...] = ("update", "duplicate", "skip")

PLAN_STALE = "PLAN_STALE"
DECISION_REQUIRED = "DECISION_REQUIRED"
DECISION_NOT_ALLOWED = "DECISION_NOT_ALLOWED"


@dataclass(frozen=True, slots=True)
class ExistingMatch:
    """The canonical object a draft's identity currently resolves to."""

    canonical_id: str
    state_token: str
    #: ``None`` when the object predates import bookkeeping and nobody can
    #: tell whether it was edited on the server since.
    server_modified: bool | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlanItem:
    client_ref: str
    kind: str
    draft_digest: str
    action: PlanAction
    existing: ExistingMatch | None = None

    @property
    def allowed(self) -> tuple[Decision, ...]:
        # "update" on an unchanged item is accepted and writes nothing, so a
        # client can answer every match the same way.
        return () if self.existing is None else DECISIONS

    def digest_basis(self) -> dict[str, str]:
        return {
            "client_ref": self.client_ref,
            "kind": self.kind,
            "draft_digest": self.draft_digest,
            "canonical_id": self.existing.canonical_id if self.existing else "",
            "state_token": self.existing.state_token if self.existing else "",
        }

    def to_portable_dict(self) -> dict[str, Any]:
        existing = None
        if self.existing is not None:
            existing = {
                "canonical_id": self.existing.canonical_id,
                "state_token": self.existing.state_token,
                "server_modified": self.existing.server_modified,
                **dict(self.existing.details),
            }
        return {
            "client_ref": self.client_ref,
            "kind": self.kind,
            "draft_digest": self.draft_digest,
            "action": self.action,
            "existing": existing,
            "allowed": list(self.allowed),
        }


def plan_digest(items: Iterable[PlanItem]) -> str:
    basis = sorted(
        (item.digest_basis() for item in items),
        key=lambda row: (row["kind"], row["client_ref"]),
    )
    text = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class PlanDecisionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def resolve_decision(item: PlanItem, raw: Any) -> Decision | None:
    """Validate the user's answer for one item; ``None`` means "create".

    A match always needs an explicit answer: silently picking one would make
    "overwrite my server copy" the default.
    """

    if item.existing is None:
        if raw not in (None, "", "create"):
            raise PlanDecisionError(DECISION_NOT_ALLOWED, "nothing to update, duplicate or skip")
        return None
    if raw in (None, ""):
        raise PlanDecisionError(DECISION_REQUIRED, "an existing copy needs update, duplicate or skip")
    if raw not in item.allowed:
        raise PlanDecisionError(DECISION_NOT_ALLOWED, f"decision not allowed here: {raw!r}")
    decision: Decision = raw
    return decision


def content_digest(value: Any) -> str:
    """Deterministic digest of JSON-like content."""

    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "DECISIONS",
    "DECISION_NOT_ALLOWED",
    "DECISION_REQUIRED",
    "Decision",
    "ExistingMatch",
    "PLAN_STALE",
    "PlanAction",
    "PlanDecisionError",
    "PlanItem",
    "content_digest",
    "plan_digest",
    "resolve_decision",
]
