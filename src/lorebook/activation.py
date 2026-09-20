from __future__ import annotations
import random
from typing import Any, Callable

def evaluate_probability(entry: dict[str, Any], *, rng: Callable[[], float] = random.random) -> tuple[bool, dict[str, Any]]:
    configured = max(0, min(100, int(entry.get("probability", 100) or 0)))
    if configured >= 100:
        return True, {"configured": configured, "roll": 0, "accepted": True}
    roll = int(rng() * 100) + 1
    return roll <= configured, {"configured": configured, "roll": roll, "accepted": roll <= configured}

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
