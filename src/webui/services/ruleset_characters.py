"""Ruleset-authoritative character lifecycle operations.

Professional character mechanics live in ``ruleset_character``.  These
operations deliberately accept only non-mechanical profile data and rebuild
the legacy projection through the selected runtime before persisting once.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from src.webui.services.characters import MAX_BIO_CHARS, _validated_portrait

if TYPE_CHECKING:
    from src.webui.api import WebAPI


PROFILE_FIELDS = frozenset({
    "pronouns",
    "appearance",
    "personality",
    "backstory",
    "ideals",
    "bonds",
    "flaws",
    "notes",
})
PROFILE_PATCH_FIELDS = frozenset({"character_name", "portrait", "profile"})
MAX_CHARACTER_NAME_CHARS = 120


class RulesetCharacterOperationError(ValueError):
    """A user-facing ruleset character lifecycle validation failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _failure(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "error": message}


def _is_rules_aware(runtime: Any) -> bool:
    return getattr(runtime.capabilities, "character_lifecycle", "legacy") == "rules_aware"


def runtime_for_card(api: "WebAPI", card: dict[str, Any]) -> Any | None:
    """Resolve a card's runtime without matching translated names or rule IDs."""

    canonical = card.get("ruleset_character")
    binding = canonical.get("rule_binding") if isinstance(canonical, dict) else None
    if not isinstance(binding, dict):
        binding = card.get("rule_binding")
    if isinstance(binding, dict):
        runtime_id = str(binding.get("runtime_id") or "").strip()
        raw_version = binding.get("runtime_version", 1)
        if runtime_id:
            try:
                minimum_version = int(raw_version)
                return api._ruleset_registry.get(
                    runtime_id, minimum_version=max(1, minimum_version),
                )
            except (AttributeError, TypeError, ValueError):
                return None

    rule_id = str(card.get("rule_id") or "").strip()
    loader = getattr(api, "_load_rule_by_id", None)
    registry = getattr(api, "_ruleset_registry", None)
    if not rule_id or not callable(loader) or registry is None:
        return None
    rule = loader(rule_id, str(card.get("language") or ""))
    if rule is None:
        return None
    try:
        return registry.resolve(rule.template)
    except (AttributeError, TypeError, ValueError):
        return None


def card_has_rules_aware_lifecycle(api: "WebAPI", card: dict[str, Any]) -> bool:
    runtime = runtime_for_card(api, card)
    return runtime is not None and _is_rules_aware(runtime)


def runtime_metadata_for_card(api: "WebAPI", card: dict[str, Any]) -> dict[str, Any] | None:
    runtime = runtime_for_card(api, card)
    if runtime is None:
        return None
    canonical = card.get("ruleset_character")
    binding = canonical.get("rule_binding") if isinstance(canonical, dict) else None
    requested = 1
    if isinstance(binding, dict):
        try:
            requested = max(1, int(binding.get("runtime_version", 1)))
        except (TypeError, ValueError):
            requested = 1
    return {
        "id": runtime.runtime_id,
        "version": runtime.runtime_version,
        "requested_minimum_version": requested,
        "capabilities": runtime.capabilities.to_dict(),
    }


