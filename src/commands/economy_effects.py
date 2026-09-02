"""Bridge narrative proposals to authoritative economic decisions.

The LLM may describe and propose a transaction, but state changes which depend
on that transaction must not become authoritative until the decision commits.
This module extracts those effects from one parsed response.  The command
orchestrator owns applying them later; the engine economy owns their persisted
decision group.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any, Iterable
from uuid import uuid4

from src.engine.language import localized_text

_MAX_PURCHASE_QUOTE_HISTORY = 24
_MAX_MERCHANT_OFFER_HISTORY = 24
_MAX_CLARIFICATION_HISTORY = 24

# Price evidence ladder for repair: the seller's persisted quote outranks the
# current narration, which outranks the acting player's own stated amount.
AMOUNT_SOURCE_NARRATION = "narration"
AMOUNT_SOURCE_PLAYER_ACTION = "player_action"
AMOUNT_SOURCE_MERCHANT_OFFER = "merchant_offer"

_ECONOMY_STATE_KEYS = {"pending_payments", "economy_proposals", "merchant_offers"}
_DEFERRED_DATA_KEYS = {
    "confirmed",
    "growth_skills",
    "info_asymmetry",
    "memory_delta",
    "milestone_grants",
    "plot_update",
    "quick_actions",
    "scene_image_prompt",
    "xp_rewards",
}

_CONDITIONAL_REWARD_RE = re.compile(
    r"(?:要是|如果|若是|完成[^。！？\n]{0,20}后|之后再|等你|待你|才能|才会|以后|将会|承诺|答应|promise|promises|will pay|\bif\b|\bonce\b|\bafter\b|\bwhen\b|\u3067\u304d\u305f\u3089|\u7d42\u308f\u3063\u305f\u3089)",
    re.IGNORECASE,
)
_COMPLETION_EVIDENCE_RE = re.compile(
    r"(?:完成|成功|击败|打倒|交付|归还|回收|达成|兑现|领取|earned|completed|complete|defeated|delivered|recovered|claimed|critical success|大成功)",
    re.IGNORECASE,
)
_PURCHASE_INTENT_RE = re.compile(
    r"(?:买下|买了|购买|购入|买入|付费|支付|缴纳|花费|订购|租用|换购|purchase|buy|bought|pay|paid|spend)",
    re.IGNORECASE,
)
_FREE_PURCHASE_RE = re.compile(r"(?:免费|无需付费|不用钱|免费领取|free|no charge)", re.IGNORECASE)
_PURCHASE_CONFIRM_RE = re.compile(
    r"(?:成交|买了|买下|购买|确认购买|接受报价|就要这个|行|可以|同意|付钱|结账|"
    r"deal|accept|accepted|confirm|confirmed|buy it|take it|pay|yes|"
    r"成約|購入|承知|支払う|了解です|はい|了承)", re.IGNORECASE,
)
_PURCHASE_OFFER_RE = re.compile(
    r"(?:需要|需|售价|价格|费用|收费|cost|price|charge)", re.IGNORECASE,
)
def _currency_labels(currency_labels: Iterable[str] | None = None) -> tuple[str, ...]:
    """Return canonical rule labels plus legacy aliases for text recognition.

    Narrative parsing is only a repair/fail-closed guard; the persisted
    currency schema remains authoritative.  Rule-provided labels let the same
    guard work for custom economies (USD, credits, gems, etc.) without adding
    ruleset branches to the generic engine.
    """

    labels = {
        "金币", "金子", "金", "gold", "credits", "credit", "dollars", "dollar",
    }
    for label in currency_labels or ():
        value = str(label or "").strip()
        if value:
            labels.add(value)
    return tuple(sorted(labels, key=len, reverse=True))


def currency_labels_for_rule(rule: Any) -> tuple[str, ...]:
    """Project declared rule currency IDs/names into the generic text guard."""

    system = getattr(rule, "currency_system", None)
    if not isinstance(system, dict) and isinstance(rule, dict):
        system = rule.get("currency_system")
    units = system.get("units", []) if isinstance(system, dict) else []
    labels: list[str] = []
    if isinstance(units, list):
        for unit in units:
            if isinstance(unit, dict):
                labels.extend(
                    str(unit.get(key) or "").strip()
                    for key in ("id", "name", "label")
                    if str(unit.get(key) or "").strip()
                )
    return _currency_labels(labels)


def _currency_amount_pattern(currency_labels: Iterable[str] | None = None) -> re.Pattern[str]:
    labels = "|".join(re.escape(label) for label in _currency_labels(currency_labels))
    return re.compile(
        rf"(?P<amount>[0-9]+|[零〇一二三四五六七八九十百千万两]+)"
        rf"\s*(?:枚|个)?\s*(?:{labels})",
        re.IGNORECASE,
    )


def _charge_pattern(currency_labels: Iterable[str] | None = None) -> re.Pattern[str]:
    labels = "|".join(re.escape(label) for label in _currency_labels(currency_labels))
    return re.compile(
        rf"(?:需要|需|必须|须|售价|价格|费用|收费|支付|付费|购买|买下|花费|缴纳|"
        rf"cost|price|charge|pay|purchase|spend)[^。！？\n]{{0,24}}?"
        rf"(?:[一二三四五六七八九十百千万两\d]+)\s*(?:枚|个)?\s*(?:{labels})"
        rf"|(?:[一二三四五六七八九十百千万两\d]+)\s*(?:{labels})"
        rf"[^。！？\n]{{0,16}}?"
        rf"(?:需要|需|支付|付费|购买|买下|花费|缴纳|cost|price|charge|pay|purchase|spend)",
        re.IGNORECASE,
    )


def _completed_payment_pattern(currency_labels: Iterable[str] | None = None) -> re.Pattern[str]:
    labels = "|".join(re.escape(label) for label in _currency_labels(currency_labels))
    return re.compile(
        rf"(?:掏出|拿出|数出|数了|递出|放下|交出|付出|支付了?|缴纳了?|付清|花费了?)\s*"
        rf"(?:[一二三四五六七八九十百千万两\d]+)\s*(?:枚|个)?\s*(?:{labels})"
        rf"|(?:paid|spent|handed over|paid out)\s+"
        rf"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:{labels})",
        re.IGNORECASE,
    )


def _chinese_amount(value: str) -> int | None:
    """Parse the small Chinese numerals commonly used in narrative prices."""

    if value.isdigit():
        return int(value)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    total = 0
    section = 0
    number = 0
    for char in value:
        if char in digits:
            number = digits[char]
        elif char in units:
            unit = units[char]
            if unit == 10000:
                section = (section + number) * unit
                total += section
                section = 0
            else:
                section += (number or 1) * unit
            number = 0
        else:
            return None
    return total + section + number


def _currency_amounts(
    narration: str,
    currency_labels: Iterable[str] | None = None,
) -> list[int]:
    amounts: list[int] = []
    for match in _currency_amount_pattern(currency_labels).finditer(str(narration or "")):
        amount = _chinese_amount(match.group("amount"))
        if amount is not None and amount > 0:
            amounts.append(amount)
    return amounts


def repair_unbacked_purchase(
    instance: Any,
    data: dict[str, Any],
    narration: str,
    *,
    actions: Iterable[dict[str, Any]] | None = None,
    currency_labels: Iterable[str] | None = None,
) -> tuple[int, bool]:
    """Bind an explicit purchase to an economy proposal before state apply.

    Item tags are intentionally independent from payment tags for ordinary
    loot, but that old shape allowed a model to emit ``EQUIP`` for a purchase
    while omitting ``PAY``.  The server now uses the player's explicit purchase
    intent plus one unambiguous currency amount to synthesize the same typed
    purchase proposal.  Ambiguous prices fail closed and suppress the grant.
    """

    state_update = data.get("state_update")
    if not isinstance(state_update, dict) or has_economy_proposal(data):
        return 0, False
    action_records = list(actions) if actions is not None else list(getattr(instance, "action_queue", []))
    action_text = "\n".join(
        str(action.get("text") or "")
        for action in action_records
        if isinstance(action, dict)
    )
    narrative_text = str(narration or "")
    explicit_purchase = bool(_PURCHASE_INTENT_RE.search(action_text))
    charge_re = _charge_pattern(currency_labels)
    completed_payment_re = _completed_payment_pattern(currency_labels)
    priced_narrative = bool(charge_re.search(narrative_text) or completed_payment_re.search(narrative_text))
    if not explicit_purchase and not priced_narrative:
        return 0, False
    actor_uids = {
        str(action.get("user_id") or "")
        for action in action_records
        if isinstance(action, dict)
        and str(action.get("user_id") or "") in getattr(instance, "players", {})
        and _PURCHASE_INTENT_RE.search(str(action.get("text") or ""))
    }

    grants: list[tuple[str, str]] = []
    players_update = state_update.get("players")
    if isinstance(players_update, dict):
        for uid, update in players_update.items():
            if not isinstance(update, dict):
                continue
            for key in ("equip_gain", "weapon_change"):
                item = str(update.get(key) or "").strip()
                if item:
                    grants.append((str(uid), item))
    loot = state_update.get("loot")
    if isinstance(loot, list):
        for item in loot:
            if isinstance(item, dict):
                uid = str(item.get("player") or "")
                name = str(item.get("item") or "").strip()
                if uid and name:
                    grants.append((uid, name))
    if not grants:
        # An explicit purchase intent whose sale the model narrated without any
        # structured grant cannot bind an item or a seller acceptance.  Keep
        # the intent as a clarification instead of silently dropping it.
        if explicit_purchase and priced_narrative:
            record_purchase_clarification(
                instance,
                reason="MISSING_SELLER_PRICE_CONFIRMATION",
                payer_uid=next(iter(actor_uids)) if len(actor_uids) == 1 else "",
                amount_candidates=_currency_amounts(narrative_text, currency_labels),
            )
        return 0, False
    if _FREE_PURCHASE_RE.search(narrative_text) and not priced_narrative:
        return 0, False

    # Bind only grants named by the purchase context.  If the narration does
    # not name an item (legacy responses), retain the conservative behavior of
    # treating all grants for the sole payer as transaction-bound.
    context_text = f"{action_text}\n{narrative_text}"
    named_grants = [
        grant for grant in grants
        if grant[1].casefold() in context_text.casefold()
    ]
    bound_grants = named_grants or grants

    amounts = _currency_amounts(narrative_text, currency_labels)
    grant_uids = {uid for uid, _item in bound_grants}
    payer_candidates = actor_uids & grant_uids

    def _drop_bound_grants() -> None:
        if isinstance(players_update, dict):
            for update in players_update.values():
                if isinstance(update, dict):
                    update.pop("equip_gain", None)
                    update.pop("weapon_change", None)
        if isinstance(loot, list):
            state_update["loot"] = []

    # Price evidence ladder: the seller's narration is the primary source; the
    # acting player's own stated amount only fills a missing price field.  A
    # player amount is evidence, never an override of a seller quote.
    amount = 0
    amount_source = ""
    if len(amounts) == 1:
        amount, amount_source = amounts[0], AMOUNT_SOURCE_NARRATION
    elif not amounts and len(payer_candidates) == 1:
        payer_uid = next(iter(payer_candidates))
        intent_amounts = [
            parsed
            for action in action_records
            if isinstance(action, dict)
            and str(action.get("user_id") or "") == payer_uid
            and _PURCHASE_INTENT_RE.search(str(action.get("text") or ""))
            for parsed in _currency_amounts(str(action.get("text") or ""), currency_labels)
        ]
        unique_intent_amounts = sorted(set(intent_amounts))
        if len(unique_intent_amounts) == 1:
            amount, amount_source = unique_intent_amounts[0], AMOUNT_SOURCE_PLAYER_ACTION

    if len(payer_candidates) != 1 or not amount or amount > 100_000:
        _drop_bound_grants()
        reason = (
            "AMBIGUOUS_PAYER"
            if len(payer_candidates) > 1
            else "INVALID_AMOUNT"
            if amount > 100_000
            else "AMBIGUOUS_PRICE"
        )
        record_purchase_clarification(
            instance,
            reason=reason,
            payer_uid=next(iter(payer_candidates)) if len(payer_candidates) == 1 else "",
            item_candidates=[item for _uid, item in bound_grants],
            amount_candidates=amounts,
        )
        return len(grants), True
    payer_uid = next(iter(payer_candidates))
    items = [item for uid, item in bound_grants if uid == payer_uid]

    offers = match_open_merchant_offers(instance, items)
    if len(offers) > 1:
        _drop_bound_grants()
        record_purchase_clarification(
            instance,
            reason="AMBIGUOUS_OFFER",
            payer_uid=payer_uid,
            item_candidates=items,
            amount_candidates=[amount],
        )
        return len(grants), True
    if len(offers) == 1:
        offer_amount = int(offers[0].get("amount") or 0)
        if amount != offer_amount:
            _drop_bound_grants()
            record_purchase_clarification(
                instance,
                reason="OFFER_PRICE_CONFLICT",
                payer_uid=payer_uid,
                item_candidates=items,
                amount_candidates=sorted({amount, offer_amount}),
            )
            return len(grants), True
        amount, amount_source = offer_amount, AMOUNT_SOURCE_MERCHANT_OFFER

    proposal = {
        "kind": "purchase",
        "uid": payer_uid,
        "amount": amount,
        "recipient_uid": payer_uid,
        "items": items,
        "reason": f"购买 {'、'.join(items)}",
        "approval_policy": "payer",
        "source": "server_purchase_guard",
        "amount_source": amount_source,
    }
    data.setdefault("state_update", {}).setdefault("economy_proposals", []).append(proposal)
    # The proposal's rewards are the sole authoritative delivery path. Consume
    # only grants bound to this payer/items; unrelated loot remains intact.
    if isinstance(loot, list):
        state_update["loot"] = [
            entry for entry in loot
            if not (
                isinstance(entry, dict)
                and str(entry.get("player") or "") == payer_uid
                and str(entry.get("item") or "").strip() in items
            )
        ]
    if isinstance(players_update, dict):
        for uid, update in players_update.items():
            if str(uid) != payer_uid or not isinstance(update, dict):
                continue
            for key in ("equip_gain", "weapon_change"):
                if str(update.get(key) or "").strip() in items:
                    update.pop(key, None)
    return 0, False


def _meaningful(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_meaningful(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_meaningful(item) for item in value)
    return value not in {None, "", False, 0}


def has_economy_proposal(data: dict[str, Any]) -> bool:
    state_update = data.get("state_update")
    if not isinstance(state_update, dict):
        return False
    return bool(
        state_update.get("pending_payments")
        or state_update.get("economy_proposals")
    )


def has_server_purchase_guard(data: dict[str, Any]) -> bool:
    """Whether this response contains a server-repaired purchase proposal."""

    state_update = data.get("state_update")
    proposals = state_update.get("economy_proposals") if isinstance(state_update, dict) else None
    return isinstance(proposals, list) and any(
        isinstance(proposal, dict) and proposal.get("source") == "server_purchase_guard"
        for proposal in proposals
    )

def _bounded_economy_collection(instance: Any, key: str) -> list[dict[str, Any]]:
    economy = getattr(instance, "economy", None)
    if not isinstance(economy, dict):
        return []
    entries = economy.setdefault(key, [])
    if not isinstance(entries, list):
        economy[key] = []
    return economy[key]


def _trim_open_history(entries: list[dict[str, Any]], *, max_history: int) -> None:
    open_entries = [
        entry for entry in entries
        if isinstance(entry, dict) and entry.get("status") == "open"
    ]
    resolved = [
        entry for entry in entries
        if not (isinstance(entry, dict) and entry.get("status") == "open")
    ]
    budget = max(0, max_history - len(open_entries))
    entries[:] = (resolved[-budget:] if budget else []) + open_entries


def record_merchant_offer(
    instance: Any,
    *,
    item_display: str,
    amount: int,
    seller_id: str = "",
    currency_id: str = "",
) -> dict[str, Any] | None:
    """Persist one world-side merchant offer from a typed payload.

    Offers are world facts, not decisions: they never bind a payer and can
    never settle, charge, or deliver anything.  The amount is the seller's
    statement and stays authoritative — a player-stated price may conflict
    with it, but never overwrite it.
    """

    name = str(item_display or "").strip()[:120]
    try:
        price = int(amount)
    except (TypeError, ValueError):
        return None
    if not name or not 0 < price <= 100_000:
        return None
    offers = _bounded_economy_collection(instance, "merchant_offers")
    for offer in offers:
        if (
            isinstance(offer, dict)
            and offer.get("status") == "open"
            and str(offer.get("item_display") or "") == name
            and (
                not offer.get("run_id")
                or str(offer.get("run_id")) == str(getattr(instance, "run_id", ""))
            )
        ):
            # A persisted seller quote stands until it is resolved or rolled
            # back; a re-narrated identical quote never moves its price.
            return offer
    offer = {
        "id": f"offer_{uuid4().hex}",
        "run_id": str(getattr(instance, "run_id", "")),
        "origin_round": int(getattr(instance, "round_number", 0) or 0),
        "item_display": name,
        "amount": price,
        "currency_id": str(currency_id or "")[:40],
        "seller_id": str(seller_id or "")[:120],
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    offers.append(offer)
    _trim_open_history(offers, max_history=_MAX_MERCHANT_OFFER_HISTORY)
    return offer


def _normalized_item_name(name: str) -> str:
    """Casefolded name without whitespace so decoration variants compare stably."""

    return "".join(str(name or "").split()).casefold()


def match_open_merchant_offers(instance: Any, item_names: Iterable[str]) -> list[dict[str, Any]]:
    """Open offers whose item reference matches a purchase item name.

    Binding requires the purchase name to equal the offer's item reference or
    extend it as a suffix (Chinese variants put modifiers before the head
    noun: "矮人精钢剑" extends "精钢剑").  Bidirectional substring matching is
    deliberately not used — "长剑鞘" must not inherit a "长剑" quote and
    "铁剑碎片" must not inherit "铁剑"; uncertain matches fall through to
    clarification instead of silently inheriting a price.
    """

    names = [_normalized_item_name(name) for name in item_names]
    names = [name for name in names if name]
    if not names:
        return []
    matches: list[dict[str, Any]] = []
    for offer in _bounded_economy_collection(instance, "merchant_offers"):
        if not isinstance(offer, dict) or offer.get("status") != "open":
            continue
        if (
            offer.get("run_id")
            and str(offer.get("run_id")) != str(getattr(instance, "run_id", ""))
        ):
            continue
        display = _normalized_item_name(str(offer.get("item_display") or ""))
        if len(display) < 2:
            continue
        if any(name == display or name.endswith(display) for name in names):
            matches.append(offer)
    return matches


def record_purchase_clarification(
    instance: Any,
    *,
    reason: str,
    payer_uid: str = "",
    item_candidates: Iterable[str] = (),
    amount_candidates: Iterable[int] = (),
) -> dict[str, Any] | None:
    """Persist an unresolvable purchase intent as structured pending state.

    A clarification is a business state, not an error: it can never settle,
    charge, or deliver anything.  It keeps the structure of a failed
    fail-closed binding available for GM/player resolution instead of
    degrading it into a prose-only notice.
    """

    items: list[str] = []
    for candidate in item_candidates:
        name = str(candidate or "").strip()[:120]
        if name and name not in items:
            items.append(name)
    amounts: list[int] = []
    for amount_candidate in amount_candidates:
        try:
            parsed = int(amount_candidate)
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in amounts:
            amounts.append(parsed)
    if not items and not amounts:
        return None
    clarifications = _bounded_economy_collection(instance, "clarifications")
    signature = (
        str(payer_uid or ""), tuple(items), tuple(amounts), str(reason)[:60],
    )
    for entry in clarifications:
        if not isinstance(entry, dict) or entry.get("status") != "open":
            continue
        entry_signature = (
            str(entry.get("payer_uid") or ""),
            tuple(str(item) for item in (entry.get("item_candidates") or [])),
            tuple(int(value) for value in (entry.get("amount_candidates") or [])),
            str(entry.get("reason") or ""),
        )
        if entry_signature == signature:
            return entry
    clarification = {
        "id": f"clarify_{uuid4().hex}",
        "run_id": str(getattr(instance, "run_id", "")),
        "origin_round": int(getattr(instance, "round_number", 0) or 0),
        "payer_uid": str(payer_uid or ""),
        "item_candidates": items,
        "amount_candidates": amounts,
        "reason": str(reason)[:60],
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    clarifications.append(clarification)
    _trim_open_history(clarifications, max_history=_MAX_CLARIFICATION_HISTORY)
    return clarification

def _purchase_quotes(instance: Any) -> list[dict[str, Any]]:
    economy = getattr(instance, "economy", None)
    if not isinstance(economy, dict):
        return []
    quotes = economy.setdefault("purchase_quotes", [])
    if not isinstance(quotes, list):
        economy["purchase_quotes"] = []
    return economy["purchase_quotes"]


def _open_purchase_quote(quotes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the single actionable offer; history entries are not open."""

    open_quotes = [
        quote for quote in quotes
        if isinstance(quote, dict) and quote.get("status", "open") == "open"
    ]
    return open_quotes[0] if len(open_quotes) == 1 else None


