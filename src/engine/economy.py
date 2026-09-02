"""Ruleset-neutral authoritative economy proposals and transactions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from src.engine.character_utils import apply_currency_delta

MAX_ECONOMY_AMOUNT = 100_000
ECONOMY_KINDS = {"payment", "purchase", "fee", "transfer", "reward"}
APPROVAL_POLICIES = {"payer", "gm", "system", "all_contributors"}
MAX_ECONOMY_OUTCOMES = 50
MAX_EFFECT_GROUPS = 50
MAX_EXTERNAL_EFFECT_DELIVERIES = 50


def economy_revision(instance: Any) -> int:
    economy = getattr(instance, "economy", {})
    if not isinstance(economy, dict):
        return 0
    return int(economy.get("decision_revision", 0) or 0)


def _advance_revision(instance: Any) -> int:
    revision = economy_revision(instance) + 1
    instance.economy["decision_revision"] = revision
    return revision


def _record_outcome(
    instance: Any,
    proposal: dict[str, Any],
    *,
    status: str,
    actor_uid: str,
) -> dict[str, Any]:
    effect_group = _effect_group_for(instance, proposal)
    outcome = {
        "id": f"outcome_{uuid4().hex}",
        "run_id": instance.run_id,
        "proposal_id": str(proposal.get("id") or ""),
        "effect_group_id": str(proposal.get("effect_group_id") or ""),
        "kind": str(proposal.get("kind") or "payment"),
        "payer_uid": str(proposal.get("payer_uid") or proposal.get("uid") or ""),
        "recipient_uid": str(proposal.get("recipient_uid") or ""),
        "amount": int(proposal.get("amount", 0) or 0),
        "reason": str(proposal.get("reason") or "经济提案")[:240],
        "status": str(status),
        "effects_status": (
            str(effect_group.get("status") or "pending")
            if effect_group is not None else "none"
        ),
        "actor_uid": str(actor_uid),
        "visibility": str(proposal.get("visibility") or "private"),
        "round": int(proposal.get("round", getattr(instance, "round_number", 0)) or 0),
        # Keep proposal origin round separate from the round in which this
        # decision was actually settled.  Rollback uses this field to remove
        # late-payment outcomes without invalidating the original offer.
        "resolved_round": int(getattr(instance, "round_number", 0) or 0),
        "resolved_at": str(proposal.get("resolved_at") or datetime.now(timezone.utc).isoformat()),
    }
    outcomes = instance.economy.setdefault("outcomes", [])
    outcomes.append(outcome)
    if len(outcomes) > MAX_ECONOMY_OUTCOMES:
        del outcomes[:-MAX_ECONOMY_OUTCOMES]
    return outcome


def queue_effect_group(
    instance: Any,
    proposals: list[dict[str, Any]],
    effects: dict[str, Any],
) -> dict[str, Any] | None:
    """Attach one deferred narrative effect batch to its authoritative decisions.

    The legacy tag protocol cannot assign individual effects to individual
    charges. When one response creates several proposals, the conservative
    contract is therefore one all-or-nothing decision barrier: all proposals
    must commit before effects apply, and any terminal rejection discards them.
    """

    candidates = [
        proposal for proposal in proposals
        if isinstance(proposal, dict)
        and proposal.get("status") == "pending"
        and proposal.get("run_id") == instance.run_id
    ]
    if not candidates or not effects:
        return None
    group = {
        "id": f"effect_{uuid4().hex}",
        "run_id": instance.run_id,
        "proposal_ids": [str(proposal.get("id") or "") for proposal in candidates],
        "effects": deepcopy(effects),
        "status": "pending",
        "round": int(getattr(instance, "round_number", 0) or 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    groups = instance.economy.setdefault("effect_groups", [])
    groups.append(group)
    if len(groups) > MAX_EFFECT_GROUPS:
        active = [
            item for item in groups
            if isinstance(item, dict)
            and item.get("status") in {"pending", "ready"}
        ]
        resolved = [
            item for item in groups
            if isinstance(item, dict)
            and item.get("status") not in {"pending", "ready"}
        ]
        resolved_budget = max(0, MAX_EFFECT_GROUPS - len(active))
        instance.economy["effect_groups"] = (
            active + resolved[-resolved_budget:]
            if resolved_budget else active
        )
    for proposal in candidates:
        proposal["effect_group_id"] = group["id"]
    return group


def _effect_group_for(
    instance: Any,
    proposal: dict[str, Any],
) -> dict[str, Any] | None:
    group_id = str(proposal.get("effect_group_id") or "")
    if not group_id:
        return None
    return next(
        (
            group for group in instance.economy.get("effect_groups", [])
            if isinstance(group, dict) and group.get("id") == group_id
        ),
        None,
    )


def _settle_effect_group(
    instance: Any,
    proposal: dict[str, Any],
) -> dict[str, Any] | None:
    group = _effect_group_for(instance, proposal)
    if group is None or group.get("status") != "pending":
        return None
    if proposal.get("status") in {"declined", "cancelled", "rejected"}:
        group["status"] = "discarded"
        group["resolved_at"] = str(proposal.get("resolved_at") or "")
        group.pop("effects", None)
        group_id = str(group.get("id") or "")
        for outcome in instance.economy.get("outcomes", []):
            if str(outcome.get("effect_group_id") or "") == group_id:
                outcome["effects_status"] = "discarded"
        return None
    proposal_ids = {str(item) for item in group.get("proposal_ids", []) if str(item)}
    states = {
        str(item.get("id") or ""): str(item.get("status") or "")
        for item in instance.economy.get("proposals", [])
        if isinstance(item, dict) and str(item.get("id") or "") in proposal_ids
    }
    if proposal_ids and all(states.get(proposal_id) == "committed" for proposal_id in proposal_ids):
        group["status"] = "ready"
        return deepcopy(group)
    return None


def complete_effect_group(instance: Any, group_id: str) -> bool:
    group = next(
        (
            item for item in instance.economy.get("effect_groups", [])
            if isinstance(item, dict) and item.get("id") == group_id
        ),
        None,
    )
    if group is None or group.get("run_id") != instance.run_id:
        return False
    if group.get("status") == "committed":
        return True
    if group.get("status") != "ready":
        return False
    group["status"] = "committed"
    group["committed_at"] = datetime.now(timezone.utc).isoformat()
    group.pop("effects", None)
    for outcome in instance.economy.get("outcomes", []):
        if str(outcome.get("effect_group_id") or "") == group_id:
            outcome["effects_status"] = "committed"
    return True


def queue_memory_delivery(
    instance: Any,
    *,
    effect_group_id: str,
    memory_delta: dict[str, Any],
    round_number: int,
) -> dict[str, Any] | None:
    """Persist an idempotent memory side effect before external delivery."""

    if not effect_group_id or not memory_delta:
        return None
    deliveries = instance.economy.setdefault("external_effects_outbox", [])
    delivery_id = f"memory:{effect_group_id}"
    existing = next(
        (
            item for item in deliveries
            if isinstance(item, dict) and item.get("id") == delivery_id
        ),
        None,
    )
    if existing is not None:
        return existing
    delivery = {
        "id": delivery_id,
        "run_id": instance.run_id,
        "effect_group_id": effect_group_id,
        "kind": "memory_delta",
        "payload": deepcopy(memory_delta),
        "round": int(round_number),
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    deliveries.append(delivery)
    if len(deliveries) > MAX_EXTERNAL_EFFECT_DELIVERIES:
        active = [
            item for item in deliveries
            if (
                isinstance(item, dict)
                and item.get("status") in {"pending", "reversal_pending"}
            )
        ]
        resolved = [
            item for item in deliveries
            if (
                isinstance(item, dict)
                and item.get("status") not in {"pending", "reversal_pending"}
            )
        ]
        budget = max(0, MAX_EXTERNAL_EFFECT_DELIVERIES - len(active))
        instance.economy["external_effects_outbox"] = (
            active + resolved[-budget:] if budget else active
        )
    return delivery


def pending_memory_deliveries(instance: Any) -> list[dict[str, Any]]:
    economy = getattr(instance, "economy", {})
    deliveries = (
        economy.get("external_effects_outbox", [])
        if isinstance(economy, dict) else []
    )
    return [
        item for item in deliveries
        if (
            isinstance(item, dict)
            and item.get("status") == "pending"
            and item.get("kind") == "memory_delta"
            and item.get("run_id") == getattr(instance, "run_id", "")
        )
    ]


def pending_memory_reversals(instance: Any) -> list[dict[str, Any]]:
    """Return delivered economy memories that must be undone after rollback."""

    economy = getattr(instance, "economy", {})
    deliveries = (
        economy.get("external_effects_outbox", [])
        if isinstance(economy, dict) else []
    )
    return [
        item for item in deliveries
        if (
            isinstance(item, dict)
            and item.get("status") == "reversal_pending"
            and item.get("kind") == "memory_delta"
            and item.get("run_id") == getattr(instance, "run_id", "")
        )
    ]


def complete_memory_delivery(instance: Any, delivery_id: str) -> bool:
    delivery = next(
        (
            item for item in instance.economy.get("external_effects_outbox", [])
            if isinstance(item, dict) and item.get("id") == delivery_id
        ),
        None,
    )
    if delivery is None or delivery.get("run_id") != instance.run_id:
        return False
    if delivery.get("status") == "delivered":
        return True
    if delivery.get("status") != "pending":
        return False
    delivery["status"] = "delivered"
    delivery["delivered_at"] = datetime.now(timezone.utc).isoformat()
    delivery.pop("payload", None)
    return True


def complete_memory_reversal(instance: Any, delivery_id: str) -> bool:
    delivery = next(
        (
            item for item in instance.economy.get("external_effects_outbox", [])
            if isinstance(item, dict) and item.get("id") == delivery_id
        ),
        None,
    )
    if delivery is None or delivery.get("run_id") != instance.run_id:
        return False
    if delivery.get("status") == "reversed":
        return True
    if delivery.get("status") != "reversal_pending":
        return False
    delivery["status"] = "reversed"
    delivery["reversed_at"] = datetime.now(timezone.utc).isoformat()
    return True


def cancel_proposals_for_player(
    instance: Any,
    uid: str,
    *,
    resolution_code: str = "PLAYER_REMOVED",
) -> set[str]:
    """Cancel unresolved proposals involving a player and discard their effects."""

    affected_ids: set[str] = set()
    now = datetime.now(timezone.utc).isoformat()
    for proposal in instance.economy.get("proposals", []):
        if not isinstance(proposal, dict) or proposal.get("status") != "pending":
            continue
        participant_uids = {
            str(proposal.get("payer_uid") or proposal.get("uid") or ""),
            str(proposal.get("recipient_uid") or ""),
            *(
                str(item.get("uid") or "")
                for item in (proposal.get("contributors") or [])
                if isinstance(item, dict)
            ),
        }
        if uid not in participant_uids:
            continue
        proposal["status"] = "cancelled"
        proposal["resolved_at"] = now
        proposal["resolution_code"] = resolution_code
        proposal_id = str(proposal.get("id") or "")
        affected_ids.add(proposal_id)
        _advance_revision(instance)
        _record_outcome(
            instance,
            proposal,
            status="cancelled",
            actor_uid="system",
        )
        _settle_effect_group(instance, proposal)
    instance.pending_payments = [
        item for item in instance.pending_payments
        if str(item.get("id") or "") not in affected_ids
    ]
    return affected_ids


def pending_proposals(instance: Any) -> list[dict[str, Any]]:
    economy = getattr(instance, "economy", {})
    proposals = economy.get("proposals") if isinstance(economy, dict) else []
    return [
        item for item in (proposals or [])
        if (
            isinstance(item, dict)
            and item.get("status") == "pending"
            and item.get("run_id") == getattr(instance, "run_id", "")
        )
    ]


def pending_economy_proposals(instance: Any) -> list[dict[str, Any]]:
    """Return every pending proposal, including legacy payment projections.

    Legacy saves may still carry entries only in ``pending_payments``.  They
    intentionally remain visible to the policy layer and are treated as
    blocking when their semantics cannot be proven safe.
    """

    proposals = pending_proposals(instance)
    known_ids = {str(item.get("id") or "") for item in proposals}
    for item in (getattr(instance, "pending_payments", []) or []):
        if not isinstance(item, dict) or item.get("status") != "pending":
            continue
        proposal_id = str(item.get("id") or "")
        if proposal_id and proposal_id not in known_ids:
            proposals.append(item)
            known_ids.add(proposal_id)
    return proposals


def is_nonblocking_personal_purchase(
    instance: Any,
    proposal: dict[str, Any],
) -> bool:
    """Whether a purchase is safe to leave pending while the table continues.

    This is deliberately a narrow, fail-closed classification.  Only a
    payer-approved purchase that grants an item to that same payer and has no
    deferred narrative/external effect may cross a round boundary.
    """

    if not isinstance(proposal, dict):
        return False
    if proposal.get("status") != "pending" or proposal.get("run_id") != instance.run_id:
        return False
    if str(proposal.get("kind") or "") != "purchase":
        return False
    if str(proposal.get("approval_policy") or "") != "payer":
        return False
    payer_uid = str(proposal.get("payer_uid") or proposal.get("uid") or "")
    recipient_uid = str(proposal.get("recipient_uid") or payer_uid)
    if not payer_uid or recipient_uid != payer_uid:
        return False
    contributors = proposal.get("contributors")
    if contributors:
        return False
    rewards = proposal.get("rewards")
    if not isinstance(rewards, list) or not rewards:
        return False
    if str(proposal.get("effect_group_id") or ""):
        return False
    # These fields indicate a transaction-dependent result.  Unknown fields
    # are not rejected, but any known external/deferred payload fails closed.
    for key in (
        "deferred_effects", "memory_delta", "scene_image_prompt",
        "quest", "plot", "private_info", "quick_actions", "narrative_effects",
    ):
        if proposal.get(key):
            return False
    return True


def blocking_economy_proposals(instance: Any) -> list[dict[str, Any]]:
    """Return pending proposals that must hold the narrative barrier."""

    return [
        proposal for proposal in pending_economy_proposals(instance)
        if not is_nonblocking_personal_purchase(instance, proposal)
    ]


def pending_effect_groups(instance: Any) -> list[dict[str, Any]]:
    """Return unresolved effect groups owned by the current run."""

    economy = getattr(instance, "economy", {})
    groups = economy.get("effect_groups") if isinstance(economy, dict) else []
    return [
        item for item in (groups or [])
        if (
            isinstance(item, dict)
            and item.get("status") in {"pending", "ready"}
            and item.get("run_id") == getattr(instance, "run_id", "")
        )
    ]


def has_pending_economy_decision(instance: Any) -> bool:
    """Whether any economy decision remains unresolved (compatibility API)."""

    return bool(
        pending_economy_proposals(instance)
        or pending_effect_groups(instance)
        or pending_memory_deliveries(instance)
        or pending_memory_reversals(instance)
    )


def has_blocking_economy_decision(instance: Any) -> bool:
    """Whether unresolved economy state must stop narrative progression."""

    return bool(
        blocking_economy_proposals(instance)
        or pending_effect_groups(instance)
        or pending_memory_deliveries(instance)
        or pending_memory_reversals(instance)
    )


def _existing_by_source(instance: Any, source_ref: str) -> dict[str, Any] | None:
    if not source_ref:
        return None
    economy = instance.economy
    record_id = economy.get("idempotency_records", {}).get(source_ref)
    for proposal in economy.get("proposals", []):
        if (
            proposal.get("status") not in {"reversed", "superseded"}
            and (proposal.get("id") == record_id or proposal.get("source_ref") == source_ref)
        ):
            return proposal
    return None


def queue_proposal(
    instance: Any,
    *,
    kind: str,
    amount: int,
    payer_uid: str = "",
    recipient_uid: str = "",
    reason: str = "",
    source: str = "narrative",
    source_ref: str = "",
    approval_policy: str = "payer",
    rewards: list[dict[str, Any]] | None = None,
    contributors: list[dict[str, Any]] | None = None,
    visibility: str = "private",
) -> dict[str, Any]:
    """Queue one idempotent proposal; no balance is changed here."""

    amount = int(amount)
    if not 0 < amount <= MAX_ECONOMY_AMOUNT:
        raise ValueError("economy amount is out of range")
    if kind not in ECONOMY_KINDS:
        raise ValueError("unsupported economy proposal kind")
    if approval_policy not in APPROVAL_POLICIES:
        raise ValueError("unsupported economy approval policy")
    normalized_contributors = deepcopy(list(contributors or []))
    if approval_policy == "all_contributors":
        contributor_uids = [
            str(item.get("uid") or "")
            for item in normalized_contributors
            if isinstance(item, dict)
        ]
        contributor_amounts = [
            int(item.get("amount", 0) or 0)
            for item in normalized_contributors
            if isinstance(item, dict)
        ]
        if (
            not contributor_uids
            or any(not uid for uid in contributor_uids)
            or len(set(contributor_uids)) != len(contributor_uids)
            or any(value <= 0 for value in contributor_amounts)
            or sum(contributor_amounts) != amount
        ):
            raise ValueError("contributors must uniquely cover the proposal amount")
    existing = _existing_by_source(instance, source_ref)
    if existing is not None:
        return existing
    economy = instance.economy
    sequence = int(economy.get("next_sequence", 1) or 1)
    proposal = {
        "id": f"eco_{uuid4().hex}",
        "run_id": instance.run_id,
        "sequence": sequence,
        "kind": str(kind),
        "payer_uid": str(payer_uid),
        "recipient_uid": str(recipient_uid),
        "uid": str(payer_uid or recipient_uid),  # legacy payment projection
        "amount": amount,
        "reason": str(reason or "经济提案")[:240],
        "source": str(source),
        "source_ref": str(source_ref),
        "approval_policy": str(approval_policy),
        "rewards": deepcopy(list(rewards or [])),
        "contributors": normalized_contributors,
        "approvals": {},
        "visibility": visibility if visibility in {"private", "party"} else "private",
        "status": "pending",
        "round": int(getattr(instance, "round_number", 0) or 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    economy.setdefault("proposals", []).append(proposal)
    economy["next_sequence"] = sequence + 1
    if source_ref:
        economy.setdefault("idempotency_records", {})[source_ref] = proposal["id"]
    if kind in {"payment", "purchase", "fee"}:
        instance.pending_payments.append(proposal)
    return proposal


def import_legacy_payment(instance: Any, payment: dict[str, Any]) -> dict[str, Any]:
    """Adopt a legacy pending payment at the compatibility boundary."""

    existing = next(
        (item for item in instance.economy.get("proposals", []) if item.get("id") == payment.get("id")),
        None,
    )
    if existing is not None:
        return existing
    proposal = {
        **deepcopy(payment),
        "id": str(payment.get("id") or f"eco_{uuid4().hex}"),
        "run_id": instance.run_id,
        "sequence": int(instance.economy.get("next_sequence", 1) or 1),
        "kind": "payment",
        "payer_uid": str(payment.get("uid") or ""),
        "approval_policy": "payer_or_gm_legacy",
        "source": "legacy",
        "source_ref": "",
        "visibility": "private",
        "status": "pending",
    }
    instance.economy.setdefault("proposals", []).append(proposal)
    instance.economy["next_sequence"] = proposal["sequence"] + 1
    return proposal


def resolve_proposal(
    instance: Any,
    proposal_id: str,
    *,
    actor_uid: str,
    accepted: bool,
    grant_reward: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Resolve one proposal. Caller must hold the aggregate lock and persist."""

    proposal = next(
        (item for item in instance.economy.get("proposals", []) if item.get("id") == proposal_id),
        None,
    )
    if proposal is None:
        legacy = next(
            (item for item in instance.pending_payments if item.get("id") == proposal_id),
            None,
        )
        if legacy is not None:
            proposal = import_legacy_payment(instance, legacy)
    if proposal is None:
        return {"ok": False, "code": "PROPOSAL_NOT_FOUND", "error": "经济提案不存在"}
    if proposal.get("run_id") != instance.run_id:
        return {"ok": False, "code": "STALE_RUN", "error": "这是上一局的经济请求"}
    if proposal.get("status") != "pending":
        return {"ok": False, "code": "ALREADY_RESOLVED", "error": "经济提案已处理"}

    kind = str(proposal.get("kind") or "payment")
    payer_uid = str(proposal.get("payer_uid") or proposal.get("uid") or "")
    recipient_uid = str(proposal.get("recipient_uid") or payer_uid)
    policy = str(proposal.get("approval_policy") or "payer")
    is_gm = actor_uid == instance.gm_uid
    contributors = [
        item for item in (proposal.get("contributors") or [])
        if isinstance(item, dict) and str(item.get("uid") or "")
    ]
    contributor_uids = {str(item.get("uid") or "") for item in contributors}
    if policy == "all_contributors":
        allowed = actor_uid in contributor_uids or (not accepted and is_gm)
    elif policy == "gm":
        allowed = is_gm
    elif policy == "system":
        allowed = actor_uid == "system"
    elif policy == "payer_or_gm_legacy":
        allowed = actor_uid in {payer_uid, instance.gm_uid}
    else:
        allowed = actor_uid == payer_uid or (not accepted and is_gm)
    if not allowed:
        return {"ok": False, "code": "FORBIDDEN", "error": "无权处理这项经济提案"}

    now = datetime.now(timezone.utc).isoformat()
    if not accepted:
        proposal["status"] = "cancelled" if is_gm and actor_uid != payer_uid else "declined"
        proposal["resolved_at"] = now
        instance.pending_payments = [
            item for item in instance.pending_payments if item.get("id") != proposal_id
        ]
        _advance_revision(instance)
        outcome = _record_outcome(
            instance, proposal, status=str(proposal["status"]), actor_uid=actor_uid,
        )
        _settle_effect_group(instance, proposal)
        return {
            "ok": True,
            "accepted": False,
            "proposal": deepcopy(proposal),
            "outcome": deepcopy(outcome),
        }

    if policy == "all_contributors":
        approvals = proposal.setdefault("approvals", {})
        approvals[actor_uid] = True
        missing = sorted(contributor_uids.difference(
            uid for uid, approved in approvals.items() if approved
        ))
        if missing:
            _advance_revision(instance)
            return {
                "ok": True,
                "accepted": True,
                "committed": False,
                "awaiting_uids": missing,
                "proposal": deepcopy(proposal),
            }

    amount = int(proposal.get("amount", 0) or 0)
    if not 0 < amount <= MAX_ECONOMY_AMOUNT:
        return {"ok": False, "code": "INVALID_AMOUNT", "error": "经济金额无效"}
    entries: list[dict[str, Any]] = []
    if policy == "all_contributors":
        balances: dict[str, int] = {}
        for contribution in contributors:
            uid = str(contribution.get("uid") or "")
            contribution_amount = int(contribution.get("amount", 0) or 0)
            if uid not in instance.players or contribution_amount <= 0:
                return {"ok": False, "code": "CONTRIBUTOR_INVALID", "error": "平摊参与者无效"}
            sheet = instance.get_character_sheet(uid)
            currency = sheet.get("currency") if isinstance(sheet.get("currency"), dict) else {}
            balances[uid] = int(currency.get("amount", sheet.get("gold", 0)) or 0)
            if balances[uid] < contribution_amount:
                proposal["status"] = "rejected"
                proposal["resolved_at"] = now
                instance.pending_payments = [
                    item for item in instance.pending_payments
                    if item.get("id") != proposal_id
                ]
                _advance_revision(instance)
                outcome = _record_outcome(
                    instance, proposal, status="rejected", actor_uid=actor_uid,
                )
                _settle_effect_group(instance, proposal)
                return {
                    "ok": False,
                    "code": "INSUFFICIENT_FUNDS",
                    "error": f"{uid} 余额不足",
                    "proposal": deepcopy(proposal),
                    "outcome": deepcopy(outcome),
                }
        for contribution in contributors:
            uid = str(contribution.get("uid") or "")
            contribution_amount = int(contribution.get("amount", 0) or 0)
            sheet = instance.get_character_sheet(uid)
            after = apply_currency_delta(sheet, -contribution_amount)
            instance.set_character_sheet(uid, sheet)
            entries.append({
                "account": f"character:{uid}",
                "delta": -contribution_amount,
                "before": balances[uid],
                "after": after,
            })
        entries.append({
            "account": "system:world",
            "delta": amount,
            "before": None,
            "after": None,
        })
    elif kind in {"payment", "purchase", "fee", "transfer"}:
        if payer_uid not in instance.players:
            return {"ok": False, "code": "PAYER_NOT_FOUND", "error": "付款角色不存在"}
        rewards = list(proposal.get("rewards") or [])
        if (rewards or kind == "transfer") and recipient_uid not in instance.players:
            return {"ok": False, "code": "RECIPIENT_NOT_FOUND", "error": "物品接收角色不存在"}
        payer = instance.get_character_sheet(payer_uid)
        currency = payer.get("currency") if isinstance(payer.get("currency"), dict) else {}
        current = int(currency.get("amount", payer.get("gold", 0)) or 0)
        if current < amount:
            proposal["status"] = "rejected"
            proposal["resolved_at"] = now
            instance.pending_payments = [
                item for item in instance.pending_payments if item.get("id") != proposal_id
            ]
            _advance_revision(instance)
            outcome = _record_outcome(
                instance, proposal, status="rejected", actor_uid=actor_uid,
            )
            _settle_effect_group(instance, proposal)
            return {
                "ok": False,
                "code": "INSUFFICIENT_FUNDS",
                "error": f"余额不足：需要 {amount}，当前 {current}",
                "proposal": deepcopy(proposal),
                "outcome": deepcopy(outcome),
            }
        before = current
        after = apply_currency_delta(payer, -amount)
        instance.set_character_sheet(payer_uid, payer)
        entries.append({"account": f"character:{payer_uid}", "delta": -amount, "before": before, "after": after})
        if kind == "transfer":
            recipient = instance.get_character_sheet(recipient_uid)
            recipient_currency = (
                recipient.get("currency")
                if isinstance(recipient.get("currency"), dict)
                else {}
            )
            recipient_before = int(
                recipient_currency.get("amount", recipient.get("gold", 0)) or 0
            )
            recipient_after = apply_currency_delta(recipient, amount)
            instance.set_character_sheet(recipient_uid, recipient)
            entries.append({
                "account": f"character:{recipient_uid}",
                "delta": amount,
                "before": recipient_before,
                "after": recipient_after,
            })
        else:
            entries.append({
                "account": "system:world",
                "delta": amount,
                "before": None,
                "after": None,
            })
        if rewards and grant_reward:
            recipient = instance.get_character_sheet(recipient_uid)
            for reward in rewards:
                grant_reward(recipient, reward)
            instance.set_character_sheet(recipient_uid, recipient)
    elif kind == "reward":
        if recipient_uid not in instance.players:
            return {"ok": False, "code": "RECIPIENT_NOT_FOUND", "error": "奖励角色不存在"}
        recipient = instance.get_character_sheet(recipient_uid)
        currency = recipient.get("currency") if isinstance(recipient.get("currency"), dict) else {}
        before = int(currency.get("amount", recipient.get("gold", 0)) or 0)
        after = apply_currency_delta(recipient, amount)
        instance.set_character_sheet(recipient_uid, recipient)
        entries.append({"account": f"character:{recipient_uid}", "delta": amount, "before": before, "after": after})
        entries.append({
            "account": "system:world",
            "delta": -amount,
            "before": None,
            "after": None,
        })
    else:
        return {"ok": False, "code": "UNSUPPORTED_KIND", "error": "不支持的经济提案类型"}

    proposal["status"] = "committed"
    proposal["resolved_at"] = now
    transaction = {
        "id": f"tx_{uuid4().hex}",
        "run_id": instance.run_id,
        "proposal_id": proposal["id"],
        "kind": kind,
        "source": proposal.get("source", ""),
        "source_ref": proposal.get("source_ref", ""),
        "reason": proposal.get("reason", ""),
        "actor_uid": actor_uid,
        "entries": entries,
        "status": "committed",
        "round": int(getattr(instance, "round_number", 0) or 0),
        "committed_at": now,
    }
    instance.economy.setdefault("transactions", []).append(transaction)
    instance.pending_payments = [
        item for item in instance.pending_payments if item.get("id") != proposal_id
    ]
    _advance_revision(instance)
    outcome = _record_outcome(
        instance, proposal, status="committed", actor_uid=actor_uid,
    )
    effect_group = _settle_effect_group(instance, proposal)
    return {
        "ok": True,
        "accepted": True,
        "proposal": deepcopy(proposal),
        "transaction": deepcopy(transaction),
        "outcome": deepcopy(outcome),
        "effect_group": effect_group,
    }


