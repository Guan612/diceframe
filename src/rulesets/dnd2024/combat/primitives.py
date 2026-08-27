"""Shared identifiers, errors, and dice primitives for D&D 2024 combat stages."""

from __future__ import annotations

import re
from typing import Any


DICE_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")
INTENT_TYPES = frozenset({
    "encounter.ready", "encounter.unready", "combat.start", "combat.end", "combat.message",
    "attack", "cast_spell", "move", "dash", "dodge", "disengage", "end_turn",
    "death_save", "stabilize", "decision.resolve",
})


class CombatIntentError(ValueError):
    """Raised when a combat intent or state is structurally invalid."""


def canonical(sheet: dict[str, Any]) -> dict[str, Any]:
    nested = sheet.get("ruleset_character")
    if isinstance(nested, dict):
        return nested
    if sheet.get("rule_binding"):
        return sheet
    raise CombatIntentError("professional character is missing canonical state")


def player_actor(uid: str) -> str:
    return f"player:{uid}"


def enemy_actor(enemy_id: str) -> str:
    return f"enemy:{enemy_id}"


def actor_kind(actor_id: str) -> tuple[str, str]:
    if actor_id.startswith("player:"):
        return "player", actor_id.removeprefix("player:")
    if actor_id.startswith("enemy:"):
        return "enemy", actor_id.removeprefix("enemy:")
    return "", ""


def roll(formula: str, rng: Any, *, critical: bool = False) -> tuple[int, list[int]]:
    match = DICE_RE.fullmatch(str(formula or ""))
    if match is None:
        raise CombatIntentError(f"unsupported dice formula: {formula}")
    count, sides, bonus = (int(value or 0) for value in match.groups())
    if critical:
        count *= 2
    rolls = [int(rng.randint(1, sides)) for _ in range(count)]
    return sum(rolls) + bonus, rolls
