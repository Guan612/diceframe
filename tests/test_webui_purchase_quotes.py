"""购买报价（purchase quote）显式确认契约测试。

覆盖 PR1 的核心差距：持久化报价必须有服务端 offer id，确认/取消是显式的
带身份端点，且结算仍只经由标准支付确认路径（一笔交易一次发货）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import web_server
from src.commands.economy_effects import record_purchase_quote
from src.webui.routes.game_gameplay_routes import (
    api_payment_resolve,
    api_purchase_quote_cancel,
    api_purchase_quote_confirm,
)
from src.webui.routes.game_query_routes import api_detail

from webapi_harness import web_api  # noqa: F401


def _quote_app(api, registry) -> web.Application:
    app = web.Application(middlewares=[web_server.auth_middleware])
    app["api"] = api
    app["subsystems"] = SimpleNamespace(registry=registry)
    app["plugin_host"] = None
    app.router.add_get("/api/games/{game_key}", api_detail)
    app.router.add_post(
        "/api/games/{game_key}/payments/{payment_id}",
        api_payment_resolve,
    )
    app.router.add_post(
        "/api/games/{game_key}/purchase-quotes/{quote_id}/confirm",
        api_purchase_quote_confirm,
    )
    app.router.add_post(
        "/api/games/{game_key}/purchase-quotes/{quote_id}/cancel",
        api_purchase_quote_cancel,
    )
    return app


def _record_quote(instance, payer_uid: str, *, item: str = "通行证", amount: int = 5):
    instance.action_queue = [{"user_id": payer_uid, "text": f"我想买{item}"}]
    data = {"state_update": {"loot": [{"player": payer_uid, "item": item}]}}
    assert record_purchase_quote(instance, data, f"{item}售价{amount}金币。")
    return instance.economy["purchase_quotes"][-1]


@pytest.mark.asyncio
async def test_quote_confirm_creates_single_pending_proposal_for_payer(web_api):
    api, _lorebook, registry, _llm, _worlds = web_api
    created = await api.create_game(
        "template_world",
        "购买报价确认",
        players=[
            {"character_name": "付款人", "attributes": {"str": 10}, "gold": 30},
            {"character_name": "旁观者", "attributes": {"str": 10}, "gold": 30},
        ],
    )
    game_key = created["game_key"]
    instance = registry.get(api._parse_key(game_key))
    payer_uid, other_uid = list(instance.players)
    quote = _record_quote(instance, payer_uid)
    assert quote["id"].startswith("quote_")
    assert instance.get_character_sheet(payer_uid)["currency"]["amount"] == 30

    app = _quote_app(api, registry)
    async with TestClient(TestServer(app)) as client:
        payer_query = {"user": payer_uid, "share": "1"}

        detail = await client.get(f"/api/games/{game_key}", params=payer_query)
        assert detail.status == 200
        projected = (await detail.json()).get("purchase_quotes", [])
        assert [item["id"] for item in projected] == [quote["id"]]
        assert projected[0]["amount"] == 5

        # 旁观者带玩家身份也不能确认他人的报价。
        denied = await client.post(
            f"/api/games/{game_key}/purchase-quotes/{quote['id']}/confirm",
            params={"user": other_uid, "share": "1"},
        )
        assert denied.status == 403
        assert not instance.economy.get("proposals")

        confirmed = await client.post(
            f"/api/games/{game_key}/purchase-quotes/{quote['id']}/confirm",
            params=payer_query,
        )
        assert confirmed.status == 200
        proposal = (await confirmed.json())["proposal"]
        assert proposal["status"] == "pending"
        assert proposal["amount"] == 5
        assert quote["status"] == "confirmed"
        assert quote["proposal_id"] == proposal["id"]
        # 确认只创建待确认提案，不扣款、不发货。
        assert instance.get_character_sheet(payer_uid)["currency"]["amount"] == 30

        repeat = await client.post(
            f"/api/games/{game_key}/purchase-quotes/{quote['id']}/confirm",
            params=payer_query,
        )
        assert repeat.status == 200
        assert (await repeat.json())["already_resolved"] is True
        assert len(instance.economy["proposals"]) == 1

        settled = await client.post(
            f"/api/games/{game_key}/payments/{proposal['id']}",
            params=payer_query,
            json={"accepted": True},
        )
        assert settled.status == 200
        sheet = instance.get_character_sheet(payer_uid)
        assert sheet["currency"]["amount"] == 25
        granted = [
            item for item in sheet.get("inventory", [])
            if item.get("name") == "通行证"
        ]
        assert len(granted) == 1
        assert len(instance.economy["transactions"]) == 1


@pytest.mark.asyncio
async def test_quote_cancel_is_explicit_and_blocks_later_confirm(web_api):
    api, _lorebook, registry, _llm, _worlds = web_api
    created = await api.create_game(
        "template_world",
        "购买报价取消",
        players=[
            {"character_name": "付款人", "attributes": {"str": 10}, "gold": 30},
            {"character_name": "GM 主持", "attributes": {"str": 10}, "gold": 30},
        ],
    )
    game_key = created["game_key"]
    instance = registry.get(api._parse_key(game_key))
    payer_uid, gm_uid = list(instance.players)
    instance.gm_uid = gm_uid
    quote = _record_quote(instance, payer_uid)

    app = _quote_app(api, registry)
    async with TestClient(TestServer(app)) as client:
        payer_query = {"user": payer_uid, "share": "1"}
        cancelled = await client.post(
            f"/api/games/{game_key}/purchase-quotes/{quote['id']}/cancel",
            params=payer_query,
        )
        assert cancelled.status == 200
        assert quote["status"] == "cancelled"
        assert quote["resolution_code"] == "CANCELLED_BY_PAYER"
        assert instance.get_character_sheet(payer_uid)["currency"]["amount"] == 30

        late = await client.post(
            f"/api/games/{game_key}/purchase-quotes/{quote['id']}/confirm",
            params=payer_query,
        )
        assert late.status == 409
        assert not instance.economy.get("proposals")

        # GM 也能取消 open 报价。
        second = _record_quote(instance, payer_uid, item="硬皮甲", amount=260)
        gm_cancel = await client.post(
            f"/api/games/{game_key}/purchase-quotes/{second['id']}/cancel",
            params={"user": gm_uid, "share": "1"},
        )
        assert gm_cancel.status == 200
        assert second["resolution_code"] == "CANCELLED_BY_GM"


@pytest.mark.asyncio
async def test_quote_confirm_rejects_stale_run(web_api):
    api, _lorebook, registry, _llm, _worlds = web_api
    created = await api.create_game(
        "template_world",
        "购买报价跨局拒绝",
        players=[
            {"character_name": "付款人", "attributes": {"str": 10}, "gold": 30},
        ],
    )
    game_key = created["game_key"]
    instance = registry.get(api._parse_key(game_key))
    payer_uid = next(iter(instance.players))
    quote = _record_quote(instance, payer_uid)

    app = _quote_app(api, registry)
    async with TestClient(TestServer(app)) as client:
        instance.run_id = "run_new_run"
        stale = await client.post(
            f"/api/games/{game_key}/purchase-quotes/{quote['id']}/confirm",
            params={"user": payer_uid, "share": "1"},
        )
        assert stale.status == 409
        assert (await stale.json())["code"] == "STALE_RUN"
        assert not instance.economy.get("proposals")
