from __future__ import annotations
import random
from typing import Any, Callable

# SillyTavern ``world_info_logic`` (public/scripts/world-info.js):
#   AND_ANY: 0, NOT_ALL: 1, NOT_ANY: 2, AND_ALL: 3
ST_SELECTIVE_LOGIC: dict[str, str] = {
    "0": "and_any",
    "1": "not_all",
    "2": "not_any",
    "3": "and_all",
}

# Legacy DiceFrame / free-form aliases that historically landed in the same
# column. ``and`` was the canonical column default and behaved as AND_ANY.
SELECTIVE_LOGIC_ALIASES: dict[str, str] = {
    "": "and_any",
    "0": "and_any", "1": "not_all", "2": "not_any", "3": "and_all",
    "and": "and_any", "and_any": "and_any", "any": "and_any", "or": "and_any",
    "and_all": "and_all", "all": "and_all",
    "not_any": "not_any",
    "not_all": "not_all",
}

# Legacy DiceFrame primary ``match_mode`` vocabulary (kept separate from the
# SillyTavern selective secondary logic above).
PRIMARY_MATCH_MODES: frozenset[str] = frozenset({"any", "all", "not_any", "not_all"})

# Canonical entry-level vector activation modes. ``hybrid`` is the default so
# migrated primary world lore keeps the pre-v2 keyword + semantic behaviour
# instead of silently losing semantic retrieval after the book_id migration.
CANONICAL_VECTOR_ACTIVATION: frozenset[str] = frozenset({"off", "hybrid", "vector_only"})
DEFAULT_VECTOR_ACTIVATION = "hybrid"


def normalize_selective_logic(value: Any) -> str:
    """Normalize a SillyTavern secondary-key logic to its canonical name.

    Unknown values fall back to ``and_any`` (the SillyTavern default) instead of
    inventing a new mode: the primary key must still gate activation.
    """

    raw = str(value if value is not None else "").strip().lower()
    return SELECTIVE_LOGIC_ALIASES.get(raw, "and_any")


def normalize_primary_match_mode(value: Any) -> str:
    """Normalize the legacy DiceFrame primary ``match_mode``."""

    mode = str(value if value is not None else "").strip().lower()
    return mode if mode in PRIMARY_MATCH_MODES else "any"

def evaluate_probability(entry: dict[str, Any], *, rng: Callable[[], float] = random.random) -> tuple[bool, dict[str, Any]]:
    configured = max(0, min(100, int(entry.get("probability", 100) or 0)))
    if configured >= 100:
        return True, {"configured": configured, "roll": 0, "accepted": True}
    roll = int(rng() * 100) + 1
    return roll <= configured, {"configured": configured, "roll": roll, "accepted": roll <= configured}

def matched_key_score(entry: dict[str, Any], *, primary_hits: list[bool], secondary_hits: list[bool] | None = None) -> int:
    """SillyTavern-compatible group score for one entry (world-info ``getScore``).

    Every matched primary key counts; secondary keys only contribute for the
    positive logics, and never for NOT_ANY / NOT_ALL.
    """

    if not primary_hits:
        return 0
    score = sum(1 for hit in primary_hits if hit)
    secondary_hits = secondary_hits or []
    if secondary_hits:
        logic = normalize_selective_logic(entry.get("selective_logic"))
        if logic == "and_any":
            score += sum(1 for hit in secondary_hits if hit)
        elif logic == "and_all" and all(secondary_hits):
            score += sum(1 for hit in secondary_hits if hit)
    return score

def eligible_for_recursion(entry: dict[str, Any], depth: int, *, recursive_pass: bool) -> bool:
    if not bool(entry.get("enabled", True)) or (bool(entry.get("delay_until_recursion", False)) and not recursive_pass):
        return False
    level = int(entry.get("recursion_level", 0) or 0)
    return level <= 0 or depth >= level

def next_recursion_buffer(entry: dict[str, Any]) -> str:
    if bool(entry.get("prevent_further_recursion", False)) or bool(entry.get("non_recursable", False)):
        return ""
    return str(entry.get("content", "") or "")

def migrate_timed_state(state: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    """Convert legacy timers to the persisted independent-counter shape.

    The operation is idempotent so the codec can normalize both old saves and
    already-migrated saves at every load/save boundary.
    """
    result: dict[str, dict[str, int]] = {}
    for entry_id, raw in (state or {}).items():
        if not isinstance(raw, dict):
            continue
        if any(key in raw for key in ("sticky_remaining", "cooldown_remaining", "delay_remaining")):
            result[str(entry_id)] = {
                "sticky_remaining": max(0, int(raw.get("sticky_remaining", 0) or 0)),
                "cooldown_remaining": max(0, int(raw.get("cooldown_remaining", 0) or 0)),
                "delay_remaining": max(0, int(raw.get("delay_remaining", 0) or 0)),
                "activated_tick": int(raw.get("activated_tick", 0) or 0),
            }
            continue
        remaining = max(0, int(raw.get("remaining", 0) or 0))
        status = str(raw.get("status", ""))
        result[str(entry_id)] = {
            "sticky_remaining": remaining if status == "active" else 0,
            "cooldown_remaining": remaining if status == "cooldown" else 0,
            "delay_remaining": remaining if status in ("delayed", "delay") else 0,
            "activated_tick": int(raw.get("activated_tick", 0) or 0),
        }
    return result