def _trim_purchase_quote_history(quotes: list[dict[str, Any]]) -> None:
    open_entries = [
        quote for quote in quotes
        if isinstance(quote, dict) and quote.get("status", "open") == "open"
    ]
    resolved = [
        quote for quote in quotes
        if not (isinstance(quote, dict) and quote.get("status", "open") == "open")
    ]
    budget = max(0, _MAX_PURCHASE_QUOTE_HISTORY - len(open_entries))
    quotes[:] = (resolved[-budget:] if budget else []) + open_entries


def close_purchase_quote(
    instance: Any,
    quote_id: str,
    *,
    status: str,
    resolution_code: str,
) -> dict[str, Any] | None:
    """Retire one persisted offer by id, keeping the audit entry in place."""

    quote = next(
        (
            quote for quote in _purchase_quotes(instance)
            if isinstance(quote, dict) and str(quote.get("id") or "") == str(quote_id)
        ),
        None,
    )
    if quote is None:
        return None
    if quote.get("status", "open") != "open":
        return None
    quote["status"] = status
    quote["resolution_code"] = resolution_code
    quote["resolved_at"] = datetime.now(timezone.utc).isoformat()
    return quote


def link_purchase_quote_proposal(instance: Any, quote_id: str, proposal_id: str) -> None:
    """Record the derived proposal id on the audit copy of a converted offer."""

    if not quote_id or not proposal_id:
        return
    for quote in _purchase_quotes(instance):
        if isinstance(quote, dict) and str(quote.get("id") or "") == str(quote_id):
            quote["proposal_id"] = str(proposal_id)
            return


