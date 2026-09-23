"""Scene-image and map-background references in a persisted module slot."""

from __future__ import annotations

from typing import Any

from src.engine.module_state import ModuleStateSpec, get_module_state, register_module_state

MODULE_NAME = "media"
SCHEMA_VERSION = 1


def fresh() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "scene_image": {}, "map_background": {}}


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    for key in ("scene_image", "map_background"):
        if not isinstance(raw.get(key), dict):
            raw[key] = {}
    return raw


def scene_image(instance: Any) -> dict[str, str]:
    return get_module_state(instance, MODULE_NAME)["scene_image"]


def replace_scene_image(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["scene_image"] = value if isinstance(value, dict) else {}


def map_background(instance: Any) -> dict[str, str]:
    return get_module_state(instance, MODULE_NAME)["map_background"]


def replace_map_background(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["map_background"] = value if isinstance(value, dict) else {}


def payload_container(payload: dict[str, Any]) -> dict[str, Any]:
    """Locate references in either a module save or a legacy package payload."""
    modules = payload.get("modules")
    slot = modules.get(MODULE_NAME) if isinstance(modules, dict) else None
    return slot if isinstance(slot, dict) else payload


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)