def normalize_character_card_blueprint(
    api: "WebAPI", character: dict[str, Any],
) -> dict[str, Any]:
    """Validate and rebuild a professional card before it enters local storage.

    A display ``rule_id`` or runtime ID is never enough. The rule template must
    resolve to the same runtime, and that runtime rebuilds every mechanical
    value from canonical choices. Only validated profile/portrait data is
    reapplied afterward. Legacy and unbound cards keep their existing path.
    """

    if not isinstance(character, dict):
        raise RulesetCharacterOperationError(
            "INVALID_RULESET_CHARACTER", "角色卡必须是对象",
        )
    runtime = runtime_for_card(api, character)
    if runtime is None or not _is_rules_aware(runtime):
        return deepcopy(character)

    canonical = character.get("ruleset_character")
    binding = canonical.get("rule_binding") if isinstance(canonical, dict) else None
    if not isinstance(canonical, dict) or not isinstance(binding, dict):
        raise RulesetCharacterOperationError(
            "INVALID_RULESET_CHARACTER", "专业角色卡缺少可重建的权威规则数据",
        )
    rule_id = str(binding.get("rule_id") or character.get("rule_id") or "").strip()
    loader = getattr(api, "_load_rule_by_id", None)
    if not rule_id or not callable(loader):
        raise RulesetCharacterOperationError(
            "RULESET_NOT_FOUND", "专业角色卡没有可用的规则标识",
        )
    locale = str(canonical.get("locale") or character.get("language") or "")
    rule = loader(rule_id, locale)
    if rule is None:
        raise RulesetCharacterOperationError(
            "RULESET_NOT_FOUND", f"找不到专业角色卡使用的规则: {rule_id}",
        )
    try:
        selected_runtime = api._ruleset_registry.resolve(rule.template)
    except (AttributeError, TypeError, ValueError) as exc:
        raise RulesetCharacterOperationError(
            "RULESET_RUNTIME_UNAVAILABLE", str(exc),
        ) from exc
    if selected_runtime.runtime_id != runtime.runtime_id:
        raise RulesetCharacterOperationError(
            "INCOMPATIBLE_RULESET_CHARACTER", "角色卡规则与运行时绑定不一致",
        )
    try:
        normalized = runtime.normalize_character_submission(
            rule, deepcopy(character), locale,
        )
    except (TypeError, ValueError) as exc:
        raise RulesetCharacterOperationError(
            "INVALID_RULESET_CHARACTER", f"专业角色卡未通过规则校验: {exc}",
        ) from exc

    profile_patch: dict[str, Any] = {}
    source_profile = canonical.get("profile")
    if isinstance(source_profile, dict):
        profile_patch["profile"] = deepcopy(source_profile)
    # An empty portrait is the card schema's "use default" sentinel, not a
    # user-supplied portrait object that needs validation.
    if character.get("portrait") not in (None, {}):
        profile_patch["portrait"] = deepcopy(character.get("portrait"))
    if profile_patch:
        normalized, _name = _apply_profile(api, runtime, normalized, profile_patch)

    # Retain human-facing library metadata, never imported operation/revision
    # journals. A newly stored blueprint starts with a fresh entity revision.
    for key in (
        "id", "card_id", "source", "source_plugin", "plugin_content_id",
        "rule_id", "rule_name", "rule_version", "mechanics", "language",
    ):
        if key in character:
            normalized[key] = deepcopy(character[key])
    return normalized


