"""generation/creator 生成器单测（P2-M + P2-L）：属性压缩、禁用词/种族双语清洗、装备降级。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.generation.creator import generate_character


class _GenLLM:
    """固定返回构造的 JSON 角色卡，模拟 LLM 输出。"""

    def __init__(self, character: dict) -> None:
        self._char = character

    async def call(self, **kwargs):
        return SimpleNamespace(content=json.dumps(self._char, ensure_ascii=False), total_tokens=0)


def _char(skills=None, race="人类", attrs=None, equipment=None):
    return {
        "character_name": "测试角色", "race": race, "class": "战士", "level": 1,
        "attributes": attrs or {"str": 12, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
        "hp": 50, "max_hp": 50,
        "skills": skills or [],
        "equipment": equipment or [],
        "inventory": [], "background": "",
    }


@pytest.mark.asyncio
async def test_zh_banned_skill_and_race_filtered():
    """中文禁用技能词/种族被后验清洗。"""
    c = _char(
        skills=[{"name": "无敌斩", "value": 80}, {"name": "侦查", "value": 40}],
        race="半神",
    )
    result = await generate_character(_GenLLM(c), "生成角色", language="zh-CN")
    names = [s["name"] for s in result["skills"]]
    assert "无敌斩" not in names
    assert result["race"] == "人类"


@pytest.mark.asyncio
async def test_en_banned_skill_and_race_filtered():
    """P2-L：英文禁用词（Invincible/Demigod）不被绕过。"""
    c = _char(
        skills=[{"name": "Invincible Strike", "value": 80}, {"name": "Stealth", "value": 40}],
        race="Demigod",
    )
    result = await generate_character(_GenLLM(c), "make a character", language="en")
    names = [s["name"] for s in result["skills"]]
    assert "Invincible Strike" not in names
    assert "Stealth" in names
    assert result["race"] == "Human"


@pytest.mark.asyncio
async def test_attribute_over_budget_compressed():
    """属性点超限被等比压缩到上限内。"""
    c = _char(attrs={"str": 30, "dex": 30, "con": 10, "int": 10, "wis": 10, "cha": 10})
    result = await generate_character(_GenLLM(c), "生成角色", language="zh-CN")
    total = sum(result["attributes"][k] for k in ("str", "dex", "con", "int", "wis", "cha"))
    assert total <= 60
    assert result["attributes"]["str"] <= 18


@pytest.mark.asyncio
async def test_equipment_quality_downgraded_to_common():
    """非 common 装备被降级。"""
    c = _char(equipment=[{"name": "神剑", "type": "weapon", "damage": 8, "quality": "legendary"}])
    result = await generate_character(_GenLLM(c), "生成角色", language="zh-CN")
    assert result["equipment"][0]["quality"] == "common"


def test_unique_world_id_avoids_collision(tmp_path):
    """P3-F：同名世界已存在时加数字后缀，不覆盖旧存档。"""
    from src.generation.creator import _unique_world_id
    (tmp_path / "ai_world.json").write_text("{}", encoding="utf-8")
    assert _unique_world_id("ai_world", tmp_path) == "ai_world_2"
    (tmp_path / "ai_world_2.json").write_text("{}", encoding="utf-8")
    assert _unique_world_id("ai_world", tmp_path) == "ai_world_3"
    assert _unique_world_id("ai_fresh", tmp_path) == "ai_fresh"


def test_apply_generated_visibility_public_secret_and_fail_closed():
    """AI 的 visibility 建议只认 public 枚举；缺失/写错/自由发挥一律 GM 秘密。"""
    from src.generation.creator import apply_generated_visibility

    public = {"name": "金狮酒馆", "visibility": "public"}
    apply_generated_visibility(public)
    assert public["visible_to"] == ["*"]
    assert "visibility" not in public  # 原始建议字段被消费，不进存储

    for bad in ({"name": "x", "visibility": "secret"},
                {"name": "x", "visibility": "公开"},   # 中文别名不认：枚举语言无关
                {"name": "x", "visibility": ""},
                {"name": "x"},                          # 缺失
                {"name": "x", "visibility": ["*"]}):    # 自由发挥
        apply_generated_visibility(bad)
        assert bad["visible_to"] == [], bad
        assert "visibility" not in bad
