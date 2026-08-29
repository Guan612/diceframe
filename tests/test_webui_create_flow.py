"""WebUI 开局创建与回滚链路测试（拆分后保留创建主流程）。"""

from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.commands.game_handler import GameHandler
from src.engine.game_instance import GameRegistry
from src.engine.health import record_health_event
from src.llm.client import LLMResponse
from src.lorebook.matcher import KeywordMatcher
from src.lorebook.store import LorebookStore
from src.webui.api import WebAPI, can_modify_character
from src.webui.session import SessionManager

from webapi_harness import FakeLLMClient, web_api, write_world

@pytest.mark.asyncio
async def test_create_game_uses_created_character_before_opening(web_api):
    api, _lorebook, registry, fake_llm, _worlds_dir = web_api

    result = await api.create_game(
        "template_world",
        "模板世界",
        narrative_perspective="third_person",
        players=[{
            "character_name": "艾琳",
            "race": "精灵",
            "class": "游侠",
            "attributes": {"str": 12},
            "background": "来自银叶林地",
        }],
    )

    assert result["ok"] is True
    inst = registry.get(api._parse_key(result["game_key"]))
    assert inst is not None
    assert [p["character_name"] for p in inst.players.values()] == ["艾琳"]
    assert "艾琳" in fake_llm.calls[-1]["user_message"]
    assert inst.narrative_perspective == "third_person"
    assert result["players"][0]["character_name"] == "艾琳"


@pytest.mark.asyncio
async def test_create_game_persists_and_returns_success_when_opening_generation_fails(
    web_api, monkeypatch,
):
    api, _lorebook, registry, fake_llm, _worlds_dir = web_api

    async def fail_opening(*_args, **_kwargs):
        raise ConnectionError("test provider is unavailable")

    monkeypatch.setattr(fake_llm, "call", fail_opening)
    result = await api.create_game(
        "template_world",
        "断线仍可进入",
        players=[{
            "character_name": "守夜人",
            "race": "人类",
            "class": "战士",
            "attributes": {"str": 12},
        }],
    )

    assert result["ok"] is True
    inst = registry.get(api._parse_key(result["game_key"]))
    assert inst is not None
    assert inst.log[-1]["round"] == 0
    assert "已经创建" in inst.log[-1]["gm_response"]
    assert (registry.save_dir / "#".join(inst.game_key) / "state.json").is_file()


@pytest.mark.asyncio
async def test_create_game_rejects_empty_player_list(web_api):
    api, _lorebook, registry, fake_llm, _worlds_dir = web_api

    result = await api.create_game("template_world", "模板世界", players=[])

    assert result["ok"] is False
    assert "至少创建或选择" in result["error"]
    assert registry.list_all() == []
    assert fake_llm.calls == []


@pytest.mark.asyncio
async def test_unconfigured_model_is_rejected_before_creating_save_data(web_api):
    api, _lorebook, registry, fake_llm, _worlds_dir = web_api
    fake_llm.providers = {
        "fake": SimpleNamespace(
            provider_name="fake",
            base_url="",
            api_key="",
            model_name="",
        ),
    }

    result = await api.create_game(
        "template_world",
        "模板世界",
        players=[{"character_name": "艾琳", "attributes": {"str": 12}}],
    )

    assert result["ok"] is False
    assert result["error_code"] == "llm_not_configured"
    assert result["missing"] == ["base_url", "model", "api_key"]
    assert registry.list_all() == []
    assert fake_llm.calls == []


@pytest.mark.asyncio
async def test_ai_generation_reports_unconfigured_model_without_calling_it(web_api):
    api, _lorebook, _registry, fake_llm, _worlds_dir = web_api
    fake_llm.providers = {
        "fake": SimpleNamespace(
            provider_name="fake",
            base_url="https://example.invalid/v1",
            api_key="",
            model_name="test-model",
        ),
    }

    result = await api.generate_rule("测试规则", "freeform_fantasy")

    assert result["ok"] is False
    assert result["error_code"] == "llm_not_configured"
    assert result["missing"] == ["api_key"]
    assert fake_llm.calls == []


