from __future__ import annotations
from typing import Any

def entry_sort_key(entry: dict[str, Any], *, recursive: bool = False, semantic_only: bool = False) -> tuple:
    return (0 if entry.get("is_constant") else 1, 0 if entry.get("_direct_match") else 1, -int(entry.get("priority", 0) or 0), int(entry.get("order", 100) or 100), 1 if recursive else 0, 1 if semantic_only else 0, str(entry.get("id", "")))

def apply_token_budget(entries: list[dict[str, Any]], budget: int | None, *, estimate: callable | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    if budget is None or budget <= 0:
        return entries, []
    estimate = estimate or (lambda row: max(1, len(str(row.get("content", ""))) // 4))
    included, omitted, used = [], [], 0
    for entry in sorted(entries, key=entry_sort_key):
        cost = int(estimate(entry))
        if used + cost <= budget:
            included.append(entry); used += cost
        else:
            omitted.append(str(entry.get("id", "")))
    return included, omitted
