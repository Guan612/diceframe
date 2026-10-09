"""Real HTTP regressions for share identity and GM-seat isolation."""

from __future__ import annotations

from copy import deepcopy
import re
from types import SimpleNamespace
from uuid import UUID

from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.engine.game_state import GameState
from src.engine.modules import room_access
from src.webui.session import SessionManager, session_middleware
from test_game_query_routes_http import (
    ROOM_PASSWORD,
    ROOM_TOKEN,
    _make_app,
    _make_game,
    _owner,
    _owner_password,  # noqa: F401
    play_env,  # noqa: F401
)


@pytest.fixture
def share_env(play_env, tmp_path):
    key, instance = _make_game(
        play_env, "share-guard", bind_adventure=False, room_password=ROOM_PASSWORD,
    )
    instance.state = GameState.ACTIVE_ACTION
    instance.players[instance.gm_uid] = {"character_name": "GM", "character_sheet": {}}
    instance.players["p2"] = {"character_name": "乙", "character_sheet": {}}
    instance.private_log = {
        "p1": [{"round": 1, "text": "A private", "source": "gm"}],
        "p2": [{"round": 1, "text": "B private", "source": "gm"}],
    }
    sessions = SessionManager(tmp_path / "sessions")
    token, _ = sessions.get_or_create(None)
    sessions.rebind(token, "p1")
    # Existing sessions keep their identity, including a previously bound GM.
    gm_token = "existing-gm-session"
    sessions._sessions[gm_token] = {"user_id": instance.gm_uid, "name": ""}
    app = _make_app(play_env)
    app["session_manager"] = sessions
    app.middlewares.insert(0, session_middleware)
    return SimpleNamespace(
        app=app, key=key, instance=instance, sessions=sessions,
        token=token, gm_token=gm_token, api=play_env.api,
    )


def _cookie(token):
    return {"Cookie": f"trpg_session={token}"}


def _share_url(env, path, uid=None):
    url = f"/api/games/{env.key}/{path}?share=1&room_token={ROOM_TOKEN}"
    return url if uid is None else f"{url}&user={uid}"


def _seat(env, uid):
    return {"X-Seat-Token": room_access.issue_seat_token(env.instance, uid)}


def _assert_seat_token_required(response, body):
    assert response.status == 401, body
    assert body["ok"] is False
    assert body["error_code"] == "SEAT_TOKEN_REQUIRED"


def _assert_gm_denied(response, body):
    assert response.status == 403, body
    assert body == {
        "ok": False,
        "error_code": "GM_SEAT_REQUIRES_OWNER",
        "error": "GM 席位需要房主登录",
    }


@pytest.mark.asyncio
async def test_f2_share_query_cannot_read_gm_private_log(share_env):
    env = share_env
    async with TestClient(TestServer(env.app)) as client:
        response = await client.get(
            _share_url(env, "private-log", env.instance.gm_uid),
            headers=_cookie(env.token),
        )
        body = await response.json()
    # ?user= is no proof of any seat, the GM's included.
    _assert_seat_token_required(response, body)


@pytest.mark.asyncio
async def test_f2_share_cookie_cannot_read_gm_private_log(share_env):
    env = share_env
    async with TestClient(TestServer(env.app)) as client:
        response = await client.get(
            _share_url(env, "private-log"), headers=_cookie(env.gm_token),
        )
        body = await response.json()
    _assert_seat_token_required(response, body)


@pytest.mark.asyncio
async def test_f2_seat_token_for_gm_seat_is_still_rejected(share_env):
    """Even a credential stored for the GM seat cannot act as GM via a share link."""
    env = share_env
    headers = {**_cookie(env.token), **_seat(env, env.instance.gm_uid)}
    async with TestClient(TestServer(env.app)) as client:
        response = await client.get(_share_url(env, "private-log"), headers=headers)
        body = await response.json()
    _assert_gm_denied(response, body)


@pytest.mark.asyncio
async def test_f2_gm_session_cannot_read_lobby_detail_as_gm(share_env):
    env = share_env
    async with TestClient(TestServer(env.app)) as client:
        response = await client.get(
            f"/api/games/{env.key}?share=1&room_token={ROOM_TOKEN}",
            headers=_cookie(env.gm_token),
        )
        body = await response.json()
    _assert_gm_denied(response, body)


@pytest.mark.asyncio
@pytest.mark.parametrize("identity_path", ["query", "cookie"])
async def test_share_gm_cannot_change_player_control(share_env, identity_path):
    env = share_env
    before = deepcopy(env.instance.players)
    uid = env.instance.gm_uid if identity_path == "query" else None
    token = env.token if identity_path == "query" else env.gm_token
    async with TestClient(TestServer(env.app)) as client:
        response = await client.post(
            _share_url(env, "players/p2/control", uid),
            headers=_cookie(token), json={"mode": "ai"},
        )
        body = await response.json()
    _assert_seat_token_required(response, body)
    assert env.instance.players == before


