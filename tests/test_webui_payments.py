"""WebUI 支付与金币结算测试（自 test_webui_create_flow 拆分）。"""

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

async def _make_game_with_pending(
    web_api,
    *,
    gold=30,
    amount=12,
    payment_id="pay_test1",
    rewards=None,
):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api
    result = await api.create_game(
        "template_world",
        "模板世界",
        players=[{
            "character_name": "艾琳",
            "race": "精灵",
            "class": "游侠",
            "attributes": {"str": 12},
            "gold": gold,
        }],
    )
    gk = result["game_key"]
    inst = registry.get(api._parse_key(gk))
    uid = next(iter(inst.players))
    inst.players[uid]["character_sheet"]["gold"] = gold
    inst.gm_uid = uid
    inst.pending_payments.append({
        "id": payment_id, "uid": uid, "amount": amount,
        "recipient_uid": uid,
        "rewards": list(rewards or []),
        "reason": "GM 建议支付", "status": "pending", "round": 1,
    })
    return api, gk, inst, uid


@pytest.mark.asyncio
async def test_raw_gold_change_cannot_bypass_economy(web_api):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api
    result = await api.create_game(
        "template_world",
        "模板世界",
        players=[{
            "character_name": "艾琳",
            "race": "精灵",
            "class": "游侠",
            "attributes": {"str": 12},
            "gold": 30,
        }],
    )
    inst = registry.get(api._parse_key(result["game_key"]))
    assert inst is not None
    uid = next(iter(inst.players))
    cs = inst.players[uid]["character_sheet"]
    cs["gold"] = 30

    # Raw state injection is not an economic authority.
    api._handler._apply_state_update(inst, {
        "players": {uid: {"gold_change": -12}},
    })

    assert inst.players[uid]["character_sheet"]["gold"] == 30
    assert inst.pending_payments == []


@pytest.mark.asyncio
async def test_negative_raw_gold_change_is_ignored(web_api):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api
    result = await api.create_game(
        "template_world",
        "模板世界",
        players=[{
            "character_name": "洛恩",
            "attributes": {"str": 10},
            "gold": 20,
        }],
    )
    inst = registry.get(api._parse_key(result["game_key"]))
    assert inst is not None
    uid = next(iter(inst.players))
    inst.players[uid]["character_sheet"]["gold"] = 20

    # Even an oversized injected delta cannot mutate the wallet.
    api._handler._apply_state_update(inst, {
        "players": {uid: {"gold_change": -50}},
    })

    assert inst.players[uid]["character_sheet"]["gold"] == 20
    assert inst.pending_payments == []


@pytest.mark.asyncio
async def test_resolve_payment_accepted_deducts_gold(web_api):
    api, gk, inst, uid = await _make_game_with_pending(web_api, gold=30, amount=12)
    res = await api.resolve_payment(gk, "pay_test1", True, uid)
    assert res["ok"] is True
    assert res["accepted"] is True
    assert inst.players[uid]["character_sheet"]["gold"] == 18
    assert res["payment"]["status"] == "committed"
    assert inst.pending_payments == []


@pytest.mark.asyncio
async def test_resolve_payment_rejected_adds_health_event(web_api):
    api, gk, inst, uid = await _make_game_with_pending(web_api, gold=30, amount=12)
    res = await api.resolve_payment(gk, "pay_test1", False, uid)
    assert res["ok"] is True
    assert res["accepted"] is False
    # 拒绝不扣金币
    assert inst.players[uid]["character_sheet"]["gold"] == 30
    # 通知 GM：健康事件
    assert any(e.get("code") == "economy_declined" for e in inst.health_events)
    assert res["payment"]["status"] == "declined"
    assert inst.pending_payments == []


@pytest.mark.asyncio
async def test_resolve_payment_permission_non_owner_blocked(web_api):
    api, gk, inst, uid = await _make_game_with_pending(web_api, gold=30, amount=12)
    # 非当事玩家、非 GM 不能处理
    res = await api.resolve_payment(gk, "pay_test1", True, "other_user")
    assert res["ok"] is False
    assert res["code"] == "FORBIDDEN"
    # 状态未变
    assert next(p for p in inst.pending_payments if p["id"] == "pay_test1")["status"] == "pending"
    assert inst.players[uid]["character_sheet"]["gold"] == 30