def settle_purchase_quote(
    instance: Any,
    data: dict[str, Any],
    *,
    currency_labels: Iterable[str] | None = None,
) -> bool:
    """Turn an open quote into a typed proposal when a player confirms it."""

    confirming_uids = {
        str(action.get("user_id") or "")
        for action in getattr(instance, "action_queue", [])
        if isinstance(action, dict)
        and _PURCHASE_CONFIRM_RE.search(str(action.get("text") or ""))
        and str(action.get("user_id") or "")
    }
    if len(confirming_uids) != 1:
        return False
    quotes = _purchase_quotes(instance)
    quote = _open_purchase_quote(quotes)
    if quote is None:
        return False
    payer_uid = str(quote.get("payer_uid") or "")
    if (
        not payer_uid
        or payer_uid not in getattr(instance, "players", {})
        or confirming_uids != {payer_uid}
        or str(quote.get("run_id") or "") != str(getattr(instance, "run_id", ""))
    ):
        return False
    items = [str(item).strip() for item in quote.get("items", []) if str(item).strip()]
    amount = int(quote.get("amount", 0) or 0)
    if amount <= 0 or not items:
        return False
    state_update = data.setdefault("state_update", {})
    # The persisted quote is the only source of truth for purchased goods.
    # Remove any model-repeated copy from ordinary LOOT/EQUIP before the
    # proposal is queued, so confirmation cannot reintroduce double delivery.
    loot = state_update.get("loot")
    if isinstance(loot, list):
        state_update["loot"] = [
            entry for entry in loot
            if not (
                isinstance(entry, dict)
                and str(entry.get("player") or "") == payer_uid
                and str(entry.get("item") or "").strip() in items
            )
        ]
    players_update = state_update.get("players")
    if isinstance(players_update, dict):
        player_update = players_update.get(payer_uid)
        if isinstance(player_update, dict):
            for key in ("equip_gain", "weapon_change"):
                if str(player_update.get(key) or "").strip() in items:
                    player_update.pop(key, None)
    proposals = state_update.setdefault("economy_proposals", [])
    def conflicts_with_quote(proposal: Any) -> bool:
        if not isinstance(proposal, dict) or proposal.get("kind") != "purchase":
            return False
        rewards = proposal.get("rewards")
        if isinstance(rewards, list) and any(
            isinstance(item, dict)
            and str(item.get("name") or item.get("item") or "").strip() in items
            for item in rewards
        ):
            return True
        proposal_items = proposal.get("items")
        return isinstance(proposal_items, list) and any(
            str(item).strip() in items for item in proposal_items
        )

    state_update["economy_proposals"] = [
        proposal for proposal in proposals
        if not conflicts_with_quote(proposal)
    ]
    state_update["economy_proposals"].append({
        "kind": "purchase", "uid": payer_uid, "amount": amount,
        "recipient_uid": str(quote.get("recipient_uid") or payer_uid),
        "items": items, "reason": str(quote.get("reason") or "购买商品"),
        "approval_policy": "payer", "source": "server_purchase_quote",
        # Keep the offer's origin round authoritative after conversion so a
        # rollback of that round can reverse the later settlement.
        "quote_id": str(quote.get("id") or ""),
    })
    # Retire the offer, keeping the audit entry; the queued proposal above is
    # now the only path to settlement.
    quote["status"] = "confirmed"
    quote["resolved_at"] = datetime.now(timezone.utc).isoformat()
    _trim_purchase_quote_history(quotes)
    return True


