from __future__ import annotations

from typing import Any

from src.lorebook.domain import LoreEntryDraft, LorebookDraft


def from_legacy_entries(payload: dict[str, Any] | list[dict[str, Any]]) -> LorebookDraft:
    rows = payload if isinstance(payload, list) else payload.get("entries", payload.get("lorebook", []))
    rows = rows if isinstance(rows, list) else []
    entries = []
    for row in rows:
        row = row if isinstance(row, dict) else {}
        entries.append(LoreEntryDraft(
            name=str(row.get("name", "") or ""), content=str(row.get("content", "") or ""),
            keys=_strings(row.get("keywords", row.get("keys", []))),
            enabled=not bool(row.get("disabled", False)), constant=bool(row.get("is_constant", row.get("constant", False))),
            selective_logic=str(row.get("match_mode", "any") or "any"),
            insertion_order=int(row.get("order", 100) or 100), probability=int(row.get("probability", 100) or 100),
            group_weight=int(row.get("group_weight", 1) or 1),
            extensions={"diceframe": {k: row[k] for k in ("type", "tier", "unreliable", "connected_to", "visible_to", "triggers_recursive") if k in row}},
            external_id=str(row.get("id", "") or ""),
        ))
    return LorebookDraft(name=str((payload or {}).get("name", "Legacy Lorebook") if isinstance(payload, dict) else "Legacy Lorebook"), entries=entries, source={"kind": "diceframe_legacy"})


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(item).strip() for item in value or [] if str(item).strip()] if isinstance(value, list) else []
