import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.webui.abuse_guard import (
    ABUSE_GUARD_KEY,
    AbuseGuard,
    SlidingWindowLimiter,
    _is_ai_request,
    abuse_guard_middleware,
)


async def _ok(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


def _app(guard: AbuseGuard) -> web.Application:
    app = web.Application(middlewares=[abuse_guard_middleware])
    app[ABUSE_GUARD_KEY] = guard
    app.router.add_post("/api/login", _ok)
    app.router.add_post("/api/games/room/action", _ok)
    app.router.add_get("/api/games/room", _ok)
    app.router.add_post("/api/rules/{rule_id}/builder/{action}", _ok)
    return app


@pytest.mark.asyncio
async def test_login_is_limited_before_reaching_handler():
    guard = AbuseGuard(
        login_per_ip_limit=2,
        login_per_ip_window=600,
        login_global_limit=100,
        ai_concurrency=10,
    )
    app = _app(guard)

    async with TestClient(TestServer(app)) as client:
        first = await client.post("/api/login")
        second = await client.post("/api/login")
        blocked = await client.post("/api/login")
        body = await blocked.json()

    assert first.status == 200
    assert second.status == 200
    assert blocked.status == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert blocked.headers["Cache-Control"] == "no-store"
    assert f"{body['retry_after']} 秒" in body["error"]
    assert "影响游戏" in body["error"]


@pytest.mark.asyncio
async def test_only_api_writes_use_the_general_request_limit():
    guard = AbuseGuard(
        write_per_ip_limit=2,
        write_global_limit=100,
        ai_concurrency=10,
    )
    app = _app(guard)

    async with TestClient(TestServer(app)) as client:
        assert (await client.post("/api/games/room/action")).status == 200
        assert (await client.post("/api/games/room/action")).status == 200
        assert (await client.post("/api/games/room/action")).status == 429
        assert (await client.get("/api/games/room")).status == 200


@pytest.mark.asyncio
async def test_stateless_builder_calls_have_their_own_budget():
    guard = AbuseGuard(
        write_per_ip_limit=2,
        write_global_limit=100,
        builder_per_ip_limit=3,
        builder_global_limit=100,
        ai_concurrency=10,
    )
    app = _app(guard)

    async with TestClient(TestServer(app)) as client:
        for action in ("choices", "validate", "derive"):
            assert (await client.post(f"/api/rules/dnd2024_srd/builder/{action}")).status == 200
        # 建卡计算不占写额度：之后普通写请求仍有完整额度。
        assert (await client.post("/api/games/room/action")).status == 200
        assert (await client.post("/api/games/room/action")).status == 200
        assert (await client.post("/api/games/room/action")).status == 429
        # 建卡自身仍然限流，不能无限消耗计算资源。
        assert (await client.post("/api/rules/dnd2024_srd/builder/finalize")).status == 429
        # 其它 rules 写接口不属于建卡计算，照常走写额度。
        assert (await client.post("/api/rules/dnd2024_srd/builder/other")).status == 429


@pytest.mark.asyncio
async def test_ai_requests_have_a_small_waiting_window_before_429():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow_handler(request: web.Request) -> web.Response:
        entered.set()
        await release.wait()
        return web.json_response({"ok": True})

    guard = AbuseGuard(
        write_per_ip_limit=100,
        write_global_limit=100,
        ai_concurrency=1,
        ai_wait_seconds=0.01,
    )
    app = web.Application(middlewares=[abuse_guard_middleware])
    app[ABUSE_GUARD_KEY] = guard
    app.router.add_post("/api/generate-text", slow_handler)

    async with TestClient(TestServer(app)) as client:
        active = asyncio.create_task(client.post("/api/generate-text"))
        await entered.wait()
        blocked = await client.post("/api/generate-text")
        release.set()
        completed = await active

    assert blocked.status == 429
    assert completed.status == 200


def test_limiter_evicts_old_identities_instead_of_growing_forever():
    now = 0.0
    limiter = SlidingWindowLimiter(max_buckets=3, clock=lambda: now)

    for index in range(10):
        now += 1
        assert limiter.check("write", f"ip-{index}", 10, 60).allowed

    assert limiter.bucket_count == 3


def test_story_recap_is_counted_as_an_ai_request():
    request = type("Request", (), {
        "path": "/api/games/room/story-recap",
        "method": "POST",
    })()

    assert _is_ai_request(request) is True


def test_kp_question_is_counted_as_an_ai_request():
    request = type("Request", (), {
        "path": "/api/games/room/kp-question",
        "method": "POST",
    })()

    assert _is_ai_request(request) is True


def test_server_speech_is_counted_as_an_ai_request():
    request = type("Request", (), {
        "path": "/api/games/room/speech",
        "method": "POST",
    })()

    assert _is_ai_request(request) is True


def test_storyboard_analysis_is_counted_as_an_ai_request():
    request = type("Request", (), {
        "path": "/api/games/room/generated-images/storyboard/analyze",
        "method": "POST",
    })()

    assert _is_ai_request(request) is True


def test_image_generation_stays_out_of_the_ai_slot_pool():
    """生图不占 AI 槽位：单次可长达 imagegen_timeout_seconds，
    挤进只有 3 个槽位的池子会把玩家行动一起饿死。"""
    for path in (
        "/api/games/room/generated-images/current-round",
        "/api/games/room/generated-images",
    ):
        request = type("Request", (), {"path": path, "method": "POST"})()

        assert _is_ai_request(request) is False


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _room_app(guard: AbuseGuard, outcomes: dict[str, int]) -> web.Application:
    """verify-room-password stub: the status per game key is set by the test."""

    async def verify(request: web.Request) -> web.Response:
        status = outcomes.get(request.match_info["game_key"], 403)
        return web.json_response({"ok": status == 200}, status=status)

    app = _app(guard)
    app.router.add_post("/api/games/{game_key}/verify-room-password", verify)
    return app


def _room_guard(clock: _Clock, **overrides) -> AbuseGuard:
    options = dict(
        write_per_ip_limit=1000, write_global_limit=1000, login_per_ip_limit=1000,
        room_password_free_failures=3, room_password_backoff_base=2,
        room_password_backoff_cap=30, room_password_per_ip_failure_limit=100,
        ai_concurrency=10, limiter=SlidingWindowLimiter(clock=clock),
    )
    options.update(overrides)
    return AbuseGuard(**options)


def _verify_url(game: str) -> str:
    from urllib.parse import quote

    return f"/api/games/{quote(game, safe='')}/verify-room-password"


@pytest.mark.asyncio
async def test_successful_room_password_entries_are_never_limited():
    clock = _Clock()
    app = _room_app(_room_guard(clock), {"web|a|web": 200})
    async with TestClient(TestServer(app)) as client:
        for _ in range(20):
            assert (await client.post(_verify_url("web|a|web"))).status == 200


@pytest.mark.asyncio
async def test_failed_room_password_entries_slow_down_instead_of_locking_out():
    clock = _Clock()
    app = _room_app(_room_guard(clock), {"web|a|web": 403})
    async with TestClient(TestServer(app)) as client:
        for _ in range(3):  # free failures
            assert (await client.post(_verify_url("web|a|web"))).status == 403
        # Fourth failure arrived; the next attempt must wait a short, growing delay.
        assert (await client.post(_verify_url("web|a|web"))).status == 403
        waited = await client.post(_verify_url("web|a|web"))
        assert waited.status == 429
        retry_after = int(waited.headers["Retry-After"])
        assert 1 <= retry_after <= 30
        # Not a lockout: once the delay passed, an attempt goes through again.
        clock.now += retry_after
        assert (await client.post(_verify_url("web|a|web"))).status == 403
        # Delays are capped, so nobody on the IP waits more than the cap.
        for _ in range(10):
            clock.now += 30
            assert (await client.post(_verify_url("web|a|web"))).status == 403
        capped = await client.post(_verify_url("web|a|web"))
        assert capped.status == 429 and int(capped.headers["Retry-After"]) <= 30


@pytest.mark.asyncio
async def test_a_correct_password_is_accepted_while_failures_back_off_elsewhere():
    clock = _Clock()
    app = _room_app(_room_guard(clock), {"web|a|web": 403, "web|b|web": 200})
    async with TestClient(TestServer(app)) as client:
        for _ in range(4):
            await client.post(_verify_url("web|a|web"))
        assert (await client.post(_verify_url("web|a|web"))).status == 429
        # Another table, and logins/writes, are unaffected.
        assert (await client.post(_verify_url("web|b|web"))).status == 200
        assert (await client.post("/api/login")).status == 200
        assert (await client.post("/api/games/room/action")).status == 200


@pytest.mark.asyncio
async def test_room_password_backoff_uses_the_canonical_game_key():
    clock = _Clock()
    # "solo" and "solo||" name the same game.
    app = _room_app(_room_guard(clock), {"solo": 403, "solo||": 403})
    async with TestClient(TestServer(app)) as client:
        for game in ("solo", "solo||", "solo", "solo||"):
            assert (await client.post(_verify_url(game))).status == 403
        assert (await client.post(_verify_url("solo"))).status == 429
        assert (await client.post(_verify_url("solo||"))).status == 429


@pytest.mark.asyncio
async def test_failed_room_passwords_have_a_hard_per_ip_total():
    clock = _Clock()
    guard = _room_guard(clock, room_password_free_failures=100, room_password_per_ip_failure_limit=3)
    app = _room_app(guard, {})
    async with TestClient(TestServer(app)) as client:
        for game in ("web|a|web", "web|b|web", "web|c|web"):
            assert (await client.post(_verify_url(game))).status == 403
        blocked = await client.post(_verify_url("web|d|web"))
        assert blocked.status == 429


def test_room_password_defaults_slow_down_quickly_and_cap_the_wait():
    from src.webui import abuse_guard

    assert abuse_guard.ROOM_PASSWORD_FREE_FAILURES <= abuse_guard.LOGIN_PER_IP_LIMIT
    assert abuse_guard.ROOM_PASSWORD_BACKOFF_CAP_SECONDS <= 60
    assert abuse_guard.ROOM_PASSWORD_PER_IP_FAILURE_LIMIT < abuse_guard.WRITE_PER_IP_LIMIT