def record_purchase_quote(
    instance: Any,
    data: dict[str, Any],
    narration: str,
    *,
    currency_labels: Iterable[str] | None = None,
) -> bool:
    """Persist one uncommitted shop quote for a later confirmation turn."""

    if has_economy_proposal(data):
        return False
    state_update = data.get("state_update")
    if not isinstance(state_update, dict):
        return False
    grants: list[tuple[str, str]] = []
    for item in state_update.get("loot", []) if isinstance(state_update.get("loot"), list) else []:
        if isinstance(item, dict) and str(item.get("player") or "").strip() and str(item.get("item") or "").strip():
            grants.append((str(item["player"]), str(item["item"]).strip()))
    players_update = state_update.get("players")
    if isinstance(players_update, dict):
        for uid, update in players_update.items():
            if isinstance(update, dict):
                for key in ("equip_gain", "weapon_change"):
                    if str(update.get(key) or "").strip():
                        grants.append((str(uid), str(update[key]).strip()))
    action_text = "\n".join(
        str(action.get("text") or "")
        for action in getattr(instance, "action_queue", [])
        if isinstance(action, dict)
    )
    amounts = _currency_amounts(narration, currency_labels)
    offer_pattern = _PURCHASE_OFFER_RE
    sentences = re.split(r"[。！？.!?\n]+", str(narration or ""))
    bound_grants = [
        grant for grant in grants
        if any(
            grant[1].casefold() in sentence.casefold()
            and offer_pattern.search(sentence)
            and _currency_amount_pattern(currency_labels).search(sentence)
            for sentence in sentences
        )
        or (
            grant[1].casefold() in action_text.casefold()
            and len(amounts) == 1
            and bool(offer_pattern.search(narration))
        )
    ]
    grant_uids = {uid for uid, _item in bound_grants}
    if (
        len(bound_grants) == 0
        or len(grant_uids) != 1
        or len(amounts) != 1
        or not (
            (
                _PURCHASE_OFFER_RE.search(narration)
                and _currency_amount_pattern(currency_labels).search(narration)
            )
            or _PURCHASE_INTENT_RE.search(action_text)
        )
    ):
        return False
    quotes = _purchase_quotes(instance)
    if any(
        isinstance(quote, dict) and quote.get("status", "open") == "open"
        for quote in quotes
    ):
        # A persisted offer is authoritative until it is confirmed or
        # invalidated by rollback; never replace its amount/items with a
        # later model narration.
        return False
    payer_uid = bound_grants[0][0]
    if payer_uid not in getattr(instance, "players", {}):
        # An offer for a payer outside the current game can never settle.
        return False
    quotes.append({
        "id": f"quote_{uuid4().hex}",
        "run_id": str(getattr(instance, "run_id", "")),
        "round": int(getattr(instance, "round_number", 0) or 0),
        "payer_uid": payer_uid, "recipient_uid": payer_uid,
        "amount": amounts[0], "items": [item for _uid, item in bound_grants],
        "reason": "购买商品", "status": "open",
    })
    _trim_purchase_quote_history(quotes)
    # A quote is only an offer.  Keep its items out of the immediate state
    # update; confirmation will re-create the typed proposal and its deferred
    # effect group.
    bound_pairs = set(bound_grants)
    if isinstance(state_update.get("loot"), list):
        state_update["loot"] = [
            entry for entry in state_update["loot"]
            if not (
                isinstance(entry, dict)
                and (str(entry.get("player") or ""), str(entry.get("item") or "").strip()) in bound_pairs
            )
        ]
    if isinstance(players_update, dict):
        for uid, update in players_update.items():
            if not isinstance(update, dict):
                continue
            for key in ("equip_gain", "weapon_change"):
                if (str(uid), str(update.get(key) or "").strip()) in bound_pairs:
                    update.pop(key, None)
    return True


