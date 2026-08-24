from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.engine.game_instance import GameInstance, GameRegistry
from src.rules.rule_system import RuleSystem
from src.rulesets.contracts import RulesetCapabilities
from src.rulesets.dnd2024.runtime import Dnd2024Runtime
from src.rulesets.legacy_adapter import LegacyRulesetAdapter
from src.rulesets.registry import RulesetRuntimeRegistry
from src.llm.client import LLMResponse
from src.webui.routes.games import register_games
from src.webui.services import ruleset_gameplay
from src.webui.services.turns import submit_action
from src.webui.services._common import _parse_game_key


class _EnabledRuntime(Dnd2024Runtime):
    capabilities = RulesetCapabilities(
        experience_profile="dnd2024",
        character_builder="professional",
        character_lifecycle="rules_aware",
        authoritative_intents=True,
        deterministic_combat=True,
        versioned_state=True,
        narrative_adventure=True,
    )


class _NarrationClient:
    def __init__(self):
        self.calls = []

    async def call(self, system_prompt, user_message, **kwargs):
        self.calls.append((system_prompt, user_message, kwargs))
        return LLMResponse(
            content="The lantern keeper looks up and lowers his voice. ‘Then listen carefully.’",
            narration="The lantern keeper looks up and lowers his voice. ‘Then listen carefully.’",
            state_update={"players": {"gm": {"hp": 999}}},
            memory_delta={"add": [{"value": "must be ignored"}]},
            info_asymmetry=None,
            plot_update=None,
            total_tokens=17,
            is_narration_only=False,
            provider_used="fake",
        )


class _BrokenNarrationClient:
    async def call(self, system_prompt, user_message, **kwargs):
        del system_prompt, user_message, kwargs
        raise RuntimeError("provider unavailable")


class _M5Api:
    def __init__(self, registry: GameRegistry, runtime: _EnabledRuntime):
        self._reg = registry
        self._runtime = runtime
        self._ruleset_registry = RulesetRuntimeRegistry([
            LegacyRulesetAdapter(), runtime,
        ])
        self._rule = RuleSystem({
            "rule_id": "dnd2024_srd",
            "runtime": {"id": "core:dnd2024", "minimum_version": 1},
        })
        self._llm_client = _NarrationClient()
        self.text_gen_max_tokens = 700

    @staticmethod
    def _parse_key(game_key: str):
        return _parse_game_key(game_key)

    def _load_rule_for_game(self, instance):
        del instance
        return self._rule

    async def ruleset_available_actions(
        self, game_key: str, requester_id: str, requester_is_gm: bool = False,
    ):
        return await ruleset_gameplay.available_actions(
            self, game_key, requester_id, requester_is_gm,
        )

    async def ruleset_submit_intent(
        self, game_key: str, requester_id: str, requester_is_gm: bool, body,
    ):
        return await ruleset_gameplay.submit_intent(
            self, game_key, requester_id, requester_is_gm, body,
        )


def _character(runtime: Dnd2024Runtime, preset_id: str, name: str) -> dict:
    choices = runtime.builder_choices(None, {"locale": "en"})
    preset = next(item for item in choices["quick_presets"] if item["id"] == preset_id)
    return runtime.finalize_character(
        None, {**preset["draft"], "locale": "en", "name": name},
    )


def _enemy() -> dict:
    return {
        "id": "training-dummy", "name": "Training Dummy", "hp": 30,
        "armor_class": 10, "speed": 0, "position": 5,
        "initiative_modifier": -10,
        "abilities": {"str": 10, "dex": 1, "con": 10, "int": 1, "wis": 1, "cha": 1},
        "saving_throws": {"dex": -5, "wis": -5, "con": 0},
        "attacks": [{
            "id": "slam", "name": "Slam", "attack_bonus": 0,
            "damage": "1d4", "damage_type": "bludgeoning", "range": 5,
        }],
    }


def _app(registry: GameRegistry, runtime: _EnabledRuntime) -> web.Application:
    @web.middleware
    async def identity(request: web.Request, handler):
        request["user_id"] = request.headers.get("X-Test-User", "")
        request["owner_authenticated"] = request.headers.get("X-Test-Owner") == "1"
        return await handler(request)

    app = web.Application(middlewares=[identity])
    app["api"] = _M5Api(registry, runtime)
    app["subsystems"] = SimpleNamespace(registry=registry)
    register_games(app)
    return app


