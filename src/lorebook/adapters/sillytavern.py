from __future__ import annotations

from typing import Any

from src.lorebook.domain import LoreEntryDraft, LorebookDraft


def from_sillytavern(payload: dict[str, Any]) -> LorebookDraft:
    rows = payload.get("entries", []) if isinstance(payload, dict) else []
    entries = []
    for raw in rows if isinstance(rows, list) else []:
        row = raw if isinstance(raw, dict) else {}
        timed = {k: int(row[k]) for k in ("sticky", "cooldown", "delay") if isinstance(row.get(k), (int, float))}
        recursion_flags = {
            key: value for key, value in {
                "non_recursable": bool(row.get("nonRecursable", row.get("non_recursable", False))),
                "prevent_further_recursion": bool(row.get("preventFurtherRecursion", row.get("prevent_further_recursion", False))),
                "delay_until_recursion": bool(row.get("delayUntilRecursion", row.get("delay_until_recursion", False))),
                "recursion_level": int(row.get("recursionLevel", row.get("recursion_level", 0)) or 0),
            }.items() if value
        }
        entries.append(LoreEntryDraft(
            name=str(row.get("comment", row.get("name", "")) or ""), content=str(row.get("content", "") or ""),
            keys=_strings(row.get("key", row.get("keys", []))), secondary_keys=_strings(row.get("keysecondary", row.get("secondary_keys", []))),
            enabled=not bool(row.get("disable", row.get("disabled", False))), constant=bool(row.get("constant", False)),
            selective_logic=str(row.get("selectiveLogic", row.get("selective_logic", "any")) or "any"),
            use_regex=bool(row.get("useRegex", row.get("use_regex", False))), case_sensitive=bool(row.get("caseSensitive", False)),
            match_whole_words=bool(row.get("matchWholeWords", False)), scan_depth=int(row.get("scanDepth", 0) or 0),
            insertion_order=int(row.get("order", 100) or 100), probability=int(row.get("probability", 100) or 100),
            groups=_strings(row.get("group", row.get("groups", []))), group_weight=int(row.get("groupWeight", 1) or 1),
            prioritize_inclusion=bool(row.get("prioritizeInclusion", row.get("prioritize_inclusion", False))),
            group_scoring=str(row.get("groupScoring", row.get("group_scoring", "")) or ""),
            recursion_flags=recursion_flags, vector_activation=str(row.get("vectorActivation", row.get("vector_activation", "off")) or "off"),
            timed=timed, prompt_slot=str(row.get("position", "") or ""), external_id=str(row.get("uid", row.get("id", "")) or ""),
            extensions={k: v for k, v in row.items() if k not in {"comment", "name", "content", "key", "keys", "keysecondary", "secondary_keys", "disable", "disabled", "constant", "selectiveLogic", "selective_logic", "useRegex", "use_regex", "order", "probability"}},
        ))
    warnings = ["ST timed effects are message-based; DiceFrame applies authoritative turn ticks."] if any(e.timed for e in entries) else []
    return LorebookDraft(name=str(payload.get("name", "SillyTavern World Info") or "SillyTavern World Info"), entries=entries, source={"kind": "sillytavern"}, warnings=warnings)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(item).strip() for item in value or [] if str(item).strip()] if isinstance(value, list) else []