@pytest.mark.asyncio
@pytest.mark.parametrize("identity_path", ["query", "cookie"])
async def test_owner_gm_share_keeps_private_log_access(share_env, identity_path):
    env = share_env
    uid = env.instance.gm_uid if identity_path == "query" else None
    expected = env.api.private_log(env.key)
    async with TestClient(TestServer(env.app)) as client:
        response = await client.get(
            _share_url(env, "private-log", uid),
            headers={**_owner(), **_cookie(env.gm_token)},
        )
        body = await response.json()
    assert response.status == 200
    assert body == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("delegate", [False, True], ids=["preview", "delegate"])
async def test_owner_player_view_keeps_private_log_isolation(share_env, delegate):
    env = share_env
    url = _share_url(env, "private-log", "p1") + ("&delegate=1" if delegate else "")
    async with TestClient(TestServer(env.app)) as client:
        response = await client.get(
            url, headers={**_owner(), **_cookie(env.gm_token)},
        )
        body = await response.json()
    assert response.status == 200
    assert body == env.api.private_log_for_user(env.key, "p1")
    assert [message["text"] for message in body["messages"]] == ["A private"]


@pytest.mark.asyncio
async def test_regular_player_share_keeps_private_log_access(share_env):
    env = share_env
    async with TestClient(TestServer(env.app)) as client:
        response = await client.get(
            _share_url(env, "private-log"),
            headers={**_cookie(env.token), **_seat(env, "p1")},
        )
        body = await response.json()
    assert response.status == 200
    assert body == env.api.private_log_for_user(env.key, "p1")


@pytest.mark.asyncio
@pytest.mark.parametrize("identity_path", ["query", "cookie"])
async def test_player_share_without_seat_token_is_rejected(share_env, identity_path):
    """Neither the public uid nor a bound cookie alone acts as a seat."""
    env = share_env
    uid = "p1" if identity_path == "query" else None
    async with TestClient(TestServer(env.app)) as client:
        response = await client.get(
            _share_url(env, "private-log", uid), headers=_cookie(env.token),
        )
        body = await response.json()
    _assert_seat_token_required(response, body)


@pytest.mark.asyncio
async def test_seat_token_beats_a_forged_user_param(share_env):
    """A holds A's token and names B in ?user=: the request still acts as A."""
    env = share_env
    async with TestClient(TestServer(env.app)) as client:
        response = await client.get(
            _share_url(env, "private-log", "p2"),
            headers={**_cookie(env.token), **_seat(env, "p1")},
        )
        body = await response.json()
    assert response.status == 200
    assert body == env.api.private_log_for_user(env.key, "p1")
    assert [message["text"] for message in body["messages"]] == ["A private"]


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["not-a-real-token", "revoked", "other-game"])
async def test_invalid_seat_tokens_are_rejected(share_env, play_env, token):
    env = share_env
    if token == "revoked":
        token = room_access.issue_seat_token(env.instance, "p1")
        room_access.revoke_seat_token(env.instance, "p1")
    elif token == "other-game":
        _key, other = _make_game(play_env, "share-guard-other", bind_adventure=False)
        token = room_access.issue_seat_token(other, "p1")
    async with TestClient(TestServer(env.app)) as client:
        response = await client.get(
            _share_url(env, "private-log", "p1"),
            headers={**_cookie(env.token), "X-Seat-Token": token},
        )
        body = await response.json()
    assert response.status == 401, body
    assert body["error_code"] == "SEAT_TOKEN_INVALID"
    assert "A private" not in str(body)


@pytest.mark.asyncio
async def test_reissued_seat_token_invalidates_the_old_one(share_env):
    env = share_env
    old = room_access.issue_seat_token(env.instance, "p1")
    new = room_access.issue_seat_token(env.instance, "p1")
    async with TestClient(TestServer(env.app)) as client:
        stale = await client.get(_share_url(env, "private-log"), headers={"X-Seat-Token": old})
        fresh = await client.get(_share_url(env, "private-log"), headers={"X-Seat-Token": new})
        stale_status, fresh_status = stale.status, fresh.status
    assert (stale_status, fresh_status) == (401, 200)


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", [False, True], ids=["shared-player", "owner"])
async def test_f4_join_gm_seat_does_not_rebind_session(share_env, owner):
    env = share_env
    original_uid = env.sessions._sessions[env.token]["user_id"]
    headers = {**_cookie(env.token), **(_owner() if owner else {})}
    async with TestClient(TestServer(env.app)) as client:
        response = await client.post(
            _share_url(env, "players"), headers=headers,
            json={"user_id": env.instance.gm_uid},
        )
        body = await response.json()
    if owner:
        assert response.status == 200
        assert body["ok"] is True
        assert body["user_id"] == env.instance.gm_uid
        assert body["reused"] is True
    else:
        # Naming an existing seat without its token is refused outright.
        assert response.status == 403, body
        assert body["error_code"] == "SEAT_TOKEN_REQUIRED"
    assert env.sessions._sessions[env.token]["user_id"] == original_uid
    assert env.sessions._sessions[env.token]["user_id"] != env.instance.gm_uid
    reloaded = SessionManager(env.sessions._path.parent)
    assert reloaded.get_or_create(env.token) == (env.token, original_uid)