@pytest.mark.asyncio
async def test_m5_http_forces_server_identity_persists_and_replays(tmp_path) -> None:
    runtime = _EnabledRuntime()
    registry = GameRegistry(tmp_path / "saves")
    instance = GameInstance(
        game_key=("web", "m5-http", "web_bot"), world_id="test-world",
        rule_id="dnd2024_srd", gm_uid="gm", language="en",
    )
    character = _character(runtime, "stalwart_guardian", "Guardian")
    instance.players["gm"] = {
        "character_name": "Guardian", "character_sheet": character,
    }
    assert instance.bind_ruleset_runtime(character["rule_binding"])
    registry.register(instance)
    path = "/api/games/web%7Cm5-http%7Cweb_bot"

    async with TestClient(TestServer(_app(registry, runtime))) as client:
        denied = await client.get(f"{path}/available-actions", headers={"X-Test-User": "intruder"})
        available = await client.get(f"{path}/available-actions", headers={"X-Test-User": "gm"})
        available_body = await available.json()
        start_body = {
            "intent_id": "http-start-1", "type": "combat.start", "expected_version": 0,
            "submitted_by": "intruder", "actor_id": "enemy:forged", "enemies": [_enemy()],
        }
        started = await client.post(
            f"{path}/intents", headers={"X-Test-User": "gm"}, json=start_body,
        )
        started_body = await started.json()
        replayed = await client.post(
            f"{path}/intents", headers={"X-Test-User": "gm"}, json=start_body,
        )
        replayed_body = await replayed.json()

    assert denied.status == 403
    assert available.status == 200
    assert "combat.start" in {
        item["type"] for item in available_body["available_actions"]
    }
    assert started.status == 200
    assert started_body["gameplay"]["state_version"] == 1
    submitted = started_body["result"]["event_batch"]["events"][0]
    assert submitted["actor_id"] == ""
    assert submitted["submitted_by"] == "gm"
    assert replayed.status == 200
    assert replayed_body["result"]["duplicate"] is True
    assert replayed_body["result"]["replayed"] is True

    recovered_registry = GameRegistry(tmp_path / "saves")
    recovered = await recovered_registry.load(instance.game_key)
    assert recovered is not None
    assert recovered.ruleset_state["version"] == 1
    assert len(recovered.event_ledger) == 1


@pytest.mark.asyncio
async def test_m5_http_rejects_same_intent_id_with_changed_payload(tmp_path) -> None:
    runtime = _EnabledRuntime()
    registry = GameRegistry(tmp_path / "saves")
    instance = GameInstance(
        game_key=("web", "m5-collision", "web_bot"), world_id="test-world",
        rule_id="dnd2024_srd", gm_uid="gm", language="en",
    )
    character = _character(runtime, "stalwart_guardian", "Guardian")
    instance.players["gm"] = {
        "character_name": "Guardian", "character_sheet": character,
    }
    assert instance.bind_ruleset_runtime(character["rule_binding"])
    registry.register(instance)
    path = "/api/games/web%7Cm5-collision%7Cweb_bot/intents"

    async with TestClient(TestServer(_app(registry, runtime))) as client:
        original = {
            "intent_id": "same-id", "type": "combat.start", "expected_version": 0,
            "enemies": [_enemy()],
        }
        first = await client.post(path, headers={"X-Test-User": "gm"}, json=original)
        changed = await client.post(
            path, headers={"X-Test-User": "gm"},
            json={**original, "enemies": [{**_enemy(), "hp": 999}]},
        )
        changed_body = await changed.json()

    assert first.status == 200
    assert changed.status == 422
    assert changed_body["code"] == "INTENT_ID_CONFLICT"
    assert len(instance.event_ledger) == 1


