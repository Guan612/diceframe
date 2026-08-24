"""Stateless resolver for professional ruleset rests."""

from __future__ import annotations

import secrets
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from src.webui.services.ruleset_builder import validate_draft_shape

if TYPE_CHECKING:
    from src.webui.api import WebAPI


def resolve(
    api: "WebAPI", rule_id: str, body: Any, language: str = "",
) -> dict[str, Any]:
    parsed = validate_draft_shape(body)
    character = parsed.get("character")
    rest = parsed.get("rest")
    hit_die_rolls = parsed.get("hit_die_rolls")
    if not isinstance(character, dict):
        raise ValueError("rest character must be a JSON object")
    if rest not in {"short", "long"}:
        raise ValueError("rest must be short or long")
    if hit_die_rolls is not None and not isinstance(hit_die_rolls, dict):
        raise ValueError("hit_die_rolls must be a JSON object")
    rule = api._load_rule_by_id(rule_id, language)
    if rule is None:
        return {"ok": False, "code": "RULE_NOT_FOUND", "error": f"规则不存在: {rule_id}"}
    runtime = api._ruleset_registry.resolve(rule.template)
    method = getattr(runtime, "complete_rest", None)
    if not callable(method):
        return {
            "ok": False,
            "code": "RULESET_REST_UNAVAILABLE",
            "error": "该规则尚未提供专业休息结算",
        }
    result = method(rule, character, rest, hit_die_rolls)
    return {"ok": True, "rule_id": rule.rule_id, **result}


def _failure(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "code": code, "error": message, **extra}


def _server_hit_die_rolls(character: dict[str, Any], requested: Any) -> dict[str, list[int]]:
    if requested is None:
        return {}
    if not isinstance(requested, dict):
        raise ValueError("hit_dice must be a JSON object")
    canonical = character.get("ruleset_character")
    canonical = canonical if isinstance(canonical, dict) else character
    available = canonical.get("resources", {}).get("hit_dice", {})
    if not isinstance(available, dict):
        raise ValueError("character hit dice are missing")
    rolls: dict[str, list[int]] = {}
    for die, raw_count in requested.items():
        if isinstance(raw_count, bool):
            raise ValueError(f"hit_dice.{die} must be a non-negative integer")
        try:
            count = int(raw_count)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"hit_dice.{die} must be a non-negative integer") from exc
        if count < 0 or count > int(available.get(die, -1)):
            raise ValueError(f"not enough {die} Hit Point Dice")
        try:
            sides = int(str(die).removeprefix("d"))
        except ValueError as exc:
            raise ValueError(f"invalid hit die {die}") from exc
        if sides < 2:
            raise ValueError(f"invalid hit die {die}")
        rolls[str(die)] = [secrets.randbelow(sides) + 1 for _ in range(count)]
    return rolls


async def resolve_live(
    api: "WebAPI", game_key: str, user_id: str, body: Any,
) -> dict[str, Any]:
    parsed = validate_draft_shape(body)
    rest = parsed.get("rest")
    if rest not in {"short", "long"}:
        return _failure("INVALID_REST", "休息类型必须是 short 或 long")
    if "hit_die_rolls" in parsed:
        return _failure(
            "CLIENT_ROLLS_FORBIDDEN", "休息骰由服务端掷出；客户端只需提交要花费的生命骰数量",
        )
    if rest == "long" and parsed.get("hit_dice"):
        return _failure("INVALID_REST", "长休不需要花费生命骰")
    if parsed.get("confirm_elapsed_time") is not True:
        return _failure("REST_CONFIRMATION_REQUIRED", "请先确认游戏时间会随本次休息推进")
    operation_id = str(parsed.get("operation_id") or "").strip()
    if not operation_id or len(operation_id) > 160:
        return _failure("INVALID_OPERATION_ID", "休息操作必须提供有效的 operation_id")

    instance = api._reg.get(api._parse_key(game_key))
    if instance is None:
        return _failure("GAME_NOT_FOUND", "游戏不存在")
    if user_id not in instance.players:
        return _failure("CHARACTER_NOT_FOUND", "角色不存在")
    rule = api._load_rule_for_game(instance)
    if rule is None:
        return _failure("RULE_NOT_FOUND", "当前游戏规则不存在")
    try:
        runtime = api._ruleset_registry.resolve(rule.template)
    except (AttributeError, TypeError, ValueError) as exc:
        return _failure("RULESET_RUNTIME_UNAVAILABLE", str(exc))
    method = getattr(runtime, "complete_rest", None)
    if not callable(method):
        return _failure("RULESET_REST_UNAVAILABLE", "该规则尚未提供专业休息结算")
    context_validator = getattr(runtime, "validate_rest_context", None)
    if callable(context_validator):
        try:
            context_validator(instance, user_id, rest)
        except ValueError as exc:
            return _failure("REST_NOT_AVAILABLE", str(exc))

    character = instance.get_character_sheet(user_id)
    revision = int(character.get("ruleset_revision", 0) or 0)
    raw_log = character.get("ruleset_operation_log")
    operation_log = deepcopy(raw_log) if isinstance(raw_log, list) else []
    previous = next((
        entry for entry in operation_log
        if isinstance(entry, dict) and entry.get("operation_id") == operation_id
    ), None)
    if previous is not None:
        if previous.get("kind") != "rest":
            return _failure(
                "OPERATION_ID_REUSED", "operation_id 已被其他角色操作使用，请重试",
            )
        return {
            "ok": True, "rule_id": rule.rule_id, "game_key": game_key,
            "user_id": user_id, "revision": revision, "duplicate": True,
            "rest": previous.get("rest"), "events": deepcopy(previous.get("events") or []),
            "character": deepcopy(character),
        }
    raw_expected = parsed.get("expected_revision")
    if isinstance(raw_expected, bool):
        raw_expected = None
    try:
        expected_revision = int(raw_expected)
    except (TypeError, ValueError):
        return _failure(
            "INVALID_CHARACTER_REVISION",
            "休息操作必须提供有效的 expected_revision",
        )
    if expected_revision != revision:
        return _failure(
            "STALE_CHARACTER_REVISION", "角色已在其他位置更新，请刷新后重试",
            revision=revision,
        )
    try:
        hit_die_rolls = _server_hit_die_rolls(
            character, parsed.get("hit_dice") if rest == "short" else None,
        )
        result = method(rule, character, rest, hit_die_rolls)
    except (TypeError, ValueError) as exc:
        return _failure("INVALID_REST", str(exc))
    updated = deepcopy(character)
    updated.update(result["character"])
    updated["ruleset_revision"] = revision + 1
    operation_log.append({
        "operation_id": operation_id,
        "kind": "rest",
        "rest": rest,
        "events": deepcopy(result.get("events") or []),
        "revision": revision + 1,
    })
    updated["ruleset_operation_log"] = operation_log[-32:]
    before_player = deepcopy(instance.players[user_id])
    instance.set_character_sheet(user_id, updated)
    try:
        await api._reg.save(instance)
    except Exception:
        instance.players[user_id] = before_player
        raise
    return {
        "ok": True, "rule_id": rule.rule_id, "game_key": game_key,
        "user_id": user_id, "revision": revision + 1, "duplicate": False,
        "rest": rest, "events": deepcopy(result.get("events") or []),
        "source_ref": result.get("source_ref"), "character": deepcopy(updated),
    }
