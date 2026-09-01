"""Stateless Web/API boundary for professional ruleset advancement."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from src.webui.services.ruleset_builder import validate_draft_shape
from src.rulesets.dnd2024 import advancement_access
from src.rulesets.dnd2024.progression.catalog import ProgressionCatalogError

if TYPE_CHECKING:
    from src.webui.api import WebAPI


def _context(api: "WebAPI", rule_id: str, language: str):
    rule = api._load_rule_by_id(rule_id, language)
    if rule is None:
        return None, None, {
            "ok": False,
            "code": "RULE_NOT_FOUND",
            "error": f"规则不存在: {rule_id}",
        }
    runtime = api._ruleset_registry.resolve(rule.template)
    if not all(
        callable(getattr(runtime, name, None))
        for name in ("progression_table", "preview_advancement", "apply_advancement")
    ):
        return rule, runtime, {
            "ok": False,
            "code": "RULESET_ADVANCEMENT_UNAVAILABLE",
            "error": "该规则尚未提供专业升级流程",
        }
    return rule, runtime, None


def progression(
    api: "WebAPI",
    rule_id: str,
    class_ref: str,
    start_level: int = 1,
    end_level: int = 20,
    language: str = "",
) -> dict[str, Any]:
    rule, runtime, error = _context(api, rule_id, language)
    if error:
        return error
    rows = runtime.progression_table(
        rule, class_ref, start_level, end_level, language,
    )
    return {"ok": True, "rule_id": rule.rule_id, "progression": rows}


def _payload(body: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    parsed = validate_draft_shape(body)
    character = parsed.get("character")
    choices = parsed.get("choices", {})
    if not isinstance(character, dict):
        raise ValueError("advancement character must be a JSON object")
    if not isinstance(choices, dict):
        raise ValueError("advancement choices must be a JSON object")
    return character, choices


def preview(
    api: "WebAPI", rule_id: str, body: Any, language: str = "",
) -> dict[str, Any]:
    rule, runtime, error = _context(api, rule_id, language)
    if error:
        return error
    character, choices = _payload(body)
    return {
        "ok": True,
        "rule_id": rule.rule_id,
        "advancement": runtime.preview_advancement(rule, character, choices),
    }


def apply(
    api: "WebAPI", rule_id: str, body: Any, language: str = "",
) -> dict[str, Any]:
    rule, runtime, error = _context(api, rule_id, language)
    if error:
        return error
    character, choices = _payload(body)
    return {
        "ok": True,
        "rule_id": rule.rule_id,
        "character": runtime.apply_advancement(rule, character, choices),
    }


def _card_context(api: "WebAPI", card_id: str):
    from src.webui.services.character_cards import _dedupe_cards, _read_cards
    from src.webui.services.ruleset_characters import runtime_for_card

    cards = _dedupe_cards(_read_cards(api))
    for index, card in enumerate(cards):
        if str(card.get("id") or "") != card_id:
            continue
        rule_id = str(card.get("rule_id") or "").strip()
        language = str(card.get("language") or "")
        rule = api._load_rule_by_id(rule_id, language)
        runtime = runtime_for_card(api._ruleset_character_dependencies, card)
        if rule is None or runtime is None:
            return cards, index, card, None, None, {
                "ok": False,
                "code": "RULESET_RUNTIME_UNAVAILABLE",
                "error": "角色卡绑定的专业规则不可用",
            }
        if not all(
            callable(getattr(runtime, name, None))
            for name in ("preview_advancement", "apply_advancement")
        ):
            return cards, index, card, rule, runtime, {
                "ok": False,
                "code": "RULESET_ADVANCEMENT_UNAVAILABLE",
                "error": "该规则尚未提供专业升级流程",
            }
        return cards, index, card, rule, runtime, None
    return cards, -1, None, None, None, {
        "ok": False,
        "code": "CHARACTER_NOT_FOUND",
        "error": f"角色卡不存在: {card_id}",
    }


def _entity_choices(body: Any) -> dict[str, Any]:
    parsed = validate_draft_shape(body)
    choices = parsed.get("choices", {})
    if not isinstance(choices, dict):
        raise ValueError("advancement choices must be a JSON object")
    return choices


def preview_card(api: "WebAPI", card_id: str, body: Any) -> dict[str, Any]:
    _cards, _index, card, rule, runtime, error = _card_context(api, card_id)
    if error:
        return error
    choices = _entity_choices(body)
    return {
        "ok": True,
        "rule_id": rule.rule_id,
        "card_id": card_id,
        "revision": int(card.get("ruleset_revision", 0) or 0),
        "advancement": runtime.preview_advancement(rule, card, choices),
    }


def apply_card(api: "WebAPI", card_id: str, body: Any) -> dict[str, Any]:
    from src.webui.services.character_cards import _write_cards

    cards, index, card, rule, runtime, error = _card_context(api, card_id)
    if error:
        return error
    parsed = validate_draft_shape(body)
    choices = _entity_choices(parsed)
    operation_id = str(parsed.get("operation_id") or "").strip()
    if not operation_id or len(operation_id) > 160:
        return {
            "ok": False,
            "code": "INVALID_OPERATION_ID",
            "error": "升级操作必须提供有效的 operation_id",
        }
    revision = int(card.get("ruleset_revision", 0) or 0)
    operation_log = card.get("ruleset_operation_log")
    operation_log = deepcopy(operation_log) if isinstance(operation_log, list) else []
    previous = next(
        (
            entry for entry in operation_log
            if isinstance(entry, dict) and entry.get("operation_id") == operation_id
        ),
        None,
    )
    if previous is not None:
        return {
            "ok": True,
            "rule_id": rule.rule_id,
            "card_id": card_id,
            "revision": revision,
            "duplicate": True,
            "character": deepcopy(card),
            "card": deepcopy(card),
        }
    raw_expected = parsed.get("expected_revision")
    if isinstance(raw_expected, bool):
        raw_expected = None
    try:
        expected_revision = int(raw_expected)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "code": "INVALID_CHARACTER_REVISION",
            "error": "升级操作必须提供有效的 expected_revision",
        }
    if expected_revision != revision:
        return {
            "ok": False,
            "code": "STALE_CHARACTER_REVISION",
            "error": "角色卡已在其他位置更新，请刷新后重试",
            "revision": revision,
        }

    # Re-run the authoritative next-level preview at commit time. Besides
    # validating choices, this makes level 20 and stale UI submissions a
    # normal client error instead of an unhandled exception.
    try:
        readiness = runtime.preview_advancement(rule, card, choices)
    except (ProgressionCatalogError, ValueError) as exc:
        return {
            "ok": False, "code": "ADVANCEMENT_NOT_READY", "error": str(exc),
            "revision": revision,
        }
    if not readiness.get("ok"):
        return {
            "ok": False,
            "code": "ADVANCEMENT_NOT_READY",
            "error": "; ".join(str(item) for item in readiness.get("errors") or [])
            or "character cannot advance at this time",
            "revision": revision,
        }
    advanced = runtime.apply_advancement(rule, card, choices)
    updated = deepcopy(card)
    updated.update(advanced)
    updated["id"] = card_id
    updated["schema_version"] = max(2, int(card.get("schema_version", 2) or 2))
    updated["ruleset_revision"] = revision + 1
    operation_log.append({
        "operation_id": operation_id,
        "kind": "advancement",
        "revision": revision + 1,
    })
    updated["ruleset_operation_log"] = operation_log[-32:]
    cards[index] = updated
    _write_cards(api, cards)
    return {
        "ok": True,
        "rule_id": rule.rule_id,
        "card_id": card_id,
        "revision": revision + 1,
        "duplicate": False,
        "character": deepcopy(updated),
        "card": deepcopy(updated),
    }


def _live_context(api: "WebAPI", game_key: str, user_id: str):
    instance = api._reg.get(api._parse_key(game_key))
    if instance is None:
        return None, None, None, None, {
            "ok": False, "code": "GAME_NOT_FOUND", "error": "游戏不存在",
        }
    if user_id not in instance.players:
        return instance, None, None, None, {
            "ok": False, "code": "CHARACTER_NOT_FOUND", "error": "角色不存在",
        }
    rule = api._load_rule_for_game(instance)
    if rule is None:
        return instance, None, None, None, {
            "ok": False, "code": "RULE_NOT_FOUND", "error": "当前游戏规则不存在",
        }
    try:
        runtime = api._ruleset_registry.resolve(rule.template)
    except (AttributeError, TypeError, ValueError) as exc:
        return instance, rule, None, None, {
            "ok": False, "code": "RULESET_RUNTIME_UNAVAILABLE", "error": str(exc),
        }
    if not all(
        callable(getattr(runtime, name, None))
        for name in ("preview_advancement", "apply_advancement")
    ):
        return instance, rule, runtime, None, {
            "ok": False,
            "code": "RULESET_ADVANCEMENT_UNAVAILABLE",
            "error": "该规则尚未提供专业升级流程",
        }
    return instance, rule, runtime, instance.get_character_sheet(user_id), None


def preview_live(
    api: "WebAPI", game_key: str, user_id: str, body: Any,
) -> dict[str, Any]:
    _instance, rule, runtime, character, error = _live_context(api, game_key, user_id)
    if error:
        return error
    choices = _entity_choices(body)
    advancement = runtime.preview_advancement(rule, character, choices)
    runtime_id = str((getattr(_instance, "ruleset_runtime", {}) or {}).get("id") or "")
    if runtime_id == "core:dnd2024":
        try:
            advancement_access.require_entitlement(
                _instance, user_id, int(advancement.get("to_level", 0) or 0),
            )
        except ValueError as exc:
            return {
                "ok": False, "code": "ADVANCEMENT_NOT_GRANTED", "error": str(exc),
                "revision": int(character.get("ruleset_revision", 0) or 0),
                "advancement_status": advancement_access.view(_instance),
            }
    return {
        "ok": True,
        "rule_id": rule.rule_id,
        "game_key": game_key,
        "user_id": user_id,
        "revision": int(character.get("ruleset_revision", 0) or 0),
        "advancement": advancement,
    }


async def apply_live(
    api: "WebAPI", game_key: str, user_id: str, body: Any,
) -> dict[str, Any]:
    instance, rule, runtime, character, error = _live_context(api, game_key, user_id)
    if error:
        return error
    parsed = validate_draft_shape(body)
    choices = _entity_choices(parsed)
    operation_id = str(parsed.get("operation_id") or "").strip()
    if not operation_id or len(operation_id) > 160:
        return {
            "ok": False, "code": "INVALID_OPERATION_ID",
            "error": "升级操作必须提供有效的 operation_id",
        }
    revision = int(character.get("ruleset_revision", 0) or 0)
    raw_log = character.get("ruleset_operation_log")
    operation_log = deepcopy(raw_log) if isinstance(raw_log, list) else []
    previous = next((
        entry for entry in operation_log
        if isinstance(entry, dict) and entry.get("operation_id") == operation_id
    ), None)
    if previous is not None:
        if previous.get("kind") != "advancement":
            return {
                "ok": False, "code": "OPERATION_ID_REUSED",
                "error": "operation_id 已被其他角色操作使用，请重试",
            }
        return {
            "ok": True, "rule_id": rule.rule_id, "game_key": game_key,
            "user_id": user_id, "revision": revision, "duplicate": True,
            "character": deepcopy(character),
        }
    raw_expected = parsed.get("expected_revision")
    if isinstance(raw_expected, bool):
        raw_expected = None
    try:
        expected_revision = int(raw_expected)
    except (TypeError, ValueError):
        return {
            "ok": False, "code": "INVALID_CHARACTER_REVISION",
            "error": "升级操作必须提供有效的 expected_revision",
        }
    if expected_revision != revision:
        return {
            "ok": False, "code": "STALE_CHARACTER_REVISION",
            "error": "角色已在其他位置更新，请刷新后重试", "revision": revision,
        }

    try:
        readiness = runtime.preview_advancement(rule, character, choices)
    except (ProgressionCatalogError, ValueError) as exc:
        return {
            "ok": False, "code": "ADVANCEMENT_NOT_READY", "error": str(exc),
            "revision": revision,
        }
    if not readiness.get("ok"):
        return {
            "ok": False,
            "code": "ADVANCEMENT_NOT_READY",
            "error": "; ".join(str(item) for item in readiness.get("errors") or [])
            or "character cannot advance at this time",
            "revision": revision,
        }
    runtime_id = str((getattr(instance, "ruleset_runtime", {}) or {}).get("id") or "")
    if runtime_id == "core:dnd2024":
        try:
            advancement_access.require_entitlement(
                instance, user_id, int(readiness.get("to_level", 0) or 0),
            )
        except ValueError as exc:
            return {
                "ok": False, "code": "ADVANCEMENT_NOT_GRANTED", "error": str(exc),
                "revision": revision,
            }
    advanced = runtime.apply_advancement(rule, character, choices)
    updated = deepcopy(character)
    updated.update(advanced)
    updated["ruleset_revision"] = revision + 1
    operation_log.append({
        "operation_id": operation_id, "kind": "advancement", "revision": revision + 1,
    })
    updated["ruleset_operation_log"] = operation_log[-32:]
    before_player = deepcopy(instance.players[user_id])
    before_advancement = advancement_access.snapshot(instance) if runtime_id == "core:dnd2024" else None
    try:
        if runtime_id == "core:dnd2024":
            advancement_access.consume(instance, user_id, int(readiness.get("to_level", 0) or 0))
        instance.set_character_sheet(user_id, updated)
        if runtime_id == "core:dnd2024":
            advancement_access.reconcile_after_level_up(instance, user_id)
        await api._reg.save(instance)
    except Exception:
        instance.players[user_id] = before_player
        if before_advancement is not None:
            instance.ruleset_state["advancement"] = before_advancement
        raise
    return {
        "ok": True, "rule_id": rule.rule_id, "game_key": game_key,
        "user_id": user_id, "revision": revision + 1, "duplicate": False,
        "character": deepcopy(updated),
        "advancement_status": advancement_access.view(instance) if runtime_id == "core:dnd2024" else None,
    }


def live_status(api: "WebAPI", game_key: str) -> dict[str, Any]:
    instance = api._reg.get(api._parse_key(game_key))
    if not instance:
        return {"ok": False, "code": "GAME_NOT_FOUND", "error": "游戏不存在"}
    runtime_id = str((getattr(instance, "ruleset_runtime", {}) or {}).get("id") or "")
    if runtime_id != "core:dnd2024":
        return {"ok": False, "code": "RULESET_ADVANCEMENT_UNAVAILABLE", "error": "当前规则不支持该升级控制"}
    return {"ok": True, "advancement": advancement_access.view(instance)}


async def control_live(api: "WebAPI", game_key: str, body: Any) -> dict[str, Any]:
    instance = api._reg.get(api._parse_key(game_key))
    if not instance:
        return {"ok": False, "code": "GAME_NOT_FOUND", "error": "游戏不存在"}
    runtime_id = str((getattr(instance, "ruleset_runtime", {}) or {}).get("id") or "")
    if runtime_id != "core:dnd2024":
        return {"ok": False, "code": "RULESET_ADVANCEMENT_UNAVAILABLE", "error": "当前规则不支持该升级控制"}
    parsed = validate_draft_shape(body)
    action = str(parsed.get("action") or "").strip().casefold()
    try:
        if action == "configure":
            advancement_access.configure(
                instance, str(parsed.get("mode") or ""), str(parsed.get("authority") or ""),
            )
        elif action == "grant":
            user_id = str(parsed.get("user_id") or "").strip()
            targets = list(instance.alive_players) if user_id == "all" else [user_id]
            if not targets:
                return {"ok": False, "code": "CHARACTER_NOT_FOUND", "error": "没有可发放升级资格的角色"}
            for target in targets:
                advancement_access.grant(instance, target, source="gm")
        elif action == "award_xp":
            if advancement_access.view(instance)["mode"] != "xp":
                return {"ok": False, "code": "INVALID_ADVANCEMENT_MODE", "error": "当前不是 XP 升级模式"}
            user_id = str(parsed.get("user_id") or "").strip()
            targets = list(instance.alive_players) if user_id == "all" else [user_id]
            try:
                amount = int(parsed.get("amount"))
            except (TypeError, ValueError):
                return {"ok": False, "code": "INVALID_XP_REWARD", "error": "请填写有效的 XP 奖励"}
            for target in targets:
                advancement_access.award_xp(instance, target, amount, source="gm")
        else:
            return {"ok": False, "code": "INVALID_ADVANCEMENT_ACTION", "error": "未知升级控制操作"}
    except ValueError as exc:
        return {"ok": False, "code": "INVALID_ADVANCEMENT_ACTION", "error": str(exc)}
    await api._reg.save(instance)
    return {"ok": True, "advancement": advancement_access.view(instance)}
