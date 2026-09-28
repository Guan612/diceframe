"""Ruleset binding storage; ruleset packages own state and event ledger contents."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.engine.module_state import (
    ModuleStateError, ModuleStateSpec, get_module_state, register_module_state,
)

MODULE_NAME = "ruleset_runtime"
SCHEMA_VERSION = 1


def fresh() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "binding": {}, "state": {}, "event_ledger": []}


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    for key in ("binding", "state"):
        if not isinstance(raw.get(key), dict):
            raw[key] = {}
    if not isinstance(raw.get("event_ledger"), list):
        raw["event_ledger"] = []
    return raw


def require_writable(instance: Any) -> None:
    """Read-only transaction preflight; never repair or materialize a slot."""
    modules = getattr(instance, "modules", None)
    if not isinstance(modules, dict):
        raise ModuleStateError("instance has no module state container")
    slot = modules.get(MODULE_NAME)
    if not isinstance(slot, dict):
        return
    if slot.get("schema_version") != SCHEMA_VERSION:
        raise ModuleStateError(f"unsupported ruleset_runtime module schema: {slot.get('schema_version')!r}")


def binding(instance: Any) -> dict[str, Any]:
    return get_module_state(instance, MODULE_NAME)["binding"]


def replace_binding(instance: Any, value: dict[str, Any]) -> None:
    get_module_state(instance, MODULE_NAME)["binding"] = value


def state(instance: Any) -> dict[str, Any]:
    return get_module_state(instance, MODULE_NAME)["state"]


def replace_state(instance: Any, value: dict[str, Any]) -> None:
    get_module_state(instance, MODULE_NAME)["state"] = value


def event_ledger(instance: Any) -> list[dict[str, Any]]:
    return get_module_state(instance, MODULE_NAME)["event_ledger"]


def replace_event_ledger(instance: Any, value: list[dict[str, Any]]) -> None:
    get_module_state(instance, MODULE_NAME)["event_ledger"] = value


def persisted_state(instance: Any) -> dict[str, Any]:
    """Preserve encode-only omission of unbound state without changing live data.

    Follow-up: rest sessions on unbound games still disappear on reload.
    Unknown slot versions remain opaque, just like other module slots.
    """
    slot = instance.modules[MODULE_NAME]
    if slot.get("schema_version") != SCHEMA_VERSION:
        return slot
    return slot if slot.get("binding") else fresh()


def bind(instance: Any, normalized: dict[str, Any]) -> None:
    require_writable(instance)
    instance.ruleset_runtime = normalized
    if not instance.ruleset_state:
        instance.ruleset_state = {"state_schema_version": normalized["state_schema_version"]}


def copy_binding_for_new_run(candidate: Any, source: Any) -> None:
    require_writable(source)
    require_writable(candidate)
    candidate.ruleset_runtime = deepcopy(source.ruleset_runtime)
    candidate.ruleset_state = (
        {"state_schema_version": int(source.ruleset_runtime.get("state_schema_version", 1) or 1)}
        if source.ruleset_runtime else {}
    )


def reset(instance: Any, saved_binding: dict[str, Any]) -> None:
    require_writable(instance)
    instance.ruleset_runtime = saved_binding
    instance.ruleset_state = (
        {"state_schema_version": int(saved_binding.get("state_schema_version", 1) or 1)}
        if saved_binding else {}
    )
    instance.event_ledger.clear()


def restore_from_transaction(instance: Any, snapshot: dict[str, Any]) -> None:
    require_writable(instance)
    instance.ruleset_state = deepcopy(snapshot["ruleset_state"])
    instance.event_ledger = deepcopy(snapshot["event_ledger"])


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)