def discard_unearned_reward_proposals(
    instance: Any,
    data: dict[str, Any],
    narration: str,
) -> int:
    """Drop rewards that are still conditional promises, before queueing them.

    ``GOLD`` is intentionally still a proposal, but a proposal must represent
    an earned event. A common model failure is to emit GOLD while an NPC is
    merely promising payment after a task is completed. Such a reward is kept
    in the prose but cannot enter the authoritative economy until a later turn
    records completion. Explicit same-turn or previously completed quest state
    is accepted as the completion evidence.
    """

    state_update = data.get("state_update")
    if not isinstance(state_update, dict):
        return 0
    proposals = state_update.get("economy_proposals")
    if not isinstance(proposals, list) or not proposals:
        return 0
    rewards = [item for item in proposals if isinstance(item, dict) and item.get("kind") == "reward"]
    narration_text = str(narration or "")
    if not rewards:
        return 0

    completed_titles: set[str] = set()
    plot_update = data.get("plot_update")
    if isinstance(plot_update, dict):
        for quest in plot_update.get("quests", []):
            if isinstance(quest, dict) and str(quest.get("status") or "").casefold() in {"completed", "complete", "已完成", "完成", "成功"}:
                title = str(quest.get("title") or "").strip().casefold()
                if title:
                    completed_titles.add(title)
    tracker = getattr(instance, "plot_tracker", None)
    for quest in getattr(tracker, "quests", {}).values() if tracker is not None else []:
        status = getattr(getattr(quest, "status", None), "value", getattr(quest, "status", ""))
        if str(status).casefold() in {"completed", "complete", "已完成", "完成", "成功"}:
            title = str(getattr(quest, "title", "") or "").strip().casefold()
            if title:
                completed_titles.add(title)

    kept: list[dict[str, Any]] = []
    dropped = 0
    for proposal in proposals:
        if proposal not in rewards:
            kept.append(proposal)
            continue
        reason = str(proposal.get("reason") or "").casefold()
        if any(title in reason or reason in title for title in completed_titles):
            kept.append(proposal)
            continue
        # A reward needs affirmative completion evidence in the same turn. A
        # conditional/promise phrase takes precedence, even if the model also
        # mentions a future payment elsewhere in the paragraph.
        if (
            _COMPLETION_EVIDENCE_RE.search(narration_text)
            and not _CONDITIONAL_REWARD_RE.search(narration_text)
        ):
            kept.append(proposal)
            continue
        dropped += 1
    state_update["economy_proposals"] = kept
    return dropped


