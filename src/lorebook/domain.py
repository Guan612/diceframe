"""Format-neutral Lorebook import contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LoreEntryDraft:
    name: str = ""
    content: str = ""
    keys: list[str] = field(default_factory=list)
    secondary_keys: list[str] = field(default_factory=list)
    enabled: bool = True
    constant: bool = False
    selective_logic: str = "any"
    use_regex: bool = False
    case_sensitive: bool = False
    match_whole_words: bool = False
    scan_depth: int = 0
    priority: int = 0
    insertion_order: int = 100
    probability: int = 100
    groups: list[str] = field(default_factory=list)
    group_weight: int = 1
    recursion_flags: dict[str, bool] = field(default_factory=dict)
    timed: dict[str, int] = field(default_factory=dict)
    prompt_slot: str = ""
    external_id: str = ""
    type: str = "other"
    tier: str = "background"
    unreliable: bool = False
    sync_on_enter: bool = False
    visible_to: list[str] = field(default_factory=list)
    connected_to: list[str] = field(default_factory=list)
    triggers_recursive: list[str] = field(default_factory=list)
    prioritize_inclusion: bool = False
    group_scoring: str = ""
    vector_activation: str = "off"
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass
class LorebookDraft:
    name: str = ""
    description: str = ""
    language: str = "zh-CN"
    settings: dict[str, Any] = field(default_factory=dict)
    entries: list[LoreEntryDraft] = field(default_factory=list)
    source: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    preserved_extensions: dict[str, Any] = field(default_factory=dict)
