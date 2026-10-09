"""Lobby-reachable data that must not cross games or the room password:
the character-card library, and the scene text in the visitor lobby view."""

from __future__ import annotations

from aiohttp.test_utils import TestClient, TestServer
import pytest
import pytest_asyncio

from src.engine.modules import room_access
from src.webui.routes.character_cards import register_character_cards as register_character_cards
from test_game_query_routes_http import (
    ROOM_TOKEN,
    _make_game,
    _owner,
    _owner_password,  # noqa: F401
    play_env,  # noqa: F401
)
from test_share_gm_seat_guard import CONFIRM, _cookie, share_env  # noqa: F401


def _names(body: dict) -> set[str]:
    return {str(card.get("character_name")) for card in body.get("cards", [])}


@pytest_asyncio.fixture
async def cards_env(share_env, play_env):
    env = share_env
    register_character_cards(env.app)
    # A card shipped by an installed plugin: meant for any table.
    assert env.api.save_character_card({
        "character_name": "Plugin Hero", "source_plugin": "starter-pack",
        "attributes": {"str": 12},
    })["ok"]
    # Someone joins another game: the join saves that character server-wide.
    other_key, _other = _make_game(play_env, "cards-other-game", bind_adventure=False)
    joined = await env.api.create_player(
        other_key, {"character_name": "Other Game Hero", "attributes": {"str": 11}},
        assign_new_id=True,
    )
    assert joined["ok"]
    return env


def _cards_url(env, *, room_token=True):
    return f"/api/games/{env.key}/character-cards?share=1" + (
        f"&room_token={ROOM_TOKEN}" if room_token else ""
    )


@pytest.mark.asyncio
async def test_visitor_sees_only_plugin_cards(cards_env):
    env = cards_env
    stranger, _ = env.sessions.get_or_create(None)
    async with TestClient(TestServer(env.app)) as client:
        response = await client.get(_cards_url(env), headers=_cookie(stranger))
        body = await response.json()
    assert response.status == 200
    assert _names(body) == {"Plugin Hero"}


@pytest.mark.asyncio
async def test_seated_player_cannot_read_cards_from_another_game(cards_env):
    env = cards_env
    seat = {"X-Seat-Token": room_access.issue_seat_token(env.instance, "p1")}
    async with TestClient(TestServer(env.app)) as client:
        response = await client.get(_cards_url(env), headers=seat)
        body = await response.json()
    assert response.status == 200
    assert "Other Game Hero" not in _names(body)
    assert _names(body) == {"Plugin Hero"}


@pytest.mark.asyncio
async def test_owner_keeps_the_full_card_library(cards_env):
    env = cards_env
    async with TestClient(TestServer(env.app)) as client:
        response = await client.get(f"/api/games/{env.key}/character-cards", headers=_owner())
        body = await response.json()
    assert {"Plugin Hero", "Other Game Hero"} <= _names(body)


@pytest.mark.asyncio
async def test_seated_player_cannot_adopt_a_card_it_cannot_list(cards_env):
    env = cards_env
    hidden = next(
        card for card in env.api.list_character_cards()["cards"]
        if card.get("character_name") == "Other Game Hero"
    )
    seat = {"X-Seat-Token": room_access.issue_seat_token(env.instance, "p1"), **CONFIRM}
    async with TestClient(TestServer(env.app)) as client:
        response = await client.post(
            f"/api/games/{env.key}/character/p1/adopt-card?share=1&room_token={ROOM_TOKEN}",
            headers=seat, json={"card_id": hidden["id"]},
        )
        body = await response.json()
    assert response.status == 404, body
    assert body["error_code"] == "CARD_NOT_AVAILABLE"
    assert "Other Game Hero" not in str(body)


# ---- scene behind the room password -----------------------------------------


@pytest.mark.asyncio
async def test_password_room_lobby_hides_scene_without_room_token(share_env):
    env = share_env
    env.instance.scene = "The harbor at midnight"
    stranger, _ = env.sessions.get_or_create(None)
    async with TestClient(TestServer(env.app)) as client:
        hidden = await (await client.get(
            f"/api/games/{env.key}?share=1", headers=_cookie(stranger),
        )).json()
        wrong = await (await client.get(
            f"/api/games/{env.key}?share=1&room_token=wrong", headers=_cookie(stranger),
        )).json()
        shown = await (await client.get(
            f"/api/games/{env.key}?share=1&room_token={ROOM_TOKEN}", headers=_cookie(stranger),
        )).json()
    assert "scene" not in hidden and "scene" not in wrong
    assert hidden["has_room_password"] is True
    assert shown["scene"] == "The harbor at midnight"


@pytest.mark.asyncio
async def test_open_room_lobby_shows_scene(share_env, play_env):
    env = share_env
    open_key, open_game = _make_game(play_env, "open-room-scene", bind_adventure=False)
    open_game.scene = "Market square"
    stranger, _ = env.sessions.get_or_create(None)
    async with TestClient(TestServer(env.app)) as client:
        body = await (await client.get(
            f"/api/games/{open_key}?share=1", headers=_cookie(stranger),
        )).json()
    assert body["viewer"] == {"kind": "outsider"}
    assert body["scene"] == "Market square"


@pytest.mark.asyncio
async def test_seated_player_and_owner_keep_scene(share_env):
    env = share_env
    env.instance.scene = "The harbor at midnight"
    seat = {"X-Seat-Token": room_access.issue_seat_token(env.instance, "p1")}
    async with TestClient(TestServer(env.app)) as client:
        seated = await (await client.get(f"/api/games/{env.key}?share=1", headers=seat)).json()
        owner = await (await client.get(f"/api/games/{env.key}", headers=_owner())).json()
    assert seated["scene"] == owner["scene"] == "The harbor at midnight"
