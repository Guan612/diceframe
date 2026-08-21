from types import SimpleNamespace

from src.engine.game_instance import GameInstance, GameRegistry
from src.webui.services.games import list_games


def test_list_games_returns_most_recent_activity_first(tmp_path):
    registry = GameRegistry(tmp_path)
    registry.register(GameInstance(
        game_key=("web", "old", "bot"),
        rule_id="freeform_fantasy",
        world_name="Old",
        started_at="2026-08-01T10:00:00+00:00",
        last_activity="2026-08-02T10:00:00+00:00",
    ))
    registry.register(GameInstance(
        game_key=("web", "new", "bot"),
        rule_id="freeform_fantasy",
        world_name="New",
        started_at="2026-08-19T10:00:00+00:00",
        last_activity="2026-08-20T10:00:00+00:00",
    ))
    registry.register(GameInstance(
        game_key=("web", "undated", "bot"),
        rule_id="freeform_fantasy",
        world_name="Undated",
    ))

    result = list_games(SimpleNamespace(_reg=registry))

    assert [game["game_key"] for game in result["games"]] == [
        "web|new|bot",
        "web|old|bot",
        "web|undated|bot",
    ]
    assert result["games"][0]["started_at"] == "2026-08-19T10:00:00+00:00"
