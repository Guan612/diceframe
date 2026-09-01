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


def pending_proposals(instance: Any) -> list[dict[str, Any]]:
    economy = getattr(instance, "economy", {})
    proposals = economy.get("proposals") if isinstance(economy, dict) else []
    return [
        item for item in (proposals or [])
        if isinstance(item, dict) and item.get("status") == "pending"
    ]


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
        return {"ok": True, "accepted": False, "proposal": deepcopy(proposal)}

    if policy == "all_contributors":
        approvals = proposal.setdefault("approvals", {})
        approvals[actor_uid] = True
        missing = sorted(contributor_uids.difference(
            uid for uid, approved in approvals.items() if approved
        ))
        if missing:
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
                return {"ok": False, "code": "INSUFFICIENT_FUNDS", "error": f"{uid} 余额不足"}
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
            return {"ok": False, "code": "INSUFFICIENT_FUNDS", "error": f"余额不足：需要 {amount}，当前 {current}"}
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
    return {
        "ok": True,
        "accepted": True,
        "proposal": deepcopy(proposal),
        "transaction": deepcopy(transaction),
    }


def reverse_round_economy(instance: Any, round_number: int) -> None:
    """Invalidate proposal effects restored by a round snapshot rollback."""

    proposal_ids: set[str] = set()
    for proposal in instance.economy.get("proposals", []):
        if int(proposal.get("round", -1) or -1) != int(round_number):
            continue
        proposal_ids.add(str(proposal.get("id") or ""))
        if proposal.get("status") == "committed":
            proposal["status"] = "reversed"
        elif proposal.get("status") == "pending":
            proposal["status"] = "superseded"
        source_ref = str(proposal.get("source_ref") or "")
        if source_ref:
            instance.economy.get("idempotency_records", {}).pop(source_ref, None)
    for transaction in instance.economy.get("transactions", []):
        if str(transaction.get("proposal_id") or "") in proposal_ids and transaction.get("status") == "committed":
            transaction["status"] = "reversed"
            transaction["reversed_at"] = datetime.now(timezone.utc).isoformat()
    instance.pending_payments = [
        item for item in instance.pending_payments
        if int(item.get("round", -1) or -1) != int(round_number)
    ]