@pytest.mark.asyncio
async def test_game_detail_exposes_multiplayer_status(web_api):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api

    created = await api.create_game(
        "template_world",
        "模板世界",
        solo=False,
        players=[
            {"character_name": "艾琳", "attributes": {"str": 10}},
            {"character_name": "洛恩", "attributes": {"str": 10}},
        ],
    )
    inst = registry.get(api._parse_key(created["game_key"]))
    first_uid = created["players"][0]["user_id"]
    await inst.add_action(first_uid, "我观察门口")
    inst.last_token_budget_bump = {"kind": "narrative", "from": 2048, "to": 4096}

    detail = api.game_detail(created["game_key"])
    status = api.multiplayer_status(created["game_key"])

    assert detail["solo_mode"] is False
    assert detail["token_budget_bump"] == {"kind": "narrative", "from": 2048, "to": 4096}
    assert detail["multiplayer"]["ready_count"] == 1
    assert status["ok"] is True
    assert status["waiting_players"][0]["character_name"] == "洛恩"


@pytest.mark.asyncio
async def test_game_server_roll_uses_world_rule(web_api):
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    created = await api.create_game(
        "template_world",
        "骰子测试",
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
    )

    result = api.roll_for_game(created["game_key"])

    assert result["ok"] is True
    assert result["dice_system"] == "d20"
    assert 1 <= result["value"] <= 20


@pytest.mark.asyncio
async def test_create_from_seed_requires_original_save_and_reuses_world(web_api):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api

    original = await api.create_game(
        "template_world",
        "原始世界",
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
    )
    seed_code = original["seed_code"]

    restarted = await api.create_from_seed(
        seed_code,
        solo=True,
        players=[{"character_name": "洛恩", "attributes": {"str": 11}}],
        gm_uid="web_restart_gm",
    )

    assert restarted["ok"] is True
    assert restarted["world_id"] == "template_world"
    assert restarted["seed_code"] == seed_code
    inst = registry.get(api._parse_key(restarted["game_key"]))
    assert [p["character_name"] for p in inst.players.values()] == ["洛恩"]
    assert inst.gm_uid == "web_restart_gm"

    empty_players = await api.create_from_seed(seed_code, solo=True, players=[])
    assert empty_players["ok"] is False
    assert "至少创建或选择" in empty_players["error"]

    missing = await api.create_from_seed("missing-seed-code", players=[])
    assert missing["ok"] is False
    assert "未找到重开引用码" in missing["error"]


@pytest.mark.asyncio
async def test_restart_game_without_players_is_rejected(web_api):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api
    inst = registry.get_or_create(("web", "empty_game", "web_bot"))
    inst.world_id = "template_world"
    inst.world_name = "模板世界"

    result = await api.restart_game("web|empty_game|web_bot")

    assert result["ok"] is False
    assert "没有角色" in result["error"]
    assert inst.players == {}


@pytest.mark.asyncio
async def test_switch_world_accepts_lorebook_only_world(web_api):
    api, lorebook, registry, _fake_llm, _worlds_dir = web_api

    created = await api.create_game(
        "template_world",
        "模板世界",
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
    )
    lorebook.create_world("custom_book_only", "只在世界书库里的世界", description="没有模板 JSON")

    result = await api.switch_world(created["game_key"], "custom_book_only")

    assert result["ok"] is True
    assert result["world_id"] == "custom_book_only"
    assert result["world_name"] == "只在世界书库里的世界"
    inst = registry.get(api._parse_key(created["game_key"]))
    assert inst.world_id == "custom_book_only"
    assert inst.world_name == "只在世界书库里的世界"


@pytest.mark.asyncio
async def test_game_health_api_marks_event(web_api):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api
    inst = registry.get_or_create(("web", "health_api", "bot"))
    event = record_health_event(inst, "memory", "MEMORY_WRITE_FAILED", "warning", "Memory write failed")

    payload = api.game_health("web|health_api|bot")
    marked = await api.mark_game_health_event("web|health_api|bot", event["id"], resolved=True)

    assert payload["ok"] is True
    assert payload["events"][0]["code"] == "MEMORY_WRITE_FAILED"
    assert marked["ok"] is True
    assert api.game_health("web|health_api|bot")["events"] == []