def reverse_round_economy(instance: Any, round_number: int) -> None:
    """Reverse economy effects associated with either round axis.

    ``proposal.round`` is the narrative/origin round, while
    ``transaction.round`` is the actual settlement round.  A late personal
    purchase can therefore need settlement-only rollback (reopen the offer)
    without erasing its origin, while origin rollback must invalidate all
    later settlements of that offer.
    """

    rollback_round = int(round_number)
    proposals = [
        item for item in instance.economy.get("proposals", [])
        if isinstance(item, dict)
    ]
    origin_ids = {
        str(proposal.get("id") or "")
        for proposal in proposals
        if int(proposal.get("round", -1) or -1) == rollback_round
    }
    transactions = [
        item for item in instance.economy.get("transactions", [])
        if isinstance(item, dict)
    ]
    settlement_transactions = [
        transaction for transaction in transactions
        if transaction.get("status") == "committed"
        and int(transaction.get("round", -1) or -1) == rollback_round
    ]
    settlement_ids = {
        str(transaction.get("proposal_id") or "")
        for transaction in settlement_transactions
    }
    affected_ids = origin_ids | settlement_ids
    now = datetime.now(timezone.utc).isoformat()

    # Invalidate proposals whose narrative origin was erased, then reverse
    # every committed settlement linked to those proposals (even if it was
    # paid in a later round).
    for proposal in proposals:
        proposal_id = str(proposal.get("id") or "")
        if proposal_id not in origin_ids:
            continue
        if proposal.get("status") == "committed":
            proposal["status"] = "reversed"
        elif proposal.get("status") == "pending":
            proposal["status"] = "superseded"
        proposal.pop("resolved_at", None)
        source_ref = str(proposal.get("source_ref") or "")
        if source_ref:
            instance.economy.get("idempotency_records", {}).pop(source_ref, None)

    for transaction in transactions:
        if (
            transaction.get("status") == "committed"
            and str(transaction.get("proposal_id") or "") in affected_ids
        ):
            transaction["status"] = "reversed"
            transaction["reversed_at"] = now

    # A settlement-only rollback keeps an earlier valid offer actionable. Do
    # not resurrect proposals whose origin round is itself being erased.
    for proposal in proposals:
        proposal_id = str(proposal.get("id") or "")
        if proposal_id not in settlement_ids or proposal_id in origin_ids:
            continue
        if proposal.get("status") == "committed" and proposal.get("run_id") == instance.run_id:
            proposal["status"] = "pending"
            proposal.pop("resolved_at", None)
            proposal.pop("resolution_code", None)
            if str(proposal.get("kind") or "payment") in {"payment", "purchase", "fee"}:
                if not any(
                    isinstance(item, dict) and str(item.get("id") or "") == proposal_id
                    for item in instance.pending_payments
                ):
                    instance.pending_payments.append(proposal)

    # Remove compatibility projections for erased origins, but retain reopened
    # settlement-only proposals.  This also avoids duplicate pending entries.
    pending: list[dict[str, Any]] = []
    seen_pending: set[str] = set()
    for item in instance.pending_payments:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if item_id in origin_ids or item.get("status") != "pending":
            continue
        if item_id and item_id in seen_pending:
            continue
        if item_id:
            seen_pending.add(item_id)
        pending.append(item)
    instance.pending_payments = pending
    for group in instance.economy.get("effect_groups", []):
        if int(group.get("round", -1) or -1) == int(round_number):
            group["status"] = "superseded"
            group.pop("effects", None)
    for delivery in instance.economy.get("external_effects_outbox", []):
        if int(delivery.get("round", -1) or -1) != int(round_number):
            continue
        if delivery.get("status") == "pending":
            delivery["status"] = "superseded"
            delivery.pop("payload", None)
        elif delivery.get("status") == "delivered":
            delivery["status"] = "reversal_pending"
            delivery["reversal_requested_at"] = datetime.now(timezone.utc).isoformat()
    instance.economy["outcomes"] = [
        item for item in instance.economy.get("outcomes", [])
        if not (
            isinstance(item, dict)
            and (
                str(item.get("proposal_id") or "") in origin_ids
                or (
                    str(item.get("proposal_id") or "") in settlement_ids
                    and (
                        int(item.get("resolved_round", item.get("round", -1)) or -1) == rollback_round
                        or str(item.get("status") or "") == "committed"
                    )
                )
            )
        )
    ]
    _advance_revision(instance)
