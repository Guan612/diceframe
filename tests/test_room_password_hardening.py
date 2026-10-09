"""Room password hardening: hashed storage, expiring hashed room tokens,
new-password length rule, export/import scrubbing and the player join flow."""

from __future__ import annotations

import hashlib
import json
import zipfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src import password_hashing
from src.engine.game_instance import GameInstance
from src.engine.module_state import ModuleStateError
from src.engine.modules import room_access
from src.migrations.instance import (
    CURRENT_INSTANCE_SCHEMA_VERSION,
    _migrate_v37_to_v38,
    migrate_game_state_payload,
    rebind_imported_game_state_payload,
)
from src.webui.routes.games import register_games
from src.webui.services import game_packages
from src.webui.services import room_password as room_password_svc
from test_game_query_routes_http import (
    GM_UID,
    _make_app,
    _make_game,
    _owner,
    _player_url,
    _seat,
    play_env,  # noqa: F401
)

PASSWORD = "correct horse"
V2_SLOT = {
    "schema_version": 2,
    "max_players": 5,
    "player_access_open": True,
    "bot_bind_token": "bind-secret",
    "room_password": PASSWORD,
    "room_token": "legacy-room-token",
    "seat_credentials": {"p1": {"hash": "seat-digest", "issued_at": "t", "epoch": 1}},
}
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _instance(password: str = "") -> GameInstance:
    instance = GameInstance(game_key=("web", "room-pw", "bot"), gm_uid="gm")
    instance.players = {"p1": {"character_name": "p1", "character_sheet": {}}}
    if password:
        instance.set_room_password(password)
    return instance


def _v37_payload(slot=None) -> dict:
    return {
        "instance_schema_version": 37,
        "game_key": ["web", "room-pw", "bot"],
        "state": "created",
        "modules": {"room_access": deepcopy(V2_SLOT if slot is None else slot)},
    }


# ---- migration 37 -> 38 ------------------------------------------------------