def _validate_profile_patch(api: "WebAPI", patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise RulesetCharacterOperationError("INVALID_CHARACTER_PROFILE", "角色资料必须是对象")
    unknown = sorted(set(patch) - PROFILE_PATCH_FIELDS)
    if unknown:
        raise RulesetCharacterOperationError(
            "MECHANICAL_CHARACTER_FIELD_FORBIDDEN",
            f"角色资料接口不能修改规则字段: {', '.join(unknown)}",
        )

    result: dict[str, Any] = {}
    if "character_name" in patch:
        name = str(patch.get("character_name") or "").strip()
        if not name:
            raise RulesetCharacterOperationError("INVALID_CHARACTER_PROFILE", "角色名不能为空")
        if len(name) > MAX_CHARACTER_NAME_CHARS:
            raise RulesetCharacterOperationError(
                "INVALID_CHARACTER_PROFILE",
                f"角色名过长（上限 {MAX_CHARACTER_NAME_CHARS} 字）",
            )
        result["character_name"] = name

    if "portrait" in patch:
        try:
            result["portrait"] = _validated_portrait(api, patch.get("portrait"))
        except ValueError as exc:
            raise RulesetCharacterOperationError("INVALID_CHARACTER_PROFILE", str(exc)) from exc

    if "profile" in patch:
        raw_profile = patch.get("profile")
        if not isinstance(raw_profile, dict):
            raise RulesetCharacterOperationError("INVALID_CHARACTER_PROFILE", "角色资料字段必须是对象")
        unknown_profile = sorted(set(raw_profile) - PROFILE_FIELDS)
        if unknown_profile:
            raise RulesetCharacterOperationError(
                "INVALID_CHARACTER_PROFILE",
                f"不支持的角色资料字段: {', '.join(unknown_profile)}",
            )
        profile: dict[str, str] = {}
        total = 0
        for key, value in raw_profile.items():
            if not isinstance(value, str):
                raise RulesetCharacterOperationError(
                    "INVALID_CHARACTER_PROFILE", f"角色资料 {key} 必须是文本",
                )
            text = value.strip()
            total += len(text)
            profile[key] = text
        if total > MAX_BIO_CHARS:
            raise RulesetCharacterOperationError(
                "INVALID_CHARACTER_PROFILE",
                f"角色资料过长（合计上限 {MAX_BIO_CHARS} 字）",
            )
        result["profile"] = profile
    return result


def _apply_profile(
    api: "WebAPI",
    runtime: Any,
    current: dict[str, Any],
    patch: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    validated = _validate_profile_patch(api, patch)
    canonical = current.get("ruleset_character")
    if not isinstance(canonical, dict):
        raise RulesetCharacterOperationError(
            "INVALID_RULESET_CHARACTER", "专业角色缺少权威规则数据",
        )
    canonical = deepcopy(canonical)
    binding = canonical.get("rule_binding")
    if not isinstance(binding, dict) or str(binding.get("runtime_id") or "") != runtime.runtime_id:
        raise RulesetCharacterOperationError(
            "INCOMPATIBLE_RULESET_CHARACTER", "角色规则版本与当前运行时不兼容",
        )

    current_identity = canonical.get("identity")
    identity = deepcopy(current_identity) if isinstance(current_identity, dict) else {}
    name = str(identity.get("name") or current.get("character_name") or "").strip()
    if "character_name" in validated:
        name = validated["character_name"]
        identity["name"] = name
        canonical["identity"] = identity

    if "profile" in validated:
        current_profile = canonical.get("profile")
        profile = deepcopy(current_profile) if isinstance(current_profile, dict) else {}
        for key, value in validated["profile"].items():
            if value:
                profile[key] = value
            else:
                profile.pop(key, None)
        if profile:
            canonical["profile"] = profile
        else:
            canonical.pop("profile", None)

    try:
        projected = runtime.project_legacy_character(canonical)
    except (TypeError, ValueError) as exc:
        raise RulesetCharacterOperationError(
            "INVALID_RULESET_CHARACTER", f"角色规则数据无法投影: {exc}",
        ) from exc
    if not isinstance(projected, dict):
        raise RulesetCharacterOperationError(
            "INVALID_RULESET_CHARACTER", "角色规则投影结果无效",
        )

    updated = deepcopy(current)
    updated.update(projected)
    updated["rule_binding"] = deepcopy(binding)
    updated["ruleset_character"] = canonical
    updated["character_name"] = name
    if "portrait" in validated:
        portrait = validated["portrait"]
        if portrait is None:
            updated.pop("portrait", None)
        else:
            updated["portrait"] = portrait
    return updated, name


async def update_live_character_profile(
    api: "WebAPI", game_key: str, user_id: str, patch: dict[str, Any],
) -> dict[str, Any]:
    instance = api._reg.get(api._parse_key(game_key))
    if instance is None or user_id not in instance.players:
        return _failure("CHARACTER_NOT_FOUND", "角色不存在")
    rule = api._load_rule_for_game(instance)
    if rule is None:
        return _failure("RULESET_NOT_FOUND", "当前游戏规则不存在")
    try:
        runtime = api._ruleset_registry.resolve(rule.template)
    except (AttributeError, TypeError, ValueError) as exc:
        return _failure("RULESET_RUNTIME_UNAVAILABLE", str(exc))
    if not _is_rules_aware(runtime):
        return _failure("RULESET_CHARACTER_NOT_SUPPORTED", "当前规则不使用专业角色资料接口")

    before_player = deepcopy(instance.players[user_id])
    try:
        updated, name = _apply_profile(
            api, runtime, instance.get_character_sheet(user_id), patch,
        )
    except RulesetCharacterOperationError as exc:
        return _failure(exc.code, str(exc))

    instance.set_player_name(user_id, name)
    instance.set_character_sheet(user_id, updated)
    try:
        await api._reg.save(instance)
    except Exception:
        instance.players[user_id] = before_player
        raise
    return {"ok": True, "character": deepcopy(updated)}


async def adopt_character_card(
    api: "WebAPI", game_key: str, user_id: str, card_id: str,
) -> dict[str, Any]:
    """Replace one live professional character from a server-owned blueprint."""
    from src.webui.services.character_cards import _dedupe_cards, _read_cards

    instance = api._reg.get(api._parse_key(game_key))
    if instance is None or user_id not in instance.players:
        return _failure("CHARACTER_NOT_FOUND", "角色不存在")
    card = next(
        (
            item for item in _dedupe_cards(_read_cards(api))
            if str(item.get("id") or "") == str(card_id or "")
        ),
        None,
    )
    if card is None:
        return _failure("CHARACTER_NOT_FOUND", f"角色卡不存在: {card_id}")
    rule = api._load_rule_for_game(instance)
    if rule is None:
        return _failure("RULESET_NOT_FOUND", "当前游戏规则不存在")
    try:
        runtime = api._ruleset_registry.resolve(rule.template)
    except (AttributeError, TypeError, ValueError) as exc:
        return _failure("RULESET_RUNTIME_UNAVAILABLE", str(exc))
    card_runtime = runtime_for_card(api, card)
    if (
        not _is_rules_aware(runtime)
        or card_runtime is None
        or card_runtime.runtime_id != runtime.runtime_id
    ):
        return _failure("INCOMPATIBLE_RULESET_CHARACTER", "角色卡与当前专业规则不兼容")
    try:
        normalized = runtime.normalize_character_submission(
            rule, deepcopy(card), str(getattr(instance, "language", "") or ""),
        )
    except ValueError as exc:
        return _failure("INVALID_RULESET_CHARACTER", str(exc))
    canonical = normalized.get("ruleset_character")
    binding = canonical.get("rule_binding") if isinstance(canonical, dict) else None
    if not isinstance(binding, dict) or not instance.bind_ruleset_runtime(binding):
        return _failure("INCOMPATIBLE_RULESET_CHARACTER", "角色卡与当前存档规则版本不兼容")
    if isinstance(card.get("portrait"), dict):
        normalized["portrait"] = deepcopy(card["portrait"])
    name = str(normalized.get("character_name") or card.get("character_name") or "").strip()
    if not name:
        return _failure("INVALID_CHARACTER_PROFILE", "角色名不能为空")
    before_player = deepcopy(instance.players[user_id])
    instance.set_player_name(user_id, name)
    instance.set_character_sheet(user_id, normalized)
    try:
        await api._reg.save(instance)
    except Exception:
        instance.players[user_id] = before_player
        raise
    return {"ok": True, "character": deepcopy(normalized)}


def update_character_card_profile(
    api: "WebAPI", card_id: str, patch: dict[str, Any],
) -> dict[str, Any]:
    # Local import keeps the storage module independent from ruleset runtime code.
    from src.webui.services.character_cards import _dedupe_cards, _read_cards, _write_cards

    cards = _dedupe_cards(_read_cards(api))
    for index, card in enumerate(cards):
        if str(card.get("id") or "") != card_id:
            continue
        runtime = runtime_for_card(api, card)
        if runtime is None or not _is_rules_aware(runtime):
            return _failure(
                "RULESET_CHARACTER_NOT_SUPPORTED", "当前角色卡不使用专业角色资料接口",
            )
        try:
            updated, _name = _apply_profile(api, runtime, card, patch)
        except RulesetCharacterOperationError as exc:
            return _failure(exc.code, str(exc))
        updated["id"] = card_id
        updated["schema_version"] = max(2, int(card.get("schema_version", 2) or 2))
        cards[index] = updated
        _write_cards(api, cards)
        return {"ok": True, "card": deepcopy(updated)}
    return _failure("CHARACTER_NOT_FOUND", f"角色卡不存在: {card_id}")