@pytest.mark.asyncio
async def test_rejoin_with_seat_token_rebinds_session(share_env):
    env = share_env
    async with TestClient(TestServer(env.app)) as client:
        response = await client.post(
            _share_url(env, "players"),
            headers={**_cookie(env.token), **_seat(env, "p2")},
            json={"join_as_new": False},
        )
        body = await response.json()
    assert response.status == 200
    assert body["ok"] is True
    assert body["user_id"] == "p2"
    assert body["reused"] is True
    assert "seat_token" not in body
    assert env.sessions._sessions[env.token]["user_id"] == "p2"


@pytest.mark.asyncio
async def test_f4_rejoin_other_seat_without_token_is_refused(share_env):
    """Naming another seat's uid neither rebinds the session nor claims the seat."""
    env = share_env
    from src.engine.player_control import get_control, set_control

    set_control(env.instance, "p2", "ai")
    before_control = get_control(env.instance, "p2")
    async with TestClient(TestServer(env.app)) as client:
        response = await client.post(
            _share_url(env, "players"), headers=_cookie(env.token),
            json={"user_id": "p2"},
        )
        body = await response.json()
    assert response.status == 403, body
    assert body["error_code"] == "SEAT_TOKEN_REQUIRED"
    assert env.sessions._sessions[env.token]["user_id"] == "p1"
    assert get_control(env.instance, "p2") == before_control


@pytest.mark.asyncio
async def test_new_seat_returns_its_token_once(share_env):
    env = share_env
    fresh_token, _ = env.sessions.get_or_create(None)
    async with TestClient(TestServer(env.app)) as client:
        response = await client.post(
            _share_url(env, "players"), headers=_cookie(fresh_token),
            json={"character_name": "Third", "join_as_new": True},
        )
        body = await response.json()
        uid = body["user_id"]
        seat_token = body["seat_token"]
        private = await client.get(
            _share_url(env, "private-log"), headers={"X-Seat-Token": seat_token},
        )
        private_status = private.status
    assert response.status == 200
    assert room_access.verify_seat_token(env.instance, seat_token) == uid
    assert private_status == 200
    stored = env.instance.modules["room_access"]["seat_credentials"][uid]
    assert seat_token not in str(stored)


def test_new_sessions_have_distinct_eight_hex_user_ids(tmp_path):
    manager = SessionManager(tmp_path)
    first_token, first_uid = manager.get_or_create(None)
    second_token, second_uid = manager.get_or_create(None)
    assert first_token != second_token
    assert first_uid != second_uid
    for uid in (first_uid, second_uid):
        assert re.fullmatch(r"web_[0-9a-f]{8}", uid)


def test_new_session_retries_colliding_user_id(tmp_path, monkeypatch):
    manager = SessionManager(tmp_path)
    colliding = UUID("12345678" + "0" * 24)
    fresh = UUID("87654321" + "0" * 24)
    manager._sessions["existing-token"] = {
        "user_id": f"web_{colliding.hex[:8]}", "name": "",
    }
    generated = iter([colliding, fresh])
    monkeypatch.setattr("src.webui.session.uuid.uuid4", lambda: next(generated))

    token, uid = manager.get_or_create("new-token")
    assert (token, uid) == ("new-token", f"web_{fresh.hex[:8]}")
    assert manager.get_or_create("existing-token") == (
        "existing-token", f"web_{colliding.hex[:8]}",
    )
    assert SessionManager(tmp_path).get_or_create(token) == (token, uid)


def test_f5_new_session_uid_is_independent_of_client_token(tmp_path, monkeypatch):
    manager = SessionManager(tmp_path)
    # Fix server randomness so this regression cannot fail by random collision.
    monkeypatch.setattr("src.webui.session.uuid.uuid4", lambda: UUID("12345678" + "0" * 24))
    supplied_token = "deadbeef" + "0" * 24
    token, uid = manager.get_or_create(supplied_token)
    assert token == supplied_token
    assert uid != "web_deadbeef"
    assert uid == "web_12345678"
    assert manager.get_or_create(token) == (token, uid)
    assert SessionManager(tmp_path).get_or_create(token) == (token, uid)