@pytest.mark.asyncio
async def test_rollback_round_pops_last_log_entry_and_reports_empty(web_api):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api
    result = await api.create_game(
        "template_world",
        "模板世界",
        players=[{
            "character_name": "艾琳",
            "race": "精灵",
            "class": "游侠",
            "attributes": {"str": 12},
        }],
    )
    gk = result["game_key"]
    inst = registry.get(api._parse_key(gk))
    uid = next(iter(inst.players))
    sheet = inst.get_character_sheet(uid)
    sheet["luck"] = 28
    sheet["resources"] = {"luck": {"current": 28, "max": 99}}
    inst.round_number = 3
    inst.log.append({
        "round": 3,
        "round_start_snapshot": {uid: {"luck": 30, "resources": {"luck": {"current": 30, "max": 99}}}},
        "pre_state_snapshot": {uid: {"luck": 28, "resources": {"luck": {"current": 28, "max": 99}}}},
    })

    rolled = await api.rollback_round(gk)

    assert rolled["ok"] is True
    assert len(inst.log) == 1  # 我加的 round3 已 pop，create_game 的开场 log 仍在
    assert inst.round_number == 3
    assert inst.get_character_sheet(uid)["luck"] == 30
    assert inst.get_character_sheet(uid)["resources"]["luck"]["current"] == 30

    second = await api.rollback_round(gk)  # 撤回开场
    assert second["ok"] is True
    assert inst.log == []

    empty = await api.rollback_round(gk)
    assert empty["ok"] is False
    assert "没有可撤回" in empty["error"]


@pytest.mark.asyncio
async def test_create_game_room_password_tristate(web_api):
    """房间密码三态（P1-A）：None+多人→生成随机密码回显；显式空串→开放；单人局不生成；太短→拒绝。"""
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api
    players = [{
        "character_name": "勇者", "class": "战士",
        "attributes": {"str": 14, "dex": 10, "con": 12, "int": 10, "wis": 10, "cha": 10},
    }]

    # 1) 多人局未声明密码 → 生成随机密码回显
    r = await api.create_game("template_world", "多人加密", players=list(players), solo=False, room_password=None)
    assert r["ok"] is True
    assert r.get("generated_password"), "多人局未声明应生成随机密码"
    inst = registry.get(api._parse_key(r["game_key"]))
    assert inst.room_password == r["generated_password"]

    # 2) 显式空串 → 开放房，不回显
    r2 = await api.create_game("template_world", "开放房", players=list(players), solo=False, room_password="")
    assert r2["ok"] is True
    assert r2.get("generated_password") is None
    inst2 = registry.get(api._parse_key(r2["game_key"]))
    assert inst2.room_password == ""

    # 3) 单人局未声明 → 不生成（solo 自玩无需密码）
    r3 = await api.create_game("template_world", "单人局", players=list(players), solo=True, room_password=None)
    assert r3["ok"] is True
    assert r3.get("generated_password") is None
    inst3 = registry.get(api._parse_key(r3["game_key"]))
    assert inst3.room_password == ""

    # 4) 太短 → 拒绝
    keys_before_rejection = {instance.game_key for instance in registry.list_all()}
    r4 = await api.create_game("template_world", "弱密码", players=list(players), solo=False, room_password="ab")
    assert r4.get("ok") is False
    assert "至少 4 位" in r4.get("error", "")
    assert {instance.game_key for instance in registry.list_all()} == keys_before_rejection


@pytest.mark.asyncio
async def test_create_game_rolls_back_when_player_creation_raises(web_api, monkeypatch):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api
    keys_before = {instance.game_key for instance in registry.list_all()}
    saves_before = {path.parent for path in registry.save_dir.rglob("state.json")}

    async def broken_create_player(*_args, **_kwargs):
        raise RuntimeError("simulated character storage failure")

    monkeypatch.setattr(api, "create_player", broken_create_player)
    result = await api.create_game(
        "template_world", "原子创建测试",
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
        gm_uid="web_session_gm",
    )

    assert result == {
        "ok": False,
        "error_code": "GAME_CREATE_FAILED",
        "error": "创建角色失败，未留下半成品存档，请重试。",
    }
    assert {instance.game_key for instance in registry.list_all()} == keys_before
    assert {path.parent for path in registry.save_dir.rglob("state.json")} == saves_before


@pytest.mark.asyncio
async def test_create_game_rolls_back_first_saved_player_when_second_fails(web_api, monkeypatch):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api
    original_create_player = api.create_player
    calls = 0

    async def fail_second_player(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            return {"ok": False, "error": "simulated second player failure"}
        return await original_create_player(*args, **kwargs)

    monkeypatch.setattr(api, "create_player", fail_second_player)
    result = await api.create_game(
        "template_world", "多角色原子创建测试",
        players=[
            {"character_name": "艾琳", "attributes": {"str": 10}},
            {"character_name": "洛恩", "attributes": {"str": 10}},
        ],
        gm_uid="web_session_gm",
    )

    assert result["ok"] is False
    assert "simulated second player failure" in result["error"]
    assert registry.list_all() == []
    assert list(registry.save_dir.rglob("state.json")) == []
