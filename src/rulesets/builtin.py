"""Composition root for first-party ruleset runtime implementations."""

from src.rulesets.dnd2024 import Dnd2024Runtime
from src.rulesets.legacy_adapter import LegacyRulesetAdapter
from src.rulesets.registry import RulesetRuntimeRegistry


def build_default_ruleset_registry() -> RulesetRuntimeRegistry:
    return RulesetRuntimeRegistry([LegacyRulesetAdapter(), Dnd2024Runtime()])
