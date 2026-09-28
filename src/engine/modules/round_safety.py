"""Round rollback safety net: player and legacy entity snapshots, plus death saves.

Together with combat_extension's round_snapshots these preserve everything
changed in the round. Reset clears the snapshots but preserves death-save caches.
"""

from __future__ import annotations

from typing import Any

from src.engine.game_state_contracts import PlayerRollbackSnapshot
from src.engine.module_state import (
    ModuleStateError, ModuleStateSpec, get_module_state, register_module_state,
)

MODULE_NAME = "round_safety"
SCHEMA_VERSION = 1


def fresh() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "round_start_snapshot": {},
        "round_entity_snapshot": {},
        "death_save_outcomes": {},
    }


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    for key in ("round_start_snapshot", "round_entity_snapshot", "death_save_outcomes"):
        if not isinstance(raw.get(key), dict):
            raw[key] = {}
    return raw


def require_writable(instance: Any) -> None:
    """Read-only transaction preflight; never repair or materialize a slot."""
    modules = getattr(instance, "modules", None)
    if not isinstance(modules, dict):
        raise ModuleStateError("instance has no module state container")
    slot = modules.get(MODULE_NAME)
    if not isinstance(slot, dict):
        return  # Missing/corrupt slots have the documented fresh default.
    if slot.get("schema_version") != SCHEMA_VERSION:
        raise ModuleStateError(f"unsupported round_safety module schema: {slot.get('schema_version')!r}")


def round_start_snapshot(instance: Any) -> PlayerRollbackSnapshot:
    return get_module_state(instance, MODULE_NAME)["round_start_snapshot"]


def capture_players(instance: Any, snapshot: PlayerRollbackSnapshot) -> None:
    get_module_state(instance, MODULE_NAME)["round_start_snapshot"] = snapshot


def round_entity_snapshot(instance: Any) -> dict[str, Any]:
    return get_module_state(instance, MODULE_NAME)["round_entity_snapshot"]


def replace_entity_snapshot(instance: Any, snapshot: dict[str, Any]) -> None:
    get_module_state(instance, MODULE_NAME)["round_entity_snapshot"] = snapshot


def death_save_outcomes(instance: Any) -> dict[str, dict[str, dict]]:
    return get_module_state(instance, MODULE_NAME)["death_save_outcomes"]


def replace_death_save_outcomes(instance: Any, value: dict[str, dict[str, dict]]) -> None:
    get_module_state(instance, MODULE_NAME)["death_save_outcomes"] = value


def clear_snapshots(instance: Any) -> None:
    require_writable(instance)
    instance.round_start_snapshot.clear()
    instance.round_entity_snapshot.clear()


def discard_round(instance: Any) -> None:
    require_writable(instance)
    instance.death_save_outcomes.clear()
    instance.round_start_snapshot.clear()
    instance.round_entity_snapshot.clear()


def keep_death_saves_for(instance: Any, round_key: str) -> None:
    require_writable(instance)
    instance.death_save_outcomes = {
        round_key: instance.death_save_outcomes.get(round_key, {}),
    }


def death_save_cache(instance: Any, round_key: str) -> dict:
    require_writable(instance)
    return instance.death_save_outcomes.setdefault(round_key, {})


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)
