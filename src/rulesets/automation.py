"""Transactional execution for server-owned ruleset intents."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.rulesets.contracts import AutomaticIntentRuntime, NarrativeDirectorAutomationRuntime


def apply_director_automation(
    runtime: Any, instance: Any, proposal: dict[str, Any], rng: Any,
    *, limit: int = 256,
) -> list[dict[str, Any]]:
    """Apply one Director intent and bounded follow-up automatic intents atomically."""

    if not isinstance(runtime, NarrativeDirectorAutomationRuntime):
        return []
    initial = runtime.director_automatic_intent(instance, proposal)
    if initial is None:
        return []
    initial_intents = initial if isinstance(initial, list) else [initial]
    if not initial_intents:
        return []
    before = {
        "ruleset_state": deepcopy(instance.ruleset_state),
        "event_ledger": deepcopy(instance.event_ledger),
        "players": deepcopy(instance.players),
        "combat_state": instance.combat_state,
        "combat_active": instance.combat_active,
        "initiative_order": deepcopy(instance.initiative_order),
        "initiative_current": instance.initiative_current,
        "scene": getattr(instance, "scene", None),
    }
    batches: list[dict[str, Any]] = []
    try:
        pending_intents = list(initial_intents)
        pending: dict[str, Any] | None = pending_intents.pop(0)
        for _ in range(limit):
            if pending is None:
                return batches
            resolved = runtime.resolve_intent(instance, pending, rng)
            if not resolved.get("ok"):
                raise ValueError(str(resolved.get("error") or "Director intent was rejected"))
            batch = resolved.get("event_batch")
            if not isinstance(batch, dict):
                raise ValueError("Director intent returned no event batch")
            applied = runtime.apply_event_batch(instance, batch)
            if not applied.get("applied"):
                raise ValueError("Director intent did not advance state")
            batches.append(deepcopy(batch))
            if pending_intents:
                pending = pending_intents.pop(0)
            else:
                pending = (
                    runtime.next_automatic_intent(instance)
                    if isinstance(runtime, AutomaticIntentRuntime)
                    else None
                )
        raise ValueError("Director automation exceeded the safety limit")
    except Exception:
        instance.ruleset_state = before["ruleset_state"]
        instance.event_ledger = before["event_ledger"]
        instance.players = before["players"]
        instance.combat_state = before["combat_state"]
        instance.combat_active = before["combat_active"]
        instance.initiative_order = before["initiative_order"]
        instance.initiative_current = before["initiative_current"]
        if before["scene"] is not None:
            instance.scene = before["scene"]
        raise


def summarize_automation_batches(batches: list[dict[str, Any]], *, chinese: bool = True) -> str:
    """Produce a short public-log note without importing a concrete ruleset."""

    event_types = {
        str(event.get("type") or "")
        for batch in batches
        for event in batch.get("events", [])
        if isinstance(event, dict)
    }
    if "dnd2024.combat.started" in event_types:
        return "自动规则已进入遭遇战。" if chinese else "Automatic rules entered an encounter."
    if "dnd2024.tutorial.choice_applied" in event_types:
        return "AI GM 已根据行动推进当前冒险节点。" if chinese else "The AI GM advanced the adventure node from the action."
    if "dnd2024.party_decision.resolved" in event_types:
        return "AI GM 已根据队伍行动结算分支。" if chinese else "The AI GM resolved the branch from the party actions."
    return "自动规则事件已结算。" if chinese else "An automatic rules event was resolved."
