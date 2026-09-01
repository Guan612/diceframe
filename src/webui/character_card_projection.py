"""Pure identity and deduplication helpers for reusable character cards."""

from __future__ import annotations

from typing import Any


def card_signature(card: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(card.get("character_name") or "").strip().lower(),
        str(card.get("race") or "").strip().lower(),
        str(card.get("class") or "").strip().lower(),
        str(card.get("background") or "").strip().lower(),
        str(card.get("rule_id") or "").strip().lower(),
    )


def dedupe_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str, str, str]] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        signature = card_signature(card)
        if not signature[0]:
            signature = (
                str(card.get("id") or f"anon_{len(order)}"),
                "",
                "",
                "",
                "",
            )
        if signature not in seen:
            order.append(signature)
        seen[signature] = card
    return [seen[signature] for signature in order]
