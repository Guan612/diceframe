from __future__ import annotations

import json

import pytest

from src.webui.routes import bot
from src.webui.services import bot_extensions


class FakeApi:
    def __init__(self, asset_path=None):
        self.calls = []
        self.asset_path = asset_path

    def bot_extension_capabilities(self):
        return {"protocol_version": 1, "stages": ["before_message", "after_result", "render"], "extensions": 2}

    async def apply_bot_extensions(self, stage, payload):
        self.calls.append((stage, payload))
        return {
            "ok": True,
            "handled": True,
            "payload": payload,
            "outputs": [{"type": "text", "text": "handled"}],
            "applied": [{"plugin_id": "demo", "name": "command"}],
        }

    def bot_extension_asset_path(self, plugin_id, relative_path):
        self.calls.append((plugin_id, relative_path))
        if self.asset_path is None:
            raise KeyError("missing")
        return self.asset_path


class FakeRequest(dict):
    def __init__(self, api, *, body=None, match_info=None, plugin_identity=None):
        super().__init__()
        self.app = {"api": api}
        self._body = body
        self.match_info = match_info or {}
        if plugin_identity:
            self["plugin_authenticated"] = plugin_identity

    async def json(self):
        return self._body


def response_json(response):
    return json.loads(response.text)


@pytest.mark.asyncio
async def test_bridge_extension_route_adds_trusted_caller_identity():
    api = FakeApi()
    request = FakeRequest(
        api,
        body={
            "stage": "before_message",
            "payload": {"platform": "qq", "kind": "command", "text": "/demo"},
        },
        plugin_identity={"plugin_id": "qq-napcat"},
    )

    response = await bot.api_apply_bridge_extensions(request)
    body = response_json(response)

    assert response.status == 200
    assert body["handled"] is True
    assert api.calls[0][0] == "before_message"
    assert api.calls[0][1]["_caller"] == {"plugin_id": "qq-napcat", "managed": True}


@pytest.mark.asyncio
async def test_bridge_extension_route_rejects_non_object_payload():
    response = await bot.api_apply_bridge_extensions(
        FakeRequest(FakeApi(), body={"stage": "render", "payload": []})
    )

    assert response.status == 400
    assert "payload" in response_json(response)["error"]


@pytest.mark.asyncio
async def test_bridge_extension_service_is_noop_without_plugin_host():
    class Api:
        _plugins = None

    payload = {"platform": "maibot", "kind": "text", "text": "hello"}
    result = await bot_extensions.apply(Api(), "render", payload)

    assert result == {
        "ok": True,
        "handled": False,
        "payload": payload,
        "outputs": [],
        "applied": [],
    }


class FakePluginHost:
    """模拟插件宿主：返回 card 输出，并暴露 data_dir 供物化。"""

    def __init__(self, data_dir):
        self.data_dir = data_dir

    async def apply_bridge_extensions(self, stage, payload):
        return {
            "ok": True,
            "handled": True,
            "payload": payload,
            "outputs": [
                {
                    "type": "card",
                    "title": "测试卡片",
                    "subtitle": "副标题",
                    "lines": ["第一行", "第二行"],
                    "fallback_text": "fallback",
                },
            ],
            "applied": [{"plugin_id": "demo", "name": "card"}],
        }


class MaterializeApi:
    def __init__(self, data_dir):
        self._plugins = FakePluginHost(data_dir)

    def bot_bridge_card_path(self, name):
        return bot_extensions.bridge_card_path(self, name)


def test_materialize_cards_turns_card_output_into_image(tmp_path):
    api = MaterializeApi(str(tmp_path))
    outputs = [
        {
            "type": "card",
            "title": "测试卡片",
            "subtitle": "副标题",
            "lines": ["第一行", "第二行"],
            "fallback_text": "",
        },
    ]

    result = bot_extensions._materialize_cards(api, outputs)

    assert len(result) == 1
    assert result[0]["type"] == "image"
    assert result[0]["asset_url"].startswith("/api/bot/bridge-cards/")
    assert result[0]["alt"] == "测试卡片"
    assert "fallback" not in result[0]["fallback_text"] or result[0]["fallback_text"]
    # 渲染出的文件真实存在
    card_dir = tmp_path / "bot" / "cards"
    assert any(card_dir.glob("card_*.png"))


def test_materialize_cards_keeps_non_card_outputs_untouched(tmp_path):
    api = MaterializeApi(str(tmp_path))
    outputs = [{"type": "text", "text": "hello"}]

    result = bot_extensions._materialize_cards(api, outputs)

    assert result == outputs


def test_bridge_card_path_rejects_bad_names(tmp_path):
    api = MaterializeApi(str(tmp_path))

    for bad in ("../evil.png", "not-card.png", "card_abc.png", "card_zzzz.png", "card_123.png"):
        try:
            bot_extensions.bridge_card_path(api, bad)
            raised = None
        except (KeyError, ValueError) as exc:
            raised = exc
        assert raised is not None, f"{bad} 应被拒绝"


def test_bridge_card_path_serves_rendered_file(tmp_path):
    api = MaterializeApi(str(tmp_path))
    # 先物化产生一张卡
    bot_extensions._materialize_cards(api, [{
        "type": "card",
        "title": "T",
        "subtitle": "S",
        "lines": ["L"],
        "fallback_text": "",
    }])
    card_dir = tmp_path / "bot" / "cards"
    files = list(card_dir.glob("card_*.png"))
    assert files, "物化应生成卡片文件"
    path = bot_extensions.bridge_card_path(api, files[0].name)
    assert path == files[0].resolve()


@pytest.mark.asyncio
async def test_bridge_card_asset_route_returns_image(tmp_path):
    api = MaterializeApi(str(tmp_path))
    bot_extensions._materialize_cards(api, [{
        "type": "card",
        "title": "T",
        "subtitle": "S",
        "lines": ["L"],
        "fallback_text": "",
    }])
    card_dir = tmp_path / "bot" / "cards"
    files = list(card_dir.glob("card_*.png"))
    assert files

    request = FakeRequest(api, match_info={"name": files[0].name})
    response = await bot.api_bridge_card_asset(request)

    assert response.status == 200
    # FileResponse 未 prepare 时 body_length 为 0，验证底层文件路径指向渲染产物且非空
    served = response._path
    assert served == files[0].resolve()
    assert served.stat().st_size > 0
    assert response.headers.get("Cache-Control") == "no-store"
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


@pytest.mark.asyncio
async def test_bridge_card_asset_route_rejects_bad_name(tmp_path):
    api = MaterializeApi(str(tmp_path))
    request = FakeRequest(api, match_info={"name": "..%2f..%2fevil.png"})

    with pytest.raises(Exception) as exc_info:
        await bot.api_bridge_card_asset(request)

    assert exc_info.value.status == 404
