from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any

@dataclass
class ActivationTrace:
    entry_id: str
    book_id: str = ""
    candidate_sources: list[str] | None = None
    matched_keys: list[str] | None = None
    secondary_matches: list[str] | None = None
    primary_result: bool | None = None
    secondary_result: bool | None = None
    semantic_score: float | None = None
    recursion_parent: str | None = None
    recursion_depth: int = 0
    probability: dict[str, Any] | None = None
    group: str | None = None
    timed: dict[str, Any] | None = None
    visibility: str = "visible"
    budget: str = "included"
    final_state: str = "candidate"
    reason_code: str = ""

    def to_dict(self, *, safe: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if safe and self.visibility != "visible":
            return {"entry_id": "", "book_id": "", "final_state": "hidden"}
        return data
