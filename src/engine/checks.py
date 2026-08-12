"""统一检定请求：从玩家行动生成规则无关的 CheckRequest，并完成原始掷骰。"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from src.engine.dice import roll
from src.engine.game_instance import GameInstance
from src.engine.language import localized_text
from src.rules.rule_system import RuleSystem

logger = logging.getLogger("trpg")


def _load_fallback_intents() -> dict:
    """加载全局兜底词表（数据驱动，支持多语言）。

    供没有自带 intents 词表的规则使用。放 templates/rules/fallback_intents.json：
    - intents: {intent_id: {aliases: {lang: [...]}, skill_candidates, default_attribute}}
    - generic_check_words: {lang: [...]} 通用检定词
    """
    path = Path(__file__).resolve().parents[2] / "templates" / "rules" / "fallback_intents.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("通用检定兜底词表加载失败: %s", exc)
        return {}


_FALLBACK_INTENTS: dict = _load_fallback_intents()


def _fallback_intent_specs(language: str) -> list[tuple[str, tuple[str, ...], tuple[str, ...], str]]:
    """兜底意图表（数据驱动），结构同旧 _INTENT_SPECS：[(intent, aliases, skills, attr)]。"""
    result: list[tuple[str, tuple[str, ...], tuple[str, ...], str]] = []
    intents = _FALLBACK_INTENTS.get("intents") or {}
    lang = localized_text(language, {"en": "en", "zh-CN": "zh-CN", "ja": "ja"})
    for intent, block in intents.items():
        aliases = block.get("aliases") or {}
        skills = block.get("skill_candidates") or {}
        alias_list = tuple(aliases.get(lang) or aliases.get("en") or aliases.get("zh-CN") or ())
        skill_list = tuple(skills.get(lang) or skills.get("en") or skills.get("zh-CN") or ())
        if not alias_list:
            continue
        result.append((intent, alias_list, skill_list, str(block.get("default_attribute") or "")))
    return result


def _fallback_generic_words(language: str) -> tuple[str, ...]:
    """兜底通用检定词（按语言取，回退英文再中文）。"""
    words = _FALLBACK_INTENTS.get("generic_check_words") or {}
    lang = localized_text(language, {"en": "en", "zh-CN": "zh-CN", "ja": "ja"})
    return tuple(words.get(lang) or words.get("en") or words.get("zh-CN") or ())


def _normalized(text: object) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _skill_name(skill: object) -> str:
    if isinstance(skill, dict):
        return str(skill.get("name") or "").strip()
    return str(skill or "").strip()


def _find_skill(character_sheet: dict, text: str, candidates: tuple[str, ...]) -> str:
    skills = character_sheet.get("skills", [])
    names = [_skill_name(skill) for skill in skills]
    direct = [name for name in names if name and _normalized(name) in text]
    if direct:
        return max(direct, key=len)
    for candidate in candidates:
        for name in names:
            if name and (_normalized(candidate) in _normalized(name) or _normalized(name) in _normalized(candidate)):
                return name
    return ""


def _attribute_name(rule: RuleSystem | None, key: str) -> str:
    if rule:
        for attribute in rule.attributes:
            if attribute.get("key") == key:
                return str(attribute.get("name") or key)
    return key


def _d20_advantage(text: str, action: dict, rule: RuleSystem | None) -> tuple[str, str]:
    if not rule or rule.mechanics != "dnd5e_core":
        return "", ""
    raw_mode = str(action.get("advantage_mode") or action.get("advantage") or "").strip().lower()
    has_advantage = raw_mode in {"advantage", "优势", "有利", "bonus"} or any(
        word in text for word in ("优势", "有利", "占优", "奖励骰", "帮忙", "协助", "偷袭", "高地")
    )
    has_disadvantage = raw_mode in {"disadvantage", "劣势", "不利", "penalty"} or any(
        word in text for word in ("劣势", "不利", "受阻", "惩罚骰", "黑暗", "负伤", "疲惫", "干扰")
    )
    if has_advantage and has_disadvantage:
        return "", "优势与劣势同时存在，已抵消"
    if has_advantage:
        return "advantage", "优势：2d20 取高"
    if has_disadvantage:
        return "disadvantage", "劣势：2d20 取低"
    return "", ""


def build_check_request(
    instance: GameInstance,
    action: dict,
    rule: RuleSystem | None,
) -> dict[str, Any] | None:
    """为单个玩家行动生成结构化检定请求；不需要检定时返回 None。"""
    uid = str(action.get("user_id") or "")
    if uid not in instance.players:
        return None
    dice_system = str(rule.dice_system if rule else "d20").lower()
    if dice_system == "none":
        return None

    text = _normalized(action.get("text"))
    selected_skill = str(action.get("selected_skill") or "").strip()
    selected_attribute = str(action.get("selected_attribute") or "").strip()
    character_sheet = instance.get_character_sheet(uid)
    intent = ""
    candidates: tuple[str, ...] = ()
    attribute = selected_attribute

    # 意图识别：优先规则词表（数据驱动），规则未带词表时回退到全局兜底词表。
    intent = rule.find_intent(action.get("text"), instance.language, dice_system) if rule else ""
    if intent:
        candidates = rule.intent_skill_candidates(intent, instance.language) if rule else ()
        if not attribute:
            attribute = rule.intent_default_attribute(intent) if rule else ""
    else:
        for intent_name, aliases, skill_candidates, attr_key in _fallback_intent_specs(instance.language):
            if any(_normalized(alias) in text for alias in aliases):
                intent = intent_name
                candidates = skill_candidates
                if not attribute:
                    attribute = attr_key
                break

    direct_skill = _find_skill(character_sheet, text, ())
    skill = selected_skill or direct_skill
    if not skill and candidates:
        skill = _find_skill(character_sheet, text, candidates)

    explicit_check = bool(selected_skill or selected_attribute)
    # 通用检定词：优先用规则词表的 generic 意图（整词边界，避免 'roll' 命中
    # 'scroll'）；规则没词表时回退全局兜底词（按语言子串）。
    generic_check = False
    if not explicit_check:
        if rule and "generic" in rule.intents:
            generic_check = rule.find_intent(
                action.get("text"), instance.language, dice_system
            ) == "generic"
        else:
            generic_check = any(word in text for word in _fallback_generic_words(instance.language))
    if not (explicit_check or intent or direct_skill or generic_check):
        return None

    if attribute and rule and attribute not in rule.attribute_keys:
        attribute = "int" if "int" in rule.attribute_keys else (rule.attribute_keys[0] if rule.attribute_keys else "")
    if not attribute:
        attribute = "dex" if not rule or "dex" in rule.attribute_keys else (rule.attribute_keys[0] if rule.attribute_keys else "")

    subject = skill or _attribute_name(rule, attribute)
    label = localized_text(instance.language, {
        "en": f"{subject} Check",
        "zh-CN": f"{subject}检定",
        "ja": f"{subject}判定",
    })
    advantage_mode, advantage_note = _d20_advantage(text, action, rule)
    actor_name = str(instance.players.get(uid, {}).get("character_name") or uid)
    return {
        "check_id": uuid.uuid4().hex,
        "required": True,
        "actor_uid": uid,
        "actor_name": actor_name,
        "dice_system": "d100" if dice_system == "d100" else "d20",
        "label": label,
        "intent": intent or "generic",
        "skill": skill,
        "attribute": attribute,
        "advantage_mode": advantage_mode,
        "advantage_note": advantage_note or None,
    }


def roll_check_request(request: dict[str, Any]) -> dict[str, Any]:
    """按 CheckRequest 只生成原始骰值；规则修正与成败由判定解析器计算。"""
    dice_system = str(request.get("dice_system") or "").lower()
    if dice_system == "d100":
        mode = str(request.get("advantage_mode") or "")
        if mode in {"advantage", "disadvantage"}:
            rolls = [roll("d100").natural, roll("d100").natural]
            value = min(rolls) if mode == "advantage" else max(rolls)
        else:
            result = roll("d100")
            rolls = [result.natural]
            value = result.natural
    elif dice_system == "d20":
        mode = str(request.get("advantage_mode") or "")
        if mode in {"advantage", "disadvantage"}:
            rolls = [roll("d20").natural, roll("d20").natural]
            value = max(rolls) if mode == "advantage" else min(rolls)
        else:
            result = roll("d20")
            rolls = [result.natural]
            value = result.natural
    else:
        raise ValueError(f"不支持的检定骰制: {dice_system}")
    return {
        "ok": True,
        "check_id": str(request.get("check_id") or ""),
        "dice_system": dice_system,
        "value": value,
        "rolls": rolls,
        "critical": value == (1 if dice_system == "d100" else 20),
        "fumble": value >= 96 if dice_system == "d100" else value == 1,
    }
