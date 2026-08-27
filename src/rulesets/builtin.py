"""Composition root for first-party ruleset runtime implementations."""

from pathlib import Path

from src.rulesets.dnd2024 import Dnd2024Runtime
from src.rulesets.legacy_adapter import LegacyRulesetAdapter
from src.rulesets.registry import RulesetRuntimeRegistry


def build_default_ruleset_registry(
    adventures_dir: str | Path | None = None,
) -> RulesetRuntimeRegistry:
    return RulesetRuntimeRegistry([
        LegacyRulesetAdapter(),
        Dnd2024Runtime(adventures_dir=adventures_dir),
    ])
