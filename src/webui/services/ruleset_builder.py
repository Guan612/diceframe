"""Stateless Web/API boundary for versioned professional character builders."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from src.rules.rule_system import RuleSystem
from src.rulesets.registry import RulesetRuntimeRegistry


MAX_BUILDER_DRAFT_BYTES = 256 * 1024
MAX_BUILDER_DRAFT_DEPTH = 32
MAX_BUILDER_DRAFT_NODES = 5000


@dataclass(frozen=True)
class RulesetBuilderDependencies:
    load_rule: Callable[[str, str], RuleSystem | None]
    ruleset_registry: RulesetRuntimeRegistry


def _measure(value: Any, depth: int = 0) -> tuple[int, int]:
    if depth > MAX_BUILDER_DRAFT_DEPTH:
        raise ValueError("builder draft nesting is too deep")
    nodes = 1
    max_depth = depth
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    for child in children:
        child_nodes, child_depth = _measure(child, depth + 1)
        nodes += child_nodes
        max_depth = max(max_depth, child_depth)
        if nodes > MAX_BUILDER_DRAFT_NODES:
            raise ValueError("builder draft contains too many values")
    return nodes, max_depth


def validate_draft_shape(draft: Any) -> dict[str, Any]:
    if not isinstance(draft, dict):
        raise ValueError("builder draft must be a JSON object")
    try:
        encoded = json.dumps(draft, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("builder draft must contain JSON-compatible values") from exc
    if len(encoded) > MAX_BUILDER_DRAFT_BYTES:
        raise ValueError("builder draft is too large")
    _measure(draft)
    return draft


def _context(
    dependencies: RulesetBuilderDependencies,
    rule_id: str,
    language: str,
    draft: Any,
):
    draft = validate_draft_shape(draft)
    if language and not draft.get("locale"):
        draft = {**draft, "locale": language}
    rule = dependencies.load_rule(rule_id, language)
    if rule is None:
        return None, None, draft, {
            "ok": False,
            "code": "RULE_NOT_FOUND",
            "error": f"规则不存在: {rule_id}",
        }
    runtime = dependencies.ruleset_registry.resolve(rule.template)
    if runtime.capabilities.character_builder != "professional":
        return rule, runtime, draft, {
            "ok": False,
            "code": "RULESET_BUILDER_UNAVAILABLE",
            "error": "该规则使用现有通用角色创建流程",
        }
    return rule, runtime, draft, None


def experience(
    dependencies: RulesetBuilderDependencies,
    rule_id: str,
    language: str = "",
) -> dict[str, Any]:
    rule = dependencies.load_rule(rule_id, language)
    if rule is None:
        return {"ok": False, "code": "RULE_NOT_FOUND", "error": f"规则不存在: {rule_id}"}
    runtime = dependencies.ruleset_registry.resolve(rule.template)
    return {
        "ok": True,
        "rule_id": rule.rule_id,
        "ruleset_runtime": dependencies.ruleset_registry.describe(rule.template).to_dict(),
        "experience": runtime.describe_experience(rule, language),
    }


def choices(
    dependencies: RulesetBuilderDependencies,
    rule_id: str,
    draft: Any,
    language: str = "",
) -> dict[str, Any]:
    rule, runtime, draft, error = _context(dependencies, rule_id, language, draft)
    if error:
        return error
    return {"ok": True, "rule_id": rule.rule_id, "choices": runtime.builder_choices(rule, draft)}


def validate(
    dependencies: RulesetBuilderDependencies,
    rule_id: str,
    draft: Any,
    language: str = "",
) -> dict[str, Any]:
    rule, runtime, draft, error = _context(dependencies, rule_id, language, draft)
    if error:
        return error
    errors = runtime.validate_character(rule, draft)
    return {"ok": True, "rule_id": rule.rule_id, "valid": not errors, "errors": errors}


def derive(
    dependencies: RulesetBuilderDependencies,
    rule_id: str,
    draft: Any,
    language: str = "",
) -> dict[str, Any]:
    rule, runtime, draft, error = _context(dependencies, rule_id, language, draft)
    if error:
        return error
    errors = runtime.validate_character(rule, draft)
    if errors:
        return {"ok": False, "code": "INVALID_CHARACTER_DRAFT", "errors": errors}
    return {"ok": True, "rule_id": rule.rule_id, "character": runtime.derive_character(rule, draft)}


def finalize(
    dependencies: RulesetBuilderDependencies,
    rule_id: str,
    draft: Any,
    language: str = "",
) -> dict[str, Any]:
    rule, runtime, draft, error = _context(dependencies, rule_id, language, draft)
    if error:
        return error
    errors = runtime.validate_character(rule, draft)
    if errors:
        return {"ok": False, "code": "INVALID_CHARACTER_DRAFT", "errors": errors}
    return {"ok": True, "rule_id": rule.rule_id, "character": runtime.finalize_character(rule, draft)}