def unearned_reward_notice(language: str) -> str:
    return localized_text(language, {
        "en": "Reward pending: the story described a conditional promise, so no reward proposal was created until the task is confirmed complete.",
        "zh-CN": "奖励待确认：当前剧情只是条件性承诺，任务确认完成前不会生成奖励提案。",
        "ja": "報酬保留中：物語が条件付きの約束を示しているため、任務の完了が確認されるまで報酬提案は作成されません。",
    })


def guard_unbacked_payment_narration(
    narration: str,
    data: dict[str, Any],
    language: str,
    *,
    currency_labels: Iterable[str] | None = None,
) -> str:
    """Prevent prose from claiming a completed payment without authority.

    Currency changes are authoritative only through PAY/TEAM_PAY/economy
    proposals.  Models occasionally narrate handing over coins while omitting
    the protocol tag; leave the balance untouched and make that fact explicit
    instead of presenting a false completed transaction to the player.
    """

    text = str(narration or "").strip()
    completed_payment_re = _completed_payment_pattern(currency_labels)
    if not text or has_economy_proposal(data) or not completed_payment_re.search(text):
        return text
    notice = {
        "en": "Authority notice: no payment proposal was created, so no gold was deducted. Ask the GM to issue a payment proposal if this fee should be charged.",
        "zh-CN": "权威账本提示：本次没有生成支付提案，因此未扣除金币。若确实需要收费，请由 GM 重新发起支付提案。",
        "ja": "権威台帳の通知：支払い提案が作成されなかったため、ゴールドは差し引かれていません。請求が必要なら GM に支払い提案を出してもらってください。",
    }.get(str(language or "").lower(), "权威账本提示：本次没有生成支付提案，因此未扣除金币。若确实需要收费，请由 GM 重新发起支付提案。")
    return f"{text}\n\n{notice}"