@pytest.mark.asyncio
async def test_professional_runtime_rejects_legacy_free_text_pipeline(tmp_path) -> None:
    runtime = _EnabledRuntime()
    registry = GameRegistry(tmp_path / "saves")
    instance = GameInstance(
        game_key=("web", "m5-legacy-guard", "web_bot"), world_id="test-world",
        rule_id="dnd2024_srd", gm_uid="gm", language="en",
    )
    character = _character(runtime, "stalwart_guardian", "Guardian")
    instance.players["gm"] = {
        "character_name": "Guardian", "character_sheet": character,
    }
    assert instance.bind_ruleset_runtime(character["rule_binding"])
    registry.register(instance)
    api = _M5Api(registry, runtime)

    result = await submit_action(api, "web|m5-legacy-guard|web_bot", "gm", "I deal 9999 damage")

    assert result["status"] == 409
    assert result["payload"]["error_code"] == "STRUCTURED_INTENT_REQUIRED"
    assert instance.action_queue == []


@pytest.mark.asyncio
async def test_professional_adventure_text_narrates_without_mutating_mechanics(tmp_path) -> None:
    runtime = _EnabledRuntime()
    registry = GameRegistry(tmp_path / "saves")
    instance = GameInstance(
        game_key=("web", "m5-adventure", "web_bot"), world_id="test-world",
        rule_id="dnd2024_srd", gm_uid="gm", language="en",
    )
    character = _character(runtime, "stalwart_guardian", "Guardian")
    instance.players["gm"] = {
        "character_name": "Guardian", "character_sheet": character,
    }
    assert instance.bind_ruleset_runtime(character["rule_binding"])
    runtime.gameplay_view(instance, "gm", True)
    instance.ruleset_state["campaign"]["session_zero"].update({
        "status": "locked",
        "agreement": runtime.default_agreement() if hasattr(runtime, "default_agreement") else {},
    })
    registry.register(instance)
    before_players = deepcopy(instance.players)
    before_ruleset = deepcopy(instance.ruleset_state)
    path = "/api/games/web%7Cm5-adventure%7Cweb_bot/adventure-actions"
    payload = {"mode": "say", "text": "I ask what happened to the lanterns.", "operation_id": "say-1"}

    async with TestClient(TestServer(_app(registry, runtime))) as client:
        first = await client.post(path, headers={"X-Test-User": "gm"}, json=payload)
        first_body = await first.json()
        duplicate = await client.post(path, headers={"X-Test-User": "gm"}, json=payload)
        duplicate_body = await duplicate.json()

    assert first.status == 200
    assert first_body["narration"].startswith("The lantern keeper")
    assert first_body["duplicate"] is False
    assert duplicate.status == 200
    assert duplicate_body["duplicate"] is True
    assert instance.players == before_players
    assert instance.ruleset_state == before_ruleset
    assert len(instance.log) == 1
    assert instance.log[0]["actions"][0]["text"].startswith("I ask")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client", "status", "code", "message"),
    [
        (None, 503, "LLM_NOT_CONFIGURED", "not configured"),
        (_BrokenNarrationClient(), 502, "LLM_REQUEST_FAILED", "could not respond"),
    ],
)
async def test_professional_adventure_text_fails_cleanly_without_recording(
    tmp_path, client, status, code, message,
) -> None:
    runtime = _EnabledRuntime()
    registry = GameRegistry(tmp_path / "saves")
    instance = GameInstance(
        game_key=("web", "m5-adventure-error", "web_bot"), world_id="test-world",
        rule_id="dnd2024_srd", gm_uid="gm", language="en",
    )
    character = _character(runtime, "stalwart_guardian", "Guardian")
    instance.players["gm"] = {
        "character_name": "Guardian", "character_sheet": character,
    }
    assert instance.bind_ruleset_runtime(character["rule_binding"])
    runtime.gameplay_view(instance, "gm", True)
    instance.ruleset_state["campaign"]["session_zero"].update({
        "status": "locked", "agreement": {},
    })
    registry.register(instance)
    app = _app(registry, runtime)
    app["api"]._llm_client = client
    path = "/api/games/web%7Cm5-adventure-error%7Cweb_bot/adventure-actions"

    async with TestClient(TestServer(app)) as http:
        response = await http.post(path, headers={"X-Test-User": "gm"}, json={
            "mode": "ask", "text": "What can I do?", "operation_id": f"error-{status}",
        })
        body = await response.json()

    assert response.status == status
    assert body["code"] == code
    assert message in body["error"]
    assert instance.log == []