def test_v37_plaintext_password_becomes_a_hash_without_losing_access() -> None:
    original = _v37_payload()
    before = deepcopy(original)
    migrated = migrate_game_state_payload(original)
    assert original == before  # input is never mutated
    assert migrated["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION == 38
    slot = migrated["modules"]["room_access"]
    assert slot["schema_version"] == room_access.SCHEMA_VERSION == 3
    assert "room_password" not in slot and "room_token" not in slot
    assert PASSWORD not in json.dumps(slot) and "legacy-room-token" not in json.dumps(slot)
    # Everything else is carried verbatim.
    for key in ("max_players", "player_access_open", "bot_bind_token", "seat_credentials"):
        assert slot[key] == V2_SLOT[key]
    instance = GameInstance.from_dict(migrated)
    assert room_access.verify_room_password(instance, PASSWORD)
    assert not room_access.verify_room_password(instance, PASSWORD + "x")
    # Players already inside keep their (now hashed, now expiring) room token.
    assert room_access.verify_room_token(instance, "legacy-room-token")
    [record] = slot["room_tokens"]
    assert record["hash"] == hashlib.sha256(b"legacy-room-token").hexdigest()
    expires = datetime.fromisoformat(record["expires_at"])
    assert timedelta(days=29) < expires - datetime.now(timezone.utc) <= timedelta(days=30)
    assert not room_access.verify_room_token(instance, "legacy-room-token", now=expires)


def test_v37_migration_is_idempotent() -> None:
    migrated = migrate_game_state_payload(_v37_payload())
    assert migrate_game_state_payload(migrated) == migrated
    step = _migrate_v37_to_v38(_v37_payload())
    assert _migrate_v37_to_v38(deepcopy(step)) == step


@pytest.mark.parametrize("slot", [
    {"schema_version": 9, "room_password": "future-plaintext", "opaque": True},
    {"schema_version": 3, "room_password_hash": "", "room_tokens": []},
])
def test_v37_migration_never_touches_a_current_or_future_slot(slot) -> None:
    migrated = _migrate_v37_to_v38(_v37_payload(slot))
    assert migrated["modules"]["room_access"] == slot
    assert migrated["instance_schema_version"] == 38


@pytest.mark.parametrize("modules", [None, [], "corrupt", {}])
def test_v37_migration_materializes_a_fresh_slot(modules) -> None:
    migrated = _migrate_v37_to_v38({"instance_schema_version": 37, "modules": modules})
    assert migrated["modules"]["room_access"] == room_access.fresh()


@pytest.mark.parametrize("password, locked", [
    ("", False), (None, False), (0, False), ([], False),
    (12345678, True), ({"opaque": 1}, True),
])
def test_v37_unusable_password_values_fail_closed(password, locked) -> None:
    migrated = migrate_game_state_payload(_v37_payload({**V2_SLOT, "room_password": password}))
    instance = GameInstance.from_dict(migrated)
    assert instance.has_room_password is locked
    assert not room_access.verify_room_password(instance, str(password))
    # Without a password there is nothing a token could unlock. A locked room
    # keeps the token of players already inside, as before the upgrade.
    assert room_access.verify_room_token(instance, "legacy-room-token") is locked


def test_short_legacy_password_keeps_working_after_upgrade() -> None:
    migrated = migrate_game_state_payload(_v37_payload({**V2_SLOT, "room_password": "abcd"}))
    instance = GameInstance.from_dict(migrated)
    assert room_access.verify_room_password(instance, "abcd")


# ---- password verification -----------------------------------------------------


def test_verify_is_exact_and_rejects_plaintext_storage() -> None:
    instance = _instance(PASSWORD)
    assert room_access.verify_room_password(instance, PASSWORD)
    for wrong in ("", " " + PASSWORD, PASSWORD.upper(), "correct", None):
        assert not room_access.verify_room_password(instance, wrong)  # type: ignore[arg-type]
    # A plaintext value in the hash field (tampered save) never verifies.
    instance.modules["room_access"]["room_password_hash"] = PASSWORD
    assert instance.has_room_password is True
    assert not room_access.verify_room_password(instance, PASSWORD)


def test_password_and_token_checks_use_constant_time_compare(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    real = password_hashing.hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(password_hashing.hmac, "compare_digest", spy)
    instance = _instance(PASSWORD)
    assert room_access.verify_room_password(instance, PASSWORD)
    assert not room_access.verify_room_password(instance, "wrong-password")
    assert len(calls) == 2

    token_calls: list[str] = []
    monkeypatch.setattr(room_access.hmac, "compare_digest", lambda a, b: token_calls.append(a) or real(a, b))
    first, _ = room_access.issue_room_token(instance, now=NOW)
    room_access.issue_room_token(instance, now=NOW)
    room_access.issue_room_token(instance, now=NOW)
    assert room_access.verify_room_token(instance, first, now=NOW)
    # Every live record is compared, even after the first one matched.
    assert len(token_calls) == 3


def test_set_password_rejects_writes_to_a_future_slot() -> None:
    slot = {"schema_version": 9, "opaque": True}
    instance = GameInstance(game_key=("web", "future", "bot"), modules={"room_access": deepcopy(slot)})
    with pytest.raises(ModuleStateError):
        room_access.set_room_password(instance, PASSWORD)
    assert instance.modules["room_access"] == slot


# ---- room tokens ---------------------------------------------------------------


def test_room_token_is_stored_hashed_and_expires() -> None:
    instance = _instance(PASSWORD)
    token, expires_at = room_access.issue_room_token(instance, ttl_seconds=3600, now=NOW)
    stored = json.dumps(instance.to_dict())
    assert token not in stored
    assert hashlib.sha256(token.encode()).hexdigest() in stored
    assert datetime.fromisoformat(expires_at) == NOW + timedelta(hours=1)
    assert room_access.verify_room_token(instance, token, now=NOW + timedelta(minutes=59))
    assert not room_access.verify_room_token(instance, token, now=NOW + timedelta(hours=1))
    assert not room_access.verify_room_token(instance, "other", now=NOW)


def test_room_tokens_need_a_password_and_die_with_it() -> None:
    instance = _instance()
    with pytest.raises(ValueError):
        room_access.issue_room_token(instance)
    instance.set_room_password(PASSWORD)
    token, _ = room_access.issue_room_token(instance)
    instance.set_room_password("")
    assert not room_access.verify_room_token(instance, token)


def test_issuing_prunes_expired_and_caps_records() -> None:
    instance = _instance(PASSWORD)
    room_access.issue_room_token(instance, ttl_seconds=60, now=NOW)
    later = NOW + timedelta(minutes=5)
    for _ in range(room_access.MAX_ROOM_TOKENS + 3):
        room_access.issue_room_token(instance, now=later)
    records = instance.modules["room_access"]["room_tokens"]
    assert len(records) == room_access.MAX_ROOM_TOKENS
    assert all(datetime.fromisoformat(record["expires_at"]) > later for record in records)


def test_malformed_token_records_never_verify() -> None:
    instance = _instance(PASSWORD)
    digest = hashlib.sha256(b"tok").hexdigest()
    instance.modules["room_access"]["room_tokens"] = [
        {"hash": digest},
        {"hash": digest, "expires_at": "not-a-date"},
        {"hash": digest, "expires_at": "2999-01-01T00:00:00"},  # naive
        "garbage",
    ]
    assert not room_access.verify_room_token(instance, "tok")


@pytest.mark.parametrize("raw, expected", [
    (None, room_access.DEFAULT_ROOM_TOKEN_TTL_SECONDS),
    ("", room_access.DEFAULT_ROOM_TOKEN_TTL_SECONDS),
    ("7", 7 * 86400),
    ("0.5", 43200),
    ("9999", 365 * 86400),
    ("0", room_access.DEFAULT_ROOM_TOKEN_TTL_SECONDS),
    ("-3", room_access.DEFAULT_ROOM_TOKEN_TTL_SECONDS),
    ("nan", room_access.DEFAULT_ROOM_TOKEN_TTL_SECONDS),
    ("abc", room_access.DEFAULT_ROOM_TOKEN_TTL_SECONDS),
])
def test_room_token_ttl_is_configurable(raw, expected) -> None:
    environ = {} if raw is None else {room_password_svc.ROOM_TOKEN_TTL_ENV: raw}
    assert room_password_svc.room_token_ttl_seconds(environ) == expected


# ---- new password length -----------------------------------------------------


@pytest.mark.parametrize("password, ok", [("abcde", False), ("abcdef", True), ("", True)])
def test_new_passwords_need_six_characters(password, ok) -> None:
    instance = _instance("previous")
    if ok:
        instance.set_room_password(password)
        assert instance.has_room_password is bool(password)
    else:
        with pytest.raises(ValueError, match="至少 6 位"):
            instance.set_room_password(password)
        # A rejected change keeps the old password.
        assert room_access.verify_room_password(instance, "previous")


# ---- export / import -----------------------------------------------------------


def _assert_scrubbed(state: dict, *, closed: bool) -> None:
    rendered = json.dumps(state, ensure_ascii=False)
    for secret in (PASSWORD, "legacy-room-token", "bind-secret", "seat-digest", "pbkdf2_sha256"):
        assert secret not in rendered, secret
    slot = state["modules"]["room_access"]
    assert slot.get("room_tokens", []) == []
    assert slot.get("room_password_hash", "") == ""
    assert slot["bot_bind_token"] == ""
    assert slot["seat_credentials"] == {}
    assert slot["player_access_open"] is (not closed)


def _export(tmp_path, payload: dict) -> dict:
    save_path = tmp_path / "state.json"
    save_path.write_text(json.dumps(payload), encoding="utf-8")
    service = game_packages.GamePackageService(game_packages.GamePackageDependencies(
        parse_game_key=lambda game_key: tuple(game_key.split("|")),
        get_instance=lambda _key: SimpleNamespace(gm_uid="gm", world_name="w"),
        state_path_for=lambda _key: save_path,
        import_save_zip=AsyncMock(),
        resolve_scene_image_file=lambda _reference: None,
        resolve_map_background_file=lambda _reference: None,
        save_scene_image_upload=lambda _payload: {"ok": True},
        save_map_background_upload=lambda _payload: {"ok": True},
    ))
    result = service.export_game_package("web|room-pw|bot")
    assert result["ok"] is True
    with zipfile.ZipFile(BytesIO(result["payload"])) as archive:
        return json.loads(archive.read("state.json"))


def test_export_never_contains_access_credentials(tmp_path) -> None:
    instance = _instance(PASSWORD)
    instance.set_bot_bind_token("bind-secret")
    room_access.issue_room_token(instance, token="legacy-room-token")
    room_access.issue_seat_token(instance, "p1")
    state = _export(tmp_path, instance.to_dict())
    _assert_scrubbed(state, closed=True)


def test_export_of_an_unmigrated_v37_save_is_scrubbed_too(tmp_path) -> None:
    state = _export(tmp_path, _v37_payload())
    _assert_scrubbed(state, closed=True)
    assert state["modules"]["room_access"]["room_password"] == ""


def test_export_of_an_open_room_stays_open(tmp_path) -> None:
    instance = _instance()
    instance.set_bot_bind_token("bind-secret")
    state = _export(tmp_path, instance.to_dict())
    _assert_scrubbed(state, closed=False)


def test_import_drops_credentials_even_from_old_packages() -> None:
    # A package exported before this change still carries plaintext secrets.
    payload = rebind_imported_game_state_payload(
        _v37_payload(), game_key=("web", "imported", "bot"), run_id="run-2",
    )
    _assert_scrubbed(payload, closed=True)
    imported = GameInstance.from_dict(payload)
    assert imported.has_room_password is False
    assert imported.player_access_open is False


def test_import_scrubs_pre_slot_legacy_saves() -> None:
    legacy = {
        "instance_schema_version": 28,
        "game_key": ["web", "old", "bot"],
        "state": "created",
        "room_password": PASSWORD,
        "room_token": "legacy-room-token",
        "bot_bind_token": "bind-secret",
        "player_access_open": True,
    }
    payload = rebind_imported_game_state_payload(legacy, game_key=("web", "imported", "bot"), run_id="r")
    _assert_scrubbed(payload, closed=True)


def test_scrub_on_a_raw_legacy_payload_closes_access() -> None:
    legacy = {"room_password": PASSWORD, "room_token": "t", "bot_bind_token": "b", "player_access_open": True}
    assert room_access.scrub_access_credentials(legacy) is True
    assert legacy == {"room_password": "", "room_token": "", "bot_bind_token": "", "player_access_open": False}


# ---- HTTP: GM view and player join flow --------------------------------------


@pytest.mark.asyncio
async def test_gm_detail_never_contains_the_password_or_its_hash(play_env) -> None:
    game_key, instance = _make_game(play_env, "gm-view", bind_adventure=False, room_password=PASSWORD)
    stored_hash = instance.modules["room_access"]["room_password_hash"]
    app = _make_app(play_env)
    async with TestClient(TestServer(app)) as client:
        detail = await client.get(f"/api/games/{game_key}", headers=_owner())
        body = await detail.json()
    assert detail.status == 200
    assert body["has_room_password"] is True
    rendered = json.dumps(body, ensure_ascii=False)
    assert PASSWORD not in rendered and stored_hash not in rendered
    assert "room_password_hash" not in rendered and "room_tokens" not in rendered


@pytest.mark.asyncio
async def test_player_join_flow_with_password_change_and_expiry(play_env, monkeypatch) -> None:
    game_key, instance = _make_game(play_env, "join-flow", bind_adventure=False)
    instance.set_room_password(PASSWORD)
    app = _make_app(play_env)
    seat = _seat(instance)
    verify_url = f"/api/games/{game_key}/verify-room-password"
    detail_url = f"/api/games/{game_key}"

    async with TestClient(TestServer(app)) as client:
        lobby = await (await client.get(_player_url(detail_url), headers=seat)).json()
        assert lobby["has_room_password"] is True

        blocked = await client.get(_player_url(f"{detail_url}/adventure"), headers=seat)
        assert blocked.status == 403
        assert (await blocked.json())["needs_room_password"] is True

        wrong = await client.post(_player_url(verify_url), headers=seat, json={"password": "nope-nope"})
        assert wrong.status == 403
        assert "room_token" not in await wrong.json()

        right = await client.post(_player_url(verify_url), headers=seat, json={"password": PASSWORD})
        body = await right.json()
        assert right.status == 200 and right.headers["Cache-Control"] == "no-store"
        token = body["room_token"]
        assert token and datetime.fromisoformat(body["expires_at"]) > datetime.now(timezone.utc)
        assert token not in json.dumps(instance.to_dict())

        # A second player gets a separate token; the first keeps working.
        second = await (await client.post(
            _player_url(verify_url), headers=seat, json={"password": PASSWORD},
        )).json()
        assert second["room_token"] != token
        for held in (token, second["room_token"]):
            ok = await client.get(_player_url(f"{detail_url}/adventure", room_token=held), headers=seat)
            assert ok.status == 200, await ok.json()

        # Expired token -> the same "needs room password" answer as no token.
        far_future = datetime.now(timezone.utc) + timedelta(days=31)
        real_now = room_access._now
        monkeypatch.setattr(room_access, "_now", lambda now: now or far_future)
        expired = await client.get(_player_url(f"{detail_url}/adventure", room_token=token), headers=seat)
        assert expired.status == 403
        assert (await expired.json())["needs_room_password"] is True
        monkeypatch.setattr(room_access, "_now", real_now)

        # The GM changing the password revokes every room token.
        instance.set_room_password("brand-new-pass")
        revoked = await client.get(_player_url(f"{detail_url}/adventure", room_token=token), headers=seat)
        assert revoked.status == 403
        assert (await (await client.post(
            _player_url(verify_url), headers=seat, json={"password": PASSWORD},
        )).json())["ok"] is False

        # The owner never needs a room token.
        owner = await client.get(f"{detail_url}/adventure", headers=_owner())
        assert owner.status == 200


@pytest.mark.asyncio
async def test_gm_password_route_enforces_new_length_and_never_echoes(play_env) -> None:
    game_key, instance = _make_game(play_env, "gm-set", bind_adventure=False)

    @web.middleware
    async def as_gm(request, handler):
        request["user_id"] = GM_UID
        return await handler(request)

    app = web.Application(middlewares=[as_gm])
    app["api"] = play_env.api
    register_games(app)
    url = f"/api/games/{game_key}/room-password"
    async with TestClient(TestServer(app)) as client:
        short = await client.post(url, headers=_owner(), json={"password": "abcde"})
        ok = await client.post(url, headers=_owner(), json={"password": "abcdef"})
        short_body, ok_body = await short.json(), await ok.json()
    assert short.status == 400 and "至少 6 位" in short_body["error"]
    assert ok.status == 200 and ok_body == {"ok": True, "has_room_password": True}
    assert room_access.verify_room_password(instance, "abcdef")
