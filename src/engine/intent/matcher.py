"""Item-name binding between purchase intents, grants and merchant offers."""

from __future__ import annotations

import re
from typing import Any, Iterable

from src.engine.intent.parser import currency_amounts


def normalized_item_name(name: str) -> str:
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

    names = [normalized_item_name(name) for name in item_names]
    names = [name for name in names if name]
    if not names:
        return []
    matches: list[dict[str, Any]] = []
    economy = getattr(instance, "economy", {})
    offers = economy.get("merchant_offers", []) if isinstance(economy, dict) else []
    for offer in offers:
        if not isinstance(offer, dict) or offer.get("status") != "open":
            continue
        if (
            offer.get("run_id")
            and str(offer.get("run_id")) != str(getattr(instance, "run_id", ""))
        ):
            continue
        display = normalized_item_name(str(offer.get("item_display") or ""))
        if len(display) < 2:
            continue
        if any(name == display or name.endswith(display) for name in names):
            matches.append(offer)
    return matches


def narration_price_for_items(
    language: str,
    narration: str,
    item_names: Iterable[str],
    currency_labels: Iterable[str] | None = None,
) -> int | None:
    """Bind a narration price to one purchase item at sentence granularity.

    只有"商品名与金额出现在同一句"的叙事金额才算该商品的报价；同句出现
    多个金额视为无法唯一确认（返回 None）。找不到绑定句返回 None，交由
    更低优先级的证据（全局唯一金额 / 行动自报）兜底。
    """

    names = [normalized_item_name(name) for name in item_names]
    names = [name for name in names if len(name) >= 2]
    if not names:
        return None
    bound: list[int] = []
    for sentence in re.split(r"[。！？.!?\n]+", str(narration or "")):
        if not any(name in normalized_item_name(sentence) for name in names):
            continue
        bound.extend(currency_amounts(language, sentence, currency_labels))
    unique = sorted(set(bound))
    return unique[0] if len(unique) == 1 else None