def discard_unbacked_purchase_items(
    instance: Any,
    data: dict[str, Any],
    narration: str,
    *,
    currency_labels: Iterable[str] | None = None,
) -> int:
    """Fail closed when prose describes a priced purchase without a proposal.

    A model can emit ``LOOT`` while narrating a shop price but omit ``PAY`` /
    ``ECONOMY``.  Granting that loot would make the item authoritative even
    though no payment decision exists.  Drop the transaction-dependent loot;
    the GM can issue a proposal explicitly on a later turn.
    """

    narration_text = str(narration or "")
    charge_re = _charge_pattern(currency_labels)
    completed_payment_re = _completed_payment_pattern(currency_labels)
    if has_economy_proposal(data) or not (charge_re.search(narration_text) or completed_payment_re.search(narration_text)):
        return 0
    state_update = data.get("state_update")
    if not isinstance(state_update, dict):
        return 0
    dropped = 0
    dropped_items: list[str] = []
    loot = state_update.get("loot")
    if isinstance(loot, list) and loot:
        dropped += len(loot)
        dropped_items.extend(
            str(entry.get("item") or "").strip()
            for entry in loot
            if isinstance(entry, dict) and str(entry.get("item") or "").strip()
        )
        state_update["loot"] = []
    players_update = state_update.get("players")
    if isinstance(players_update, dict):
        for player_update in players_update.values():
            if not isinstance(player_update, dict):
                continue
            for key in ("equip_gain", "weapon_change"):
                if key in player_update:
                    dropped += 1
                    name = str(player_update.get(key) or "").strip()
                    if name:
                        dropped_items.append(name)
                    player_update.pop(key, None)
    if dropped:
        record_purchase_clarification(
            instance,
            reason="MISSING_SELLER_PRICE_CONFIRMATION",
            item_candidates=dropped_items,
            amount_candidates=_currency_amounts(narration_text, currency_labels),
        )
    return dropped