def test_new_session_without_token_uses_separate_uid_randomness(tmp_path, monkeypatch):
    manager = SessionManager(tmp_path)
    generated = iter([UUID("deadbeef" + "0" * 24), UUID("12345678" + "0" * 24)])
    monkeypatch.setattr("src.webui.session.uuid.uuid4", lambda: next(generated))
    token, uid = manager.get_or_create(None)
    assert token == "deadbeef" + "0" * 24
    assert uid == "web_12345678"


def test_existing_session_keeps_legacy_uid(tmp_path, monkeypatch):
    manager = SessionManager(tmp_path)
    token = "deadbeef" + "0" * 24
    manager._sessions[token] = {"user_id": "web_deadbeef", "name": ""}

    def unexpected_randomness():
        pytest.fail("Existing sessions must not allocate a new identity")

    monkeypatch.setattr("src.webui.session.uuid.uuid4", unexpected_randomness)
    assert manager.get_or_create(token) == (token, "web_deadbeef")


@pytest.mark.asyncio
async def test_share_player_cannot_edit_another_seats_character(share_env):
    env = share_env
    before = deepcopy(env.instance.players["p2"])
    async with TestClient(TestServer(env.app)) as client:
        response = await client.put(
            _share_url(env, "character/p2", "p2"),
            headers={**_cookie(env.token), **_seat(env, "p1")},
            json={"character_name": "hijacked"},
        )
    assert response.status == 403
    assert env.instance.players["p2"] == before


# ---- seat-token issuance --------------------------------------------------


@pytest.mark.asyncio
async def test_owner_issues_and_rotates_a_takeover_token(share_env):
    env = share_env
    old = room_access.issue_seat_token(env.instance, "p2")
    async with TestClient(TestServer(env.app)) as client:
        response = await client.post(
            _share_url(env, "players/p2/seat-token"), headers=_owner(),
        )
        body = await response.json()
    assert response.status == 200, body
    assert body["user_id"] == "p2"
    assert room_access.verify_seat_token(env.instance, body["seat_token"]) == "p2"
    assert room_access.verify_seat_token(env.instance, old) is None


@pytest.mark.asyncio
async def test_seat_player_cannot_issue_another_seats_token(share_env):
    env = share_env
    async with TestClient(TestServer(env.app)) as client:
        response = await client.post(
            _share_url(env, "players/p2/seat-token"),
            headers={**_cookie(env.token), **_seat(env, "p1")},
        )
        body = await response.json()
    assert response.status == 403, body
    assert "seat_token" not in body
    assert not room_access.has_seat_token(env.instance, "p2")


@pytest.mark.asyncio
async def test_gm_seat_never_gets_a_share_token(share_env):
    env = share_env
    async with TestClient(TestServer(env.app)) as client:
        response = await client.post(
            _share_url(env, f"players/{env.instance.gm_uid}/seat-token"), headers=_owner(),
        )
        body = await response.json()
    assert response.status == 400, body
    assert body["error_code"] == "GM_SEAT_REQUIRES_OWNER"
    assert not room_access.has_seat_token(env.instance, env.instance.gm_uid)


@pytest.mark.asyncio
async def test_bound_session_claims_its_seat_token_once(share_env):
    """Players who joined before seat tokens migrate on their next page open."""
    env = share_env
    async with TestClient(TestServer(env.app)) as client:
        first = await client.post(_share_url(env, "seat-token/claim"), headers=_cookie(env.token))
        first_body = await first.json()
        again = await client.post(_share_url(env, "seat-token/claim"), headers=_cookie(env.token))
        again_body = await again.json()
    assert first.status == 200, first_body
    assert first_body["user_id"] == "p1"
    assert room_access.verify_seat_token(env.instance, first_body["seat_token"]) == "p1"
    # A second claim never rotates the credential away from the seat's devices.
    assert again.status == 409
    assert again_body["error_code"] == "SEAT_TOKEN_EXISTS"
    assert room_access.verify_seat_token(env.instance, first_body["seat_token"]) == "p1"


@pytest.mark.asyncio
async def test_unbound_or_gm_session_cannot_claim(share_env):
    env = share_env
    stranger, _ = env.sessions.get_or_create(None)
    async with TestClient(TestServer(env.app)) as client:
        unbound = await client.post(_share_url(env, "seat-token/claim"), headers=_cookie(stranger))
        unbound_body = await unbound.json()
        gm = await client.post(_share_url(env, "seat-token/claim"), headers=_cookie(env.gm_token))
        gm_body = await gm.json()
    assert unbound.status == 403
    assert unbound_body["error_code"] == "SEAT_NOT_BOUND"
    _assert_gm_denied(gm, gm_body)
    assert env.instance.modules["room_access"]["seat_credentials"] == {}
