from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from src.engine.game_instance import GameInstance, GameRegistry
from src.rulesets.dnd2024.runtime import Dnd2024Runtime
from src.rulesets.registry import RulesetRuntimeRegistry
from src.webui.services.game_queries import game_detail, list_games, player_context


def test_list_projects_legacy_rule_without_mutating_instance(tmp_path: Path) -> None:
    registry = GameRegistry(tmp_path)
    instance = GameInstance(
        game_key=("web", "legacy", "bot"),
        world_id="legacy-world",
        rule_id="",
    )
    registry.register(instance)
    handler = SimpleNamespace(
        _load_world_template=lambda _world_id: {
            "default_rule": "freeform_fantasy",
        },
    )

    result = list_games(SimpleNamespace(_reg=registry, _handler=handler))

    assert result["games"][0]["rule_id"] == "freeform_fantasy"
    assert instance.rule_id == ""


def test_dnd_detail_projection_is_runtime_owned_and_read_only(
    tmp_path: Path,
) -> None:
    registry = GameRegistry(tmp_path)
    instance = GameInstance(
        game_key=("web", "dnd", "bot"),
        world_id="dnd-world",
        rule_id="dnd2024_srd",
    )
    instance.players["hero"] = {
        "character_name": "Hero",
        "character_sheet": {
            "ruleset_character": {
                "build": {"level": 1, "class_levels": [{"level": 1}]},
            },
        },
    }
    instance.ruleset_runtime = {
        "id": "core:dnd2024",
        "version": 1,
        "requested_minimum_version": 1,
    }
    instance.ruleset_state = {"legacy": {"kept": True}}
    registry.register(instance)
    rule = SimpleNamespace(template={
        "runtime": {"id": "core:dnd2024", "minimum_version": 1},
    })
    api = SimpleNamespace(
        _reg=registry,
        _parse_key=lambda game_key: tuple(game_key.split("|")),
        _load_rule_for_game=lambda _instance: rule,
        _ruleset_registry=RulesetRuntimeRegistry([Dnd2024Runtime()]),
    )
    before = deepcopy(instance.ruleset_state)

    detail = game_detail(api, "web|dnd|bot")

    assert detail is not None
    assert detail["ruleset_runtime"]["id"] == "core:dnd2024"
    assert detail["advancement"] == {
        "mode": "milestone",
        "authority": "ai_gm",
        "players": [{
            "user_id": "hero",
            "character_name": "Hero",
            "level": 1,
            "xp": 0,
            "next_level_xp": 300,
            "entitled": False,
            "target_level": 0,
            "source": "",
        }],
    }
    assert instance.ruleset_state == before


def test_generic_game_queries_do_not_import_dnd() -> None:
    source = (
        Path(__file__).parents[1]
        / "src"
        / "webui"
        / "services"
        / "game_queries.py"
    ).read_text(encoding="utf-8")

    assert "src.rulesets.dnd2024" not in source


def test_player_context_projects_server_owned_identity_flags() -> None:
    assert player_context(
        preview=True, delegate=False, user_id="player-1",
    ) == {
        "ok": True,
        "preview": True,
        "delegate": False,
        "user_id": "player-1",
    }