@pytest.mark.asyncio
async def test_resolve_payment_insufficient_gold(web_api):
    api, gk, inst, uid = await _make_game_with_pending(
        web_api,
        gold=5,
        amount=12,
        rewards=[{"name": "解毒草", "category": ""}],
    )
    res = await api.resolve_payment(gk, "pay_test1", True, uid)
    assert res["ok"] is False
    assert res["code"] == "INSUFFICIENT_FUNDS"
    assert inst.players[uid]["character_sheet"]["gold"] == 5
    assert not any(
        item.get("name") == "解毒草"
        for item in inst.players[uid]["character_sheet"].get("inventory", [])
    )
    # 余额不足：交易不成立，pending 被自动取消，避免弹窗反复出现
    assert not any(
        p["id"] == "pay_test1" and p["status"] == "pending"
        for p in inst.pending_payments
    )


@pytest.mark.asyncio
async def test_multiplayer_payment_grants_items_to_recipient(web_api):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api
    result = await api.create_game(
        "template_world",
        "多人交易",
        players=[
            {"character_name": "付款者", "attributes": {"str": 12}, "gold": 30},
            {"character_name": "接收者", "attributes": {"str": 12}, "gold": 5},
        ],
    )
    gk = result["game_key"]
    inst = registry.get(api._parse_key(gk))
    payer_uid, recipient_uid = list(inst.players)
    inst.gm_uid = payer_uid
    inst.players[payer_uid]["character_sheet"]["gold"] = 30
    inst.pending_payments.append({
        "id": "pay_multi",
        "uid": payer_uid,
        "amount": 15,
        "recipient_uid": recipient_uid,
        "rewards": [
            {"name": "解毒草", "category": ""},
            {"name": "止血苔", "category": ""},
        ],
        "reason": "替队友购买药草",
        "status": "pending",
        "round": 1,
    })

    resolved = await api.resolve_payment(
        gk, "pay_multi", True, payer_uid
    )
    assert resolved["ok"] is True
    assert inst.players[payer_uid]["character_sheet"]["gold"] == 15
    recipient_inventory = inst.players[recipient_uid]["character_sheet"]["inventory"]
    assert {item["name"] for item in recipient_inventory} >= {"解毒草", "止血苔"}


@pytest.mark.asyncio
async def test_apply_state_update_creates_pending_payment(web_api):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api
    result = await api.create_game(
        "template_world", "模板世界",
        players=[{"character_name": "艾琳", "attributes": {"str": 12}, "gold": 30}],
    )
    inst = registry.get(api._parse_key(result["game_key"]))
    uid = next(iter(inst.players))
    assert inst.pending_payments == []

    api._handler._apply_state_update(inst, {
        "pending_payments": [{
            "uid": uid,
            "amount": 7,
            "recipient_uid": uid,
            "items": ["药水"],
            "reason": "购买药水",
        }],
    })
    assert len(inst.pending_payments) == 1
    pay = inst.pending_payments[0]
    assert pay["uid"] == uid
    assert pay["amount"] == 7
    assert pay["recipient_uid"] == uid
    assert pay["rewards"][0]["name"] == "药水"
    assert pay["status"] == "pending"
    assert pay["id"].startswith("eco_")
    # PAY 不直接扣金币
    assert inst.players[uid]["character_sheet"]["gold"] == 30
    assert not any(
        item.get("name") == "药水"
        for item in inst.players[uid]["character_sheet"].get("inventory", [])
    )


@pytest.mark.asyncio
async def test_apply_state_update_caps_loot_per_round(web_api):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api
    result = await api.create_game(
        "template_world", "模板世界",
        players=[{"character_name": "艾琳"}],
    )
    inst = registry.get(api._parse_key(result["game_key"]))
    uid = next(iter(inst.players))

    api._handler._apply_state_update(inst, {
        "loot": [{"player": uid, "item": f"物品{i}"} for i in range(25)],
    })

    inventory = inst.players[uid]["character_sheet"]["inventory"]
    names = {item["name"] for item in inventory}
    assert {f"物品{i}" for i in range(20)} <= names
    assert not names & {f"物品{i}" for i in range(20, 25)}


