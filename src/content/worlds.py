"""Content V2 world-template loader with legacy V1 fallback."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

_DISPLAY_FIELDS = frozenset({"world_name", "description", "world_setting", "starter_scene"})
_LORE_DISPLAY_FIELDS = frozenset({"name", "keywords", "content"})


def materialize_world(core: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Apply a typed world locale without changing canonical lore identity/mechanics."""
    if not isinstance(overlay, dict):
        raise ValueError("world locale overlay must be an object")
    fields = overlay.get("fields")
    if not isinstance(fields, dict) or set(fields) - _DISPLAY_FIELDS:
        raise ValueError("world locale fields contain mechanics or unknown fields")
    canonical_id = str(core.get("world_id") or core.get("id") or "")
    target = overlay.get("target")
    if not isinstance(target, dict) or target.get("kind") not in {"world", "world_template"}:
        raise ValueError("world locale target kind is invalid")
    if str(target.get("id") or "") != canonical_id:
        raise ValueError("world locale target id is invalid")
    localized_entries = overlay.get("starter_lorebook", {})
    if not isinstance(localized_entries, dict):
        raise ValueError("world locale starter_lorebook must be an object keyed by canonical entry id")
    result = copy.deepcopy(core)
    result.update(copy.deepcopy(fields))
    entries = result.get("starter_lorebook", [])
    if not isinstance(entries, list):
        raise ValueError("world core starter_lorebook must be a list")
    by_id = {str(entry.get("id")): entry for entry in entries if isinstance(entry, dict) and entry.get("id")}
    for entry_id, values in localized_entries.items():
        if str(entry_id) not in by_id or not isinstance(values, dict):
            raise ValueError("world locale references an unknown starter lore entry")
        forbidden = set(values) - _LORE_DISPLAY_FIELDS
        if forbidden:
            raise ValueError(f"world locale lore entry contains mechanics fields: {sorted(forbidden)}")
        if "keywords" in values and not isinstance(values["keywords"], list):
            raise ValueError("world locale lore keywords must be a list")
        by_id[str(entry_id)].update(copy.deepcopy(values))
    result["active_locale"] = str(overlay.get("locale") or result.get("default_locale") or "")
    return result


def load_world_template(worlds_dir: str | Path, world_id: str, locale: str = "") -> dict[str, Any] | None:
    root = Path(worlds_dir)
    world_id = str(world_id or "").strip()
    if not world_id:
        return None
    path = root / f"{world_id}.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or int(raw.get("world_schema_version", 1) or 1) < 2:
        return raw
    requested = str(locale or raw.get("default_locale") or "").replace("_", "-")
    if requested:
        exact = root / "locales" / requested / f"{world_id}.json"
        fallback = root / "locales" / requested.split("-", 1)[0] / f"{world_id}.json"
        overlay_path = exact if exact.exists() else fallback
        if overlay_path.exists():
            overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
            if not isinstance(overlay, dict):
                raise ValueError("world locale overlay must be an object")
            if overlay.get("locale_schema_version") != 1 or not str(overlay.get("locale") or "").strip():
                raise ValueError("world locale schema is invalid")
            return materialize_world(raw, overlay)
    raw["active_locale"] = raw.get("default_locale", "")
    return raw
