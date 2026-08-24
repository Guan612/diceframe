"""Stateless Web/API boundary for professional ruleset advancement."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from src.webui.services.ruleset_builder import validate_draft_shape

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
        runtime = runtime_for_card(api, card)
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
    return {
        "ok": True,
        "rule_id": rule.rule_id,
        "game_key": game_key,
        "user_id": user_id,
        "revision": int(character.get("ruleset_revision", 0) or 0),
        "advancement": runtime.preview_advancement(rule, character, choices),
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

    advanced = runtime.apply_advancement(rule, character, choices)
    updated = deepcopy(character)
    updated.update(advanced)
    updated["ruleset_revision"] = revision + 1
    operation_log.append({
        "operation_id": operation_id, "kind": "advancement", "revision": revision + 1,
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
        "character": deepcopy(updated),
    }
