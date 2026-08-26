from __future__ import annotations

from types import SimpleNamespace

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.engine.game_instance import GameInstance, GameRegistry
from src.rules.rule_system import RuleSystem
from src.rulesets.dnd2024.runtime import Dnd2024Runtime
from src.rulesets.legacy_adapter import LegacyRulesetAdapter
from src.rulesets.registry import RulesetRuntimeRegistry
from src.webui.routes.games import register_games
from src.webui.services import ruleset_gameplay
from src.webui.services._common import _parse_game_key


class _MemoryProbe:
    def __init__(self):
        self.calls: list[tuple[str, dict, int]] = []

    async def apply_delta(self, game_key: str, delta: dict, round_number: int) -> None:
        self.calls.append((game_key, delta, round_number))


class _M6Api:
    def __init__(self, registry: GameRegistry, runtime: Dnd2024Runtime, memory: _MemoryProbe):
        self._reg = registry
        self._mem = memory
        self._ruleset_registry = RulesetRuntimeRegistry([LegacyRulesetAdapter(), runtime])
        self._rule = RuleSystem({
            "rule_id": "dnd2024_srd",
            "runtime": {"id": "core:dnd2024", "minimum_version": 1},
        })

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


def _character(runtime: Dnd2024Runtime) -> dict:
    choices = runtime.builder_choices(None, {"locale": "en"})
    preset = next(item for item in choices["quick_presets"] if item["id"] == "stalwart_guardian")
    return runtime.finalize_character(
        None, {**preset["draft"], "locale": "en", "name": "HTTP Guide"},
    )


def _app(registry: GameRegistry, runtime: Dnd2024Runtime, memory: _MemoryProbe) -> web.Application:
    @web.middleware
    async def identity(request: web.Request, handler):
        request["user_id"] = request.headers.get("X-Test-User", "")
        request["owner_authenticated"] = request.headers.get("X-Test-Owner") == "1"
        return await handler(request)

    app = web.Application(middlewares=[identity])
    app["api"] = _M6Api(registry, runtime, memory)
    app["subsystems"] = SimpleNamespace(registry=registry)
    register_games(app)
    return app


@pytest.mark.asyncio
async def test_m6_http_runs_confirmed_session_and_tutorial_into_memory(tmp_path) -> None:
    runtime = Dnd2024Runtime()
    memory = _MemoryProbe()
    registry = GameRegistry(tmp_path / "saves")
    instance = GameInstance(
        game_key=("web", "m6-http", "web_bot"), world_id="test-world",
        rule_id="dnd2024_srd", gm_uid="gm", language="en",
    )
    character = _character(runtime)
    instance.players["gm"] = {
        "character_name": "HTTP Guide", "character_sheet": character,
    }
    assert instance.bind_ruleset_runtime(character["rule_binding"])
    instance.world_id = "greymoor"
    package = runtime._adventure_loader.resolve("core:lanterns_of_greymoor", "en")
    assert instance.bind_adventure(package.binding("greymoor"))
    registry.register(instance)
    path = "/api/games/web%7Cm6-http%7Cweb_bot"
    headers = {"X-Test-User": "gm"}
    defaults = runtime.gameplay_view(instance, "gm", True)["campaign"]["session_zero_defaults"]

    async with TestClient(TestServer(_app(registry, runtime, memory))) as client:
        version = 0

        async def submit(intent_type: str, **fields):
            nonlocal version
            response = await client.post(
                f"{path}/intents", headers=headers,
                json={
                    "intent_id": f"http-{intent_type}-{version}",
                    "type": intent_type,
                    "expected_version": version,
                    "submitted_by": "forged",
                    **fields,
                },
            )
            body = await response.json()
            assert response.status == 200, body
            version = body["gameplay"]["state_version"]
            return body

        proposed = await submit("session_zero.propose", agreement=defaults)
        submitted = proposed["result"]["event_batch"]["events"][0]
        assert submitted["submitted_by"] == "gm"
        await submit("session_zero.respond", response="accept")
        await submit("session_zero.lock")
        await submit("tutorial.start", adventure_id="lanterns_of_greymoor")
        await submit("tutorial.choose", choice_id="inspect_cold_ash")
        await submit("tutorial.choose", choice_id="reassure_mira")
        await submit("tutorial.choose", choice_id="follow_small_tracks")

        view = runtime.gameplay_view(instance, "gm", True)
        preset = next(
            item for item in view["encounter_presets"] if item["id"] == "first_skirmish"
        )
        await submit(
            "combat.start", encounter_preset_id="first_skirmish",
            enemies=preset["enemies"],
        )
        await submit("combat.end")
        await submit("tutorial.choose", choice_id="secure_the_glade")
        completed = await submit("tutorial.choose", choice_id="return_the_light")

    assert completed["gameplay"]["campaign"]["tutorial"]["status"] == "completed"
    assert len(memory.calls) == 3
    assert all(call[0] == str(instance.game_key) for call in memory.calls)
    assert all(call[1]["add"][0]["confidence"] == 1.0 for call in memory.calls)
    recovered_registry = GameRegistry(tmp_path / "saves")
    recovered = await recovered_registry.load(instance.game_key)
    assert recovered is not None
    assert recovered.ruleset_state["campaign"]["tutorial"]["status"] == "completed"
    assert len(recovered.ruleset_state["campaign"]["chapter_summaries"]) == 3
    assert len(recovered.log) == 8
    assert all(
        action.get("text") not in {"执行规则行动", "Resolve a rules action"}
        for entry in recovered.log for action in entry.get("actions", [])
    )
    assert any(
        "遭遇战开始" in str(entry.get("gm_response") or "")
        or "Encounter started" in str(entry.get("gm_response") or "")
        for entry in recovered.log
    )
