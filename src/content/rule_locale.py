"""Pure V2 rule locale materialization helper."""

from __future__ import annotations

import copy
from typing import Any


def materialize_rule(core: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(core)
    fields = overlay.get("fields") if isinstance(overlay.get("fields"), dict) else {}
    rule_fields = overlay.get("rule") if isinstance(overlay.get("rule"), dict) else {}
    result.update({key: value for key, value in rule_fields.items() if key in {"rule_name", "name", "description", "attr_hint", "skill_hint", "gm_prompt_appendix"}})
    for key, values in (("attributes", overlay.get("attributes")), ("classes", overlay.get("classes")), ("items", overlay.get("items")), ("skills", overlay.get("skills"))):
        if not isinstance(values, dict):
            continue
        if key == "attributes":
            by_key = {str(item.get("key")): item for item in result.get("attributes", []) if isinstance(item, dict)}
            for identity, data in values.items():
                if identity in by_key and isinstance(data, dict):
                    by_key[identity].update({k: v for k, v in data.items() if k in {"name", "label", "hint"}})
        elif key == "classes":
            by_id = {str(item.get("id")): item for item in result.get("classes", []) if isinstance(item, dict) and item.get("id")}
            for identity, data in values.items():
                if identity in by_id and isinstance(data, dict):
                    by_id[identity].update({k: v for k, v in data.items() if k in {"name", "description"}})
                    if "starter_equipment_ids" in by_id[identity]:
                        by_id[identity]["starter_equipment"] = list(by_id[identity]["starter_equipment_ids"])
        elif key == "items" and isinstance(result.get("items"), dict):
            for identity, data in values.items():
                if identity in result["items"] and isinstance(data, dict):
                    result["items"][identity].update({k: v for k, v in data.items() if k in {"name", "description"}})
        elif key == "skills":
            result.setdefault("skill_names", {}).update(values)
    if fields:
        result.update({key: value for key, value in fields.items() if key in {"name", "description"}})
    result["active_locale"] = overlay.get("locale", result.get("default_locale", ""))
    return result
