"""角色管理服务：角色列表 / 规则属性辅助 / 角色CRUD / 建卡。"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.engine.character_utils import (
    build_starter_items,
    calc_hp_from_rule,
    initial_special_stat_value,
    make_default_character,
    normalize_character_sheet,
)
from src.content.worlds import localize_lorebook_entries
from src.engine.language import localized_text
from src.engine.health import record_health_event
from src.engine.economy import resolve_proposal
from src.commands.state_items import grant_classified_item
from src.rulesets.contracts import GameDetailProjectionRuntime
from src.webui.character_contracts import MAX_BIO_CHARS

if TYPE_CHECKING:
    from src.rulesets.registry import RulesetRuntimeRegistry

logger = logging.getLogger("trpg")


@dataclass(frozen=True)
class CharacterGameDependencies:
    get_instance: Callable[[tuple[str, ...]], Any | None]
    parse_game_key: Callable[[str], tuple[str, ...]]
    save_instance: Callable[[Any], Awaitable[None]]


@dataclass(frozen=True)
class CharacterRuleDependencies:
    rules_dir: Path | None
    load_rule_by_id: Callable[[str, str], Any | None]
    load_rule_for_game: Callable[[Any], Any | None]
    ruleset_registry: "RulesetRuntimeRegistry"


@dataclass(frozen=True)
class CharacterAssetDependencies:
    lorebook: Any | None
    load_world_template: Callable[[str, str], dict[str, Any] | None]
    avatar_file: Callable[[str], Path | None]
    generated_image_file: Callable[[str], Path | None]


@dataclass(frozen=True)
class CharacterDependencies:
    games: CharacterGameDependencies
    rules: CharacterRuleDependencies
    assets: CharacterAssetDependencies
    save_character_card: Callable[[dict[str, Any]], dict[str, Any]]

_ATTR_NAME_EN = {
    "str": "STR",
    "con": "CON",
    "dex": "DEX",
    "int": "INT",
    "edu": "EDU",
    "app": "APP",
    "pow": "POW",
    "siz": "SIZ",
    "wis": "WIS",
    "cha": "CHA",
}

_ATTR_NAME_ZH = {
    "str": "力量",
    "con": "体质",
    "dex": "敏捷",
    "int": "智力",
    "edu": "教育",
    "app": "外貌",
    "pow": "意志",
    "siz": "体型",
    "wis": "感知",
    "cha": "魅力",
}


def _normalize_skills(skills: list, rule=None) -> list[dict]:
    """规范化技能列表：字符串转为含数值的对象格式。"""
    base_values: dict[str, int] = rule.skill_base_values if rule else {}
    result: list[dict] = []
    for s in skills:
        if isinstance(s, str):
            result.append({"name": s, "value": base_values.get(s, 20)})
        elif isinstance(s, dict):
            name = s.get("name", "")
            result.append({
                "name": name,
                "value": s.get("value", base_values.get(name, 20)),
            })
    return result


def _format_rule_attr(attr: dict) -> dict:
    key = attr["key"]
    name = attr.get("name") or _ATTR_NAME_ZH.get(key, key)
    name_en = attr.get("name_en") or _ATTR_NAME_EN.get(key, key.upper())
    return {
        "key": key,
        "name": name,
        "name_en": name_en,
        "display_name": attr.get("display_name") or (f"{name} ({name_en})" if name_en else name),
        "min": attr.get("min", 3),
        "max": attr.get("max", 18),
    }


def _fallback_rule_attrs() -> list[dict[str, Any]]:
    return [
        _format_rule_attr({"key": key, "name": name, "min": 3, "max": 18})
        for key, name in [
            ("str", "力量"), ("dex", "敏捷"), ("con", "体质"),
            ("int", "智力"), ("wis", "感知"), ("cha", "魅力"),
        ]
    ]


def _fallback_rule_meta() -> dict[str, Any]:
    return {
        "dice_system": "d20",
        "rule_id": "",
        "mechanics": "freeform_d20_core",
        "hp_formula": "",
        "auto_hp": False,
        "attr_hint": "",
        "skill_mode": "narrative",
        "skill_hint": "",
        "max_skills": 3,
        "skill_point_total": 0,
        "max_skill_value": 0,
        "skill_point_spend_mode": "total_value",
        "skill_pools": {},
        "skill_base_values": {},
        "currency": "金币",
        "conflict_model": {"type": "hp_based"},
        "currency_system": {"base_unit": "unit", "units": [{"id": "unit", "name": "金币", "rate": 1}]},
        "resource_schema": [{"key": "hp", "label": "生命", "min": 0}],
        "identity_schema": [
            {"key": "origin", "label": "种族", "type": "text", "legacy_field": "race"},
            {"key": "archetype", "label": "职业", "type": "text", "legacy_field": "class"},
            {"key": "background", "label": "背景", "type": "text", "legacy_field": "background"},
        ],
        "progression_schema": {"type": "xp_level"},
        "ui_schema": {
            "primary_resources": ["hp"],
            "secondary_resources": [],
            "identity_labels": {"origin": "种族", "archetype": "职业", "background": "背景"},
            "show_level": True,
            "show_xp": True,
            "currency_label": "金币",
            "equipment_label": "装备",
        },
    }


def _character_schema_for_rule(rule) -> dict[str, Any]:
    """Build the one character-creation contract used with and without a game."""
    if not rule:
        return {
            "rule_attrs": _fallback_rule_attrs(),
            "rule_attrs_total": 60,
            "rule_classes": ["战士", "法师", "游侠", "盗贼", "牧师", "冒险者"],
            "rule_special_stats": [],
            "rule_meta": _fallback_rule_meta(),
            "skill_pool": [],
        }
    meta = {
        "dice_system": rule.dice_system,
        "rule_id": rule.rule_id,
        "rule_name": rule.rule_name,
        "rule_version": str(rule.template.get("rule_version") or ""),
        "mechanics": rule.mechanics,
        "hp_formula": rule.hp_formula,
        "auto_hp": rule.mechanics == "coc7e_core",
        "attr_hint": rule.attr_hint,
        "skill_mode": rule.skill_mode,
        "skill_hint": rule.skill_hint,
        "max_skills": rule.max_skills,
        "skill_point_total": rule.skill_point_total,
        "max_skill_value": rule.max_skill_value,
        "skill_point_spend_mode": rule.skill_point_spend_mode,
        "skill_pools": rule.skill_pools,
        "skill_base_values": rule.skill_base_values,
        "currency": rule.currency,
        "conflict_model": rule.conflict_model,
        "currency_system": rule.currency_system,
        "resource_schema": rule.resource_schema,
        "identity_schema": rule.identity_schema,
        "progression_schema": rule.progression_schema,
        "ui_schema": rule.ui_schema,
    }
    explicit_skill_pool = rule.template.get("skill_pool")
    legacy_skills = rule.template.get("skills")
    if isinstance(explicit_skill_pool, list):
        skill_pool = list(explicit_skill_pool)
    elif isinstance(legacy_skills, list):
        skill_pool = list(legacy_skills)
    else:
        skill_pool = []
    if not skill_pool:
        # Standalone creation has no class selection context yet. Offer the
        # union of class pools so the same rule schema remains useful before a
        # game (and before the user has settled on an archetype).
        for class_pool in rule.skill_pools.values():
            for skill in class_pool:
                if skill not in skill_pool:
                    skill_pool.append(skill)
    return {
        "rule_attrs": [_format_rule_attr(attr) for attr in rule.attributes],
        "rule_attrs_total": rule.attribute_points,
        "rule_classes": rule.get_class_names(),
        "rule_special_stats": rule.special_stats,
        "rule_meta": meta,
        "skill_pool": skill_pool,
    }


def character_schema(
    dependencies: CharacterDependencies,
    rule_id: str,
    language: str = "",
) -> dict[str, Any]:
    """Return rule-driven creation fields without requiring a GameInstance."""
    rule = dependencies.rules.load_rule_by_id(rule_id, language)
    if not rule:
        return {"ok": False, "error": f"规则不存在: {rule_id}"}
    return {
        "ok": True,
        **_character_schema_for_rule(rule),
        "ruleset_runtime": dependencies.rules.ruleset_registry.describe(
            rule.template,
        ).to_dict(),
    }


def format_attribute_map(attributes: dict, rule_attrs: list[dict]) -> str:
    """按规则属性顺序格式化属性，中文界面同时显示中文名与英文 key。"""
    attr_by_key = {a["key"]: a for a in rule_attrs}
    keys = [a["key"] for a in rule_attrs]
    keys.extend(k for k in attributes if k not in attr_by_key)
    parts = []
    for key in keys:
        if key not in attributes:
            continue
        attr = _format_rule_attr(attr_by_key.get(key) or {"key": key})
        parts.append(f"{attr['display_name']}:{attributes[key]}")
    return " ".join(parts)


def list_characters(
    dependencies: CharacterDependencies,
    game_key: str,
) -> dict[str, Any]:
    inst = dependencies.games.get_instance(
        dependencies.games.parse_game_key(game_key),
    )
    if not inst:
        return {"players": [], "npcs": [], "rule_attrs": []}
    players = [{"user_id": uid, **p} for uid, p in inst.players.items()]
    rule_attrs = _get_rule_attrs_for_game(dependencies, inst)
    rule = dependencies.rules.load_rule_for_game(inst)
    for player in players:
        cs = player.get("character_sheet", {})
        normalize_character_sheet(cs, rule)
        cs["attributes_display"] = format_attribute_map(cs.get("attributes", {}), rule_attrs)
    npcs_by_name: dict[str, dict[str, Any]] = {}
    for nid, npc in inst.npcs.items():
        name = npc.get("character_name") or npc.get("name") or nid
        npcs_by_name[name] = {"npc_id": nid, **npc, "name": name}
    if dependencies.assets.lorebook and inst.world_id:
        entries = dependencies.assets.lorebook.list_entries(inst.world_id, "npc")
        world_data = dependencies.assets.load_world_template(
            inst.world_id,
            str(getattr(inst, "language", "") or ""),
        )
        lore_status = localized_text(
            getattr(inst, "language", ""),
            {"en": "Lorebook", "zh-CN": "世界书", "ja": "ワールドブック"},
        )
        for entry in localize_lorebook_entries(entries, world_data):
            name = entry.get("name", "")
            if not name or name in npcs_by_name:
                continue
            npcs_by_name[name] = {
                "npc_id": entry.get("id", name),
                "name": name,
                "character_name": name,
                "tier": entry.get("tier", ""),
                "status": lore_status,
                "relation": entry.get("relation", ""),
                "content": entry.get("content", ""),
                "portrait": entry.get("portrait"),
            }
    npcs = list(npcs_by_name.values())
    rule_attrs_total = _get_rule_attrs_total(dependencies, inst)
    result: dict[str, Any] = {
        "players": players,
        "npcs": npcs,
        "rule_attrs": rule_attrs,
        "rule_attrs_total": rule_attrs_total,
        "rule_classes": _get_rule_classes_for_game(dependencies, inst),
        "rule_special_stats": _get_rule_special_stats(dependencies, inst),
        "rule_meta": _get_rule_meta_for_game(dependencies, inst),
    }
    if rule is not None:
        runtime_metadata = dependencies.rules.ruleset_registry.describe(
            rule.template,
        ).to_dict()
        result["ruleset_runtime"] = runtime_metadata
        runtime = dependencies.rules.ruleset_registry.resolve(rule.template)
        if isinstance(runtime, GameDetailProjectionRuntime):
            result.update(runtime.game_detail_projection(inst))
    return result


def _get_rule_classes_for_game(
    dependencies: CharacterDependencies,
    inst: Any,
) -> list[str]:
    try:
        rule = dependencies.rules.load_rule_for_game(inst)
        if rule:
            return _character_schema_for_rule(rule)["rule_classes"]
    except Exception:
        logger.exception("读取规则职业失败: world_id=%s", inst.world_id)
    return ["战士", "法师", "游侠", "盗贼", "牧师", "冒险者"]


def _get_rule_attrs_for_game(
    dependencies: CharacterDependencies,
    inst: Any,
) -> list[dict]:
    try:
        rule = dependencies.rules.load_rule_for_game(inst)
        if rule:
            return _character_schema_for_rule(rule)["rule_attrs"]
    except Exception:
        logger.exception("读取规则属性失败: world_id=%s", inst.world_id)
    return _fallback_rule_attrs()


def _get_rule_attrs_total(dependencies: CharacterDependencies, inst: Any) -> int:
    try:
        rule = dependencies.rules.load_rule_for_game(inst)
        if rule:
            return _character_schema_for_rule(rule)["rule_attrs_total"]
    except Exception:
        logger.exception("读取规则属性点失败: world_id=%s", inst.world_id)
    return 60


def _get_rule_special_stats(
    dependencies: CharacterDependencies,
    inst: Any,
) -> list[dict]:
    try:
        rule = dependencies.rules.load_rule_for_game(inst)
        if rule:
            return _character_schema_for_rule(rule)["rule_special_stats"]
    except Exception:
        logger.exception("读取特殊属性失败: world_id=%s", inst.world_id)
    return []


def _get_rule_meta_for_game(
    dependencies: CharacterDependencies,
    inst: Any,
) -> dict[str, Any]:
    try:
        rule = dependencies.rules.load_rule_for_game(inst)
        if rule:
            return _character_schema_for_rule(rule)["rule_meta"]
    except Exception:
        logger.exception("读取规则建卡提示失败: world_id=%s", inst.world_id)
    return _fallback_rule_meta()


def get_character(
    dependencies: CharacterDependencies,
    game_key: str,
    user_id: str,
) -> dict[str, Any] | None:
    inst = dependencies.games.get_instance(
        dependencies.games.parse_game_key(game_key),
    )
    if not inst or user_id not in inst.players:
        return None
    player = inst.get_player(user_id) or {}
    character_sheet = player.get("character_sheet", {})
    normalize_character_sheet(
        character_sheet, dependencies.rules.load_rule_for_game(inst),
    )
    inst.set_character_sheet(user_id, character_sheet)
    return {"user_id": user_id, **(inst.get_player(user_id) or {})}


async def update_character(
    dependencies: CharacterDependencies,
    game_key: str,
    user_id: str,
    updates: dict,
) -> dict[str, Any]:
    inst = dependencies.games.get_instance(
        dependencies.games.parse_game_key(game_key),
    )
    if not inst or user_id not in inst.players:
        return {"ok": False, "error": "角色不存在"}
    rule = dependencies.rules.load_rule_for_game(inst)
    if rule is not None:
        runtime = dependencies.rules.ruleset_registry.resolve(rule.template)
        if getattr(runtime.capabilities, "character_lifecycle", "legacy") == "rules_aware":
            return {
                "ok": False,
                "error_code": "RULESET_CHARACTER_OPERATION_REQUIRED",
                "error": "专业规则角色不能使用旧版通用编辑接口",
            }
    updates = dict(updates)
    character_name = str(updates.pop("character_name", "")).strip()
    if character_name:
        inst.set_player_name(user_id, character_name)
    cs = inst.get_character_sheet(user_id)
    if "background" in updates and len(str(updates.get("background", ""))) > MAX_BIO_CHARS:
        return {"ok": False, "error": f"角色背景过长（上限 {MAX_BIO_CHARS} 字）"}
    rule = dependencies.rules.load_rule_for_game(inst)
    if "portrait" in updates:
        try:
            portrait = _validated_portrait(
                dependencies.assets, updates.pop("portrait"),
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        if portrait is None:
            cs.pop("portrait", None)
        else:
            cs["portrait"] = portrait
    explicit_hp_update = (
        "hp" in updates
        or "max_hp" in updates
        or (
            isinstance(updates.get("resources"), dict)
            and isinstance(updates.get("resources", {}).get("hp"), dict)
        )
    )
    # 消耗属性点
    new_attrs = updates.get("attributes")
    old_attrs = cs.get("attributes", {})
    pool = cs.get("level_up_points", 0)
    if isinstance(new_attrs, dict) and pool > 0 and isinstance(old_attrs, dict):
        used = sum(max(0, int(new_attrs.get(k, 0)) - int(old_attrs.get(k, 0)))
                   for k in set(old_attrs) | set(new_attrs))
        updates["level_up_points"] = max(0, pool - used)
    cs.update(updates)
    # 确保 attr_points_max 不低于当前属性总和，避免升级后编辑界面卡上线
    try:
        cur_attrs = cs.get("attributes", {})
        if isinstance(cur_attrs, dict) and cur_attrs:
            total = sum(int(v) for v in cur_attrs.values())
            stored = cs.get("attr_points_max", 0)
            if total > stored:
                cs["attr_points_max"] = total
                logger.info("attr_points_max 修正: %d -> %d (uid=%s)", stored, total, user_id)
    except (TypeError, ValueError):
        logger.warning("attr_points_max 自动修正失败: uid=%s", user_id, exc_info=True)
    # 规范化技能格式
    if "skills" in updates:
        cs["skills"] = _normalize_skills(updates.get("skills", []), rule)
    # 属性变化后可按规则补算 HP；若用户明确手填 HP，则尊重手填值。
    new_attrs = updates.get("attributes")
    if isinstance(new_attrs, dict) and not explicit_hp_update:
        try:
            base_hp = (
                rule.calculate_hp(new_attrs, cs.get("class", ""))
                if rule
                else calc_hp_from_rule(
                    new_attrs,
                    rules_dir=dependencies.rules.rules_dir,
                    language=getattr(inst, "language", ""),
                )
            )
            lv_bonus = max(0, (cs.get("level", 1) - 1) * 5)
            new_hp = base_hp + lv_bonus
            curr_hp_ratio = cs.get("hp", 1) / max(1, cs.get("max_hp", 1))
            cs["max_hp"] = new_hp
            cs["hp"] = max(1, round(new_hp * curr_hp_ratio))
            logger.info("HP 重算: con=%s HP=%d->%d",
                new_attrs.get("con", "?"), cs.get("max_hp", 0), new_hp)
        except Exception as exc:
            logger.warning("属性变化后 HP 重算失败: %s", exc)
    normalize_character_sheet(cs, rule)
    inst.set_character_sheet(user_id, cs)
    await dependencies.games.save_instance(inst)
    try:
        dependencies.save_character_card({
            "character_name": inst.players[user_id].get("character_name", ""),
            "character_sheet": cs,
        })
    except Exception:
        logger.warning("角色卡同步入库失败: uid=%s", user_id, exc_info=True)
    return {"ok": True}


def _validated_portrait(
    dependencies: CharacterAssetDependencies,
    portrait: Any,
) -> dict[str, str] | None:
    # Existing saves use an empty object as "no explicit portrait". Treat it
    # exactly like null so editing unrelated profile fields remains possible.
    if portrait is None or portrait == {}:
        return None
    if not isinstance(portrait, dict):
        raise ValueError("头像数据无效")
    kind = str(portrait.get("kind") or "")
    if kind == "builtin":
        portrait_id = str(portrait.get("id") or "")
        if not portrait_id or len(portrait_id) > 100:
            raise ValueError("内置头像编号无效")
        return {"kind": "builtin", "id": portrait_id}
    if kind == "upload":
        asset_id = str(portrait.get("asset_id") or "")
        if not asset_id or dependencies.avatar_file(asset_id) is None:
            raise ValueError("上传头像不存在")
        return {"kind": "upload", "asset_id": asset_id}
    if kind == "generated":
        asset_id = str(portrait.get("asset_id") or "")
        if not asset_id or dependencies.generated_image_file(asset_id) is None:
            raise ValueError("生成头像不存在")
        return {"kind": "generated", "asset_id": asset_id}
    raise ValueError("头像类型无效")


async def update_npc_portrait(
    dependencies: CharacterDependencies,
    game_key: str,
    npc_id: str,
    portrait: Any,
) -> dict[str, Any]:
    inst = dependencies.games.get_instance(
        dependencies.games.parse_game_key(game_key),
    )
    if not inst:
        return {"ok": False, "error": "游戏不存在"}
    npc_key = str(npc_id or "").strip()
    if not npc_key:
        return {"ok": False, "error": "NPC 不存在"}
    npc = inst.npcs.get(npc_key)
    if npc is None:
        for key, candidate in inst.npcs.items():
            if str(candidate.get("id") or candidate.get("npc_id") or "") == npc_key:
                npc_key, npc = key, candidate
                break
    if npc is None and dependencies.assets.lorebook and inst.world_id:
        entry = dependencies.assets.lorebook.get_entry(npc_key)
        if entry and entry.get("world_id") == inst.world_id and entry.get("type") == "npc":
            world_data = dependencies.assets.load_world_template(
                inst.world_id,
                str(getattr(inst, "language", "") or ""),
            )
            entry = localize_lorebook_entries([entry], world_data)[0]
            name = str(entry.get("name") or npc_key)
            npc = {
                "name": name,
                "character_name": name,
                "tier": entry.get("tier", ""),
            }
            inst.npcs[npc_key] = npc
    if npc is None:
        return {"ok": False, "error": "NPC 不存在"}
    try:
        normalized = _validated_portrait(dependencies.assets, portrait)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if normalized is None:
        npc.pop("portrait", None)
    else:
        npc["portrait"] = normalized
    await dependencies.games.save_instance(inst)
    return {"ok": True, "portrait": npc.get("portrait")}


async def resolve_payment(
    dependencies: CharacterDependencies,
    game_key: str,
    payment_id: str,
    accepted: bool,
    session_uid: str = "",
) -> dict[str, Any]:
    inst = dependencies.games.get_instance(
        dependencies.games.parse_game_key(game_key),
    )
    if not inst:
        return {"ok": False, "error": "游戏不存在"}
    actor_uid = str(session_uid or "")

    def grant_reward(sheet: dict[str, Any], reward: dict[str, Any]) -> None:
        item_name = str(reward.get("name") or "").strip()
        if item_name:
            grant_classified_item(sheet, item_name, str(reward.get("category") or ""))

    async with inst._lock:
        result = resolve_proposal(
            inst,
            payment_id,
            actor_uid=actor_uid,
            accepted=bool(accepted),
            grant_reward=grant_reward,
        )
    # Insufficient funds changes the proposal to rejected, so persist both
    # successful resolutions and terminal business failures.
    if result.get("ok") or result.get("code") == "INSUFFICIENT_FUNDS":
        await dependencies.games.save_instance(inst)
    if not result.get("ok"):
        return result
    proposal = result.get("proposal") or {}
    uid = str(proposal.get("payer_uid") or proposal.get("recipient_uid") or "")
    amount = int(proposal.get("amount", 0) or 0)
    name = inst.players.get(uid, {}).get("character_name", uid)
    awaiting_party = bool(accepted and result.get("committed") is False)
    record_health_event(
        inst,
        component="economy",
        code=(
            "economy_approved"
            if awaiting_party
            else "economy_committed"
            if accepted
            else "economy_declined"
        ),
        severity="info",
        title="经济提案已处理",
        message=(
            f"{name} 已确认，等待其他队员：{proposal.get('reason') or amount}"
            if awaiting_party
            else f"{name} {'确认' if accepted else '拒绝'}：{proposal.get('reason') or amount}"
        ),
    )
    await dependencies.games.save_instance(inst)
    return {**result, "payment": proposal}


async def delete_character(
    dependencies: CharacterDependencies,
    game_key: str,
    user_id: str,
) -> dict[str, Any]:
    inst = dependencies.games.get_instance(
        dependencies.games.parse_game_key(game_key),
    )
    if not inst or user_id not in inst.players:
        return {"ok": False, "error": "角色不存在"}
    if len(inst.players) <= 1:
        return {"ok": False, "error": "至少保留一个角色，无法删除最后一个"}
    name = inst.players[user_id].get("character_name", user_id)
    removed = await inst.remove_player(user_id)
    if not removed:
        return {"ok": False, "error": "角色不存在"}
    inst.remove_payments_for_player(user_id)
    inst.clear_private_messages(user_id)
    await dependencies.games.save_instance(inst)
    logger.info("角色已删除: %s (%s)", name, game_key)
    return {"ok": True}


async def create_player(dependencies: CharacterDependencies, game_key: str, character: dict,
                       force_uid: str = "", assign_new_id: bool = False) -> dict[str, Any]:
    inst = dependencies.games.get_instance(
        dependencies.games.parse_game_key(game_key),
    )
    if not inst:
        return {"ok": False, "error": "游戏不存在"}
    requested_uid = str(character.get("user_id") or "").strip()
    if requested_uid and requested_uid in inst.players:
        return {
            "ok": True,
            "user_id": requested_uid,
            "character_name": inst.players[requested_uid].get("character_name", requested_uid),
            "reused": True,
        }
    # uid 决策：GM 代建(assign_new_id)生成独立 uid；否则优先 force_uid（session 身份）或显式 requested_uid
    if assign_new_id:
        uid = "player_" + str(time.time_ns())[-12:]
    elif force_uid:
        if force_uid in inst.players:
            return {"ok": True, "user_id": force_uid,
                    "character_name": inst.players[force_uid].get("character_name", force_uid),
                    "reused": True}
        uid = force_uid
    elif requested_uid:
        uid = requested_uid
    else:
        uid = "player_" + str(time.time_ns())[-12:]
    max_players = max(1, int(getattr(inst, "max_players", 6) or 6))
    if uid not in inst.players and len(inst.players) >= max_players:
        return {
            "ok": False,
            "error": f"房间已满（最多 {max_players} 人）",
            "error_code": "game_room_full",
        }
    rule = dependencies.rules.load_rule_for_game(inst)
    rule_id = rule.rule_id if rule else "freeform_fantasy"
    professional_character = False
    if rule is not None:
        runtime = dependencies.rules.ruleset_registry.resolve(rule.template)
        professional_character = runtime.capabilities.character_builder == "professional"
        if professional_character:
            try:
                character = runtime.normalize_character_submission(
                    rule, character, getattr(inst, "language", ""),
                )
            except ValueError as exc:
                return {
                    "ok": False,
                    "error_code": "INVALID_PROFESSIONAL_CHARACTER",
                    "error": str(exc),
                }
            canonical = character.get("ruleset_character")
            binding = canonical.get("rule_binding") if isinstance(canonical, dict) else None
            if not isinstance(binding, dict) or not inst.bind_ruleset_runtime(binding):
                return {
                    "ok": False,
                    "error_code": "INCOMPATIBLE_RULESET_CHARACTER",
                    "error": "角色与当前游戏的专业规则版本不兼容",
                }
    # 仅传了名字的轻量加入会自动生成默认角色卡。
    has_full_sheet = bool(character.get("attributes") or character.get("equipment") or character.get("skills"))
    if not has_full_sheet:
        name = character.get("name") or character.get("character_name") or "冒险者"
        try:
            templates_base = (
                dependencies.rules.rules_dir.parent
                if dependencies.rules.rules_dir
                else None
            )
            character = make_default_character(name, rule_id or "freeform_fantasy", templates_base, language=getattr(inst, "language", ""))
            character["character_name"] = name
        except Exception:
            logger.exception("生成默认角色卡失败: %s", name)
    attrs = character.get("attributes", {})
    rule_attrs = _get_rule_attrs_for_game(dependencies, inst)
    total_points = sum(int(attrs.get(r["key"], 10)) for r in rule_attrs) if rule_attrs else 60
    default_weapons = [{"name": "徒手", "type": "weapon", "damage": 2, "slot": "main_hand", "quality": "common"}]
    hp = character.get("hp")
    max_hp = character.get("max_hp")
    if hp is None or max_hp is None:
        hp = (
            rule.calculate_hp(attrs, character.get("class", ""))
            if rule
            else calc_hp_from_rule(
                attrs,
                rule_id,
                dependencies.rules.rules_dir,
                character.get("class", ""),
                language=getattr(inst, "language", ""),
            )
        )
        max_hp = hp
    default_class = rule.classes[0]["name"] if (rule and rule.classes) else "冒险者"
    if len(str(character.get("background", ""))) > MAX_BIO_CHARS:
        return {"ok": False, "error": f"角色背景过长（上限 {MAX_BIO_CHARS} 字）"}
    starter_equip, starter_inv = build_starter_items(rule, character.get("class") or default_class)
    cs = {
        "race": character.get("race", "人类"),
        "class": character.get("class") or default_class,
        "identity": character.get("identity", {}),
        "level": 1, "xp": 0,
        "attributes": attrs,
        "hp": hp, "max_hp": max_hp,
        "equipment": character.get("equipment") or starter_equip or default_weapons,
        "inventory": character.get("inventory") or starter_inv,
        "key_items": character.get("key_items", []),
        "skills": _normalize_skills(character.get("skills", []), rule),
        "background": character.get("background", ""),
        "deceased": False,
        "gold": character.get("gold", 30),
        "currency": character.get("currency", {}),
        "portrait": character.get("portrait", {}),
        "attr_points_max": total_points,
    }
    if professional_character:
        cs["rule_binding"] = deepcopy(character["rule_binding"])
        cs["ruleset_character"] = deepcopy(character["ruleset_character"])
        cs["armor_class"] = int(character.get("armor_class", 10) or 10)
    # 初始化 special_stats（理智值/幸运值/内力等）
    try:
        if rule:
            for ss in rule.special_stats:
                max_val = ss.get("max", 99)
                init_val = initial_special_stat_value(ss, attrs)
                cs[ss["key"]] = init_val
                cs[f"max_{ss['key']}"] = max_val
    except Exception as exc:
        logger.exception("初始化特殊属性失败: %s", exc)
    normalize_character_sheet(cs, rule)
    player = {
        "character_name": character.get("character_name") or character.get("name") or "冒险者",
        "character_sheet": cs,
    }
    inst.put_player(uid, player)
    dependencies.save_character_card({
        **player,
        "rule_id": rule_id,
        "rule_name": rule.rule_name if rule else rule_id,
        "rule_version": str(rule.template.get("rule_version") or "") if rule else "",
        "mechanics": rule.mechanics if rule else "",
        "language": getattr(inst, "language", ""),
    })
    await dependencies.games.save_instance(inst)
    return {"ok": True, "user_id": uid, "character_name": player["character_name"]}