def unbacked_purchase_notice(language: str) -> str:
    return localized_text(language, {
        "en": "Purchase items were not granted because no payment proposal was created.",
        "zh-CN": "由于没有生成支付提案，本次购买物品未发放。",
        "ja": "支払い提案が作成されなかったため、購入品は付与されませんでした。",
    })


def defer_narrative_effects(
    data: dict[str, Any],
    response: Any,
    *,
    defer_state_update: bool = True,
) -> dict[str, Any]:
    """Remove decision-dependent effects from the immediate round response."""

    if not has_economy_proposal(data):
        return {}
    state_update = dict(data.get("state_update") or {})
    if not defer_state_update and has_server_purchase_guard(data):
        # A repaired purchase only proves that the purchased item is
        # settlement-dependent.  Keep the explicitly remaining item grants on
        # the normal pipeline, but fail closed for every other state field.
        immediate_state = {
            key: deepcopy(value)
            for key, value in state_update.items()
            if key in _ECONOMY_STATE_KEYS or key == "loot"
        }
        deferred_state = {
            key: deepcopy(value)
            for key, value in state_update.items()
            if key not in _ECONOMY_STATE_KEYS and key != "loot" and _meaningful(value)
        }
        players = state_update.get("players")
        if isinstance(players, dict):
            immediate_players: dict[str, dict[str, Any]] = {}
            deferred_players: dict[str, dict[str, Any]] = {}
            for uid, raw_update in players.items():
                if not isinstance(raw_update, dict):
                    if _meaningful(raw_update):
                        deferred_players[str(uid)] = deepcopy(raw_update)
                    continue
                immediate_update = {
                    key: deepcopy(value)
                    for key, value in raw_update.items()
                    if key in {"equip_gain", "weapon_change"} and _meaningful(value)
                }
                deferred_update = {
                    key: deepcopy(value)
                    for key, value in raw_update.items()
                    if key not in {"equip_gain", "weapon_change"} and _meaningful(value)
                }
                if immediate_update:
                    immediate_players[str(uid)] = immediate_update
                if deferred_update:
                    deferred_players[str(uid)] = deferred_update
            if immediate_players:
                immediate_state["players"] = immediate_players
            else:
                immediate_state.pop("players", None)
            if deferred_players:
                deferred_state["players"] = deferred_players
            else:
                deferred_state.pop("players", None)
    else:
        immediate_state = {
            key: deepcopy(value)
            for key, value in state_update.items()
            if not defer_state_update or key in _ECONOMY_STATE_KEYS
        }
        deferred_state = {
            key: deepcopy(value)
            for key, value in state_update.items()
            if defer_state_update and key not in _ECONOMY_STATE_KEYS and _meaningful(value)
        }
    deferred: dict[str, Any] = {}
    if deferred_state:
        deferred["state_update"] = deferred_state
    data["state_update"] = immediate_state
    response.state_update = immediate_state

    for key in _DEFERRED_DATA_KEYS:
        value = data.get(key)
        if _meaningful(value):
            deferred[key] = deepcopy(value)
        if key in {"memory_delta"}:
            data[key] = {"add": [], "update": [], "forget": []}
        elif key == "plot_update":
            data[key] = {"quests": [], "relations": [], "decisions": []}
        elif key in {"info_asymmetry"}:
            data[key] = {}
        elif key in {"confirmed", "growth_skills", "milestone_grants", "quick_actions"}:
            data[key] = []
        elif key == "xp_rewards":
            data[key] = {}
        else:
            data[key] = ""

    response.memory_delta = data.get("memory_delta", {})
    response.info_asymmetry = data.get("info_asymmetry", {})
    response.plot_update = data.get("plot_update", {})
    return deferred


def pending_decision_notice(language: str) -> str:
    return localized_text(language, {
        "en": (
            "Settlement pending: any narrated goods, services, scene changes, or quest progress "
            "that depend on this transaction have not taken effect yet."
        ),
        "zh-CN": "结算待确认：本次交易关联的物品、服务、场景或任务推进尚未生效。",
        "ja": "決済確認待ち：この取引に関連するアイテム・サービス・場面・クエスト進行はまだ発効していません。",
    })
