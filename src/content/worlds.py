"""Content V2 world-template loader with legacy V1 fallback."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

_DISPLAY_FIELDS = frozenset({
    "world_name", "description", "world_setting", "starter_scene",
    "suggested_difficulty", "starter_lorebook",
})


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
            forbidden = set(overlay) - {"locale_schema_version", "locale", "target", "fields"}
            if forbidden:
                raise ValueError(f"world locale overlay contains mechanics fields: {sorted(forbidden)}")
            fields = overlay.get("fields")
            if not isinstance(fields, dict) or set(fields) - _DISPLAY_FIELDS:
                raise ValueError("world locale overlay contains invalid fields")
            result = copy.deepcopy(raw)
            result.update(copy.deepcopy(fields))
            result["active_locale"] = overlay.get("locale", requested)
            return result
    raw["active_locale"] = raw.get("default_locale", "")
    return raw
