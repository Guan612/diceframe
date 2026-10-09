"""Small in-memory guard against request floods and expensive AI concurrency."""

from __future__ import annotations

import asyncio
import math
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Awaitable, Callable

from aiohttp import web

from src.webui.services._common import canonical_game_key


LOGIN_PER_IP_LIMIT = 10
LOGIN_PER_IP_WINDOW_SECONDS = 10 * 60
LOGIN_GLOBAL_LIMIT = 60
LOGIN_GLOBAL_WINDOW_SECONDS = 60
WRITE_PER_IP_LIMIT = 60
WRITE_PER_IP_WINDOW_SECONDS = 60
WRITE_GLOBAL_LIMIT = 600
WRITE_GLOBAL_WINDOW_SECONDS = 60
# 房间密码猜测：只计「失败」的尝试（输对的玩家从不被限）。同一 IP+同一局
# 前几次失败不受影响，之后每次尝试之间需等待指数增长、有上限的间隔——是
# 减速而不是封锁，共用出口 IP（隧道/代理/NAT）后面的正常玩家最多等一个上限
# 间隔，不会被同 IP 的捣乱者把整局锁死。同一 IP 的失败总数另有硬上限，
# 防止对多局撒网。与 owner 登录、通用写入分桶，互不挤占。
# 身份按 request.remote（直连对端地址）计；不信任 X-Forwarded-For，因为本项目
# 没有「可信反向代理」配置——反代后面所有玩家共用代理 IP，正是减速设计要兜住的情况。
ROOM_PASSWORD_FREE_FAILURES = 5
ROOM_PASSWORD_BACKOFF_BASE_SECONDS = 2
ROOM_PASSWORD_BACKOFF_CAP_SECONDS = 60
ROOM_PASSWORD_FAILURE_WINDOW_SECONDS = 10 * 60
ROOM_PASSWORD_PER_IP_FAILURE_LIMIT = 50
# 建卡器的 choices/validate/derive/finalize 是无状态计算（POST 只为携带草稿），
# 单独计额：引导建卡每改一步都会请求，不能挤占同 IP 其它玩家的写额度。
BUILDER_PER_IP_LIMIT = 300
BUILDER_PER_IP_WINDOW_SECONDS = 60
BUILDER_GLOBAL_LIMIT = 3000
BUILDER_GLOBAL_WINDOW_SECONDS = 60
AI_CONCURRENCY_LIMIT = 3
AI_SLOT_WAIT_SECONDS = 2.0
MAX_TRACKED_BUCKETS = 2000

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# 凭据兑换端点与登录共用限流桶：两者都能用于暴力猜测 owner 访问权。
_LOGIN_PATHS = frozenset({"/api/login", "/api/pairing/claim"})
_ROOM_PASSWORD_PATH = re.compile(r"^/api/games/([^/]+)/verify-room-password/?$")
_BUILDER_PATH = re.compile(r"^/api/rules/[^/]+/builder/(?:choices|validate|derive|finalize)$")
_AI_EXACT_PATHS = frozenset({
    "/api/generate-world",
    "/api/generate-rule",
    "/api/generate-character",
    "/api/generate-text",
    "/api/image-prompts/optimize",
    "/api/test-connection",
    "/api/test-embedding",
    "/api/assistant/chat",
    "/api/tts/test",
})
_AI_GAME_SUFFIXES = (
    "/action",
    "/kp-question",
    "/advance",
    "/luck",
    "/stream-action",
    "/story-recap",
    "/reset",
    "/restart",
    "/switch-world",
    "/speech",
    # 分镜分析走的是主文本模型，和上面几条一样要占 AI 槽位。
    # 生图接口（/current-round、POST .../generated-images）故意不进这里：
    # 单次可长达 imagegen_timeout_seconds，占满槽位会把玩家行动一起饿死。
    "/storyboard/analyze",
)


@dataclass(frozen=True)
class LimitDecision:
    allowed: bool
    retry_after: int = 0


class SlidingWindowLimiter:
    """Bounded sliding-window counters; restarting the app resets all counters."""

    def __init__(
        self,
        *,
        max_buckets: int = MAX_TRACKED_BUCKETS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_buckets = max(1, max_buckets)
        self._clock = clock
        self._buckets: dict[tuple[str, str], deque[float]] = {}
        self._last_seen: dict[tuple[str, str], float] = {}
        self._last_cleanup = 0.0

    def check(self, scope: str, identity: str, limit: int, window_seconds: int) -> LimitDecision:
        now = self._clock()
        self._cleanup(now, max(window_seconds, LOGIN_PER_IP_WINDOW_SECONDS))
        key = (scope, identity)
        bucket = self._buckets.setdefault(key, deque())
        cutoff = now - window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        self._last_seen[key] = now
        if len(bucket) >= limit:
            retry_after = max(1, math.ceil(window_seconds - (now - bucket[0])))
            return LimitDecision(False, retry_after)
        bucket.append(now)
        self._evict_if_needed(key)
        return LimitDecision(True)

    def now(self) -> float:
        return self._clock()

    def recent(self, scope: str, identity: str, window_seconds: int) -> list[float]:
        """Timestamps recorded in the window, without recording a new one."""
        key = (scope, identity)
        bucket = self._buckets.get(key)
        if not bucket:
            return []
        cutoff = self._clock() - window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        return list(bucket)

    def record(self, scope: str, identity: str, window_seconds: int) -> None:
        """Record one event (e.g. a failed attempt) without checking a limit."""
        now = self._clock()
        self._cleanup(now, max(window_seconds, LOGIN_PER_IP_WINDOW_SECONDS))
        key = (scope, identity)
        self._buckets.setdefault(key, deque()).append(now)
        self._last_seen[key] = now
        self._evict_if_needed(key)

    @property
    def bucket_count(self) -> int:
        return len(self._buckets)

    def _cleanup(self, now: float, retention_seconds: int) -> None:
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        stale_before = now - retention_seconds
        for key, last_seen in list(self._last_seen.items()):
            if last_seen <= stale_before:
                self._last_seen.pop(key, None)
                self._buckets.pop(key, None)

    def _evict_if_needed(self, current_key: tuple[str, str]) -> None:
        while len(self._buckets) > self.max_buckets:
            candidates = (
                (key, seen)
                for key, seen in self._last_seen.items()
                if key != current_key
            )
            victim = min(candidates, key=lambda item: item[1], default=None)
            if victim is None:
                break
            self._last_seen.pop(victim[0], None)
            self._buckets.pop(victim[0], None)


class AbuseGuard:
    def __init__(
        self,
        *,
        login_per_ip_limit: int = LOGIN_PER_IP_LIMIT,
        login_per_ip_window: int = LOGIN_PER_IP_WINDOW_SECONDS,
        login_global_limit: int = LOGIN_GLOBAL_LIMIT,
        login_global_window: int = LOGIN_GLOBAL_WINDOW_SECONDS,
        write_per_ip_limit: int = WRITE_PER_IP_LIMIT,
        write_per_ip_window: int = WRITE_PER_IP_WINDOW_SECONDS,
        write_global_limit: int = WRITE_GLOBAL_LIMIT,
        write_global_window: int = WRITE_GLOBAL_WINDOW_SECONDS,
        room_password_free_failures: int = ROOM_PASSWORD_FREE_FAILURES,
        room_password_backoff_base: float = ROOM_PASSWORD_BACKOFF_BASE_SECONDS,
        room_password_backoff_cap: float = ROOM_PASSWORD_BACKOFF_CAP_SECONDS,
        room_password_failure_window: int = ROOM_PASSWORD_FAILURE_WINDOW_SECONDS,
        room_password_per_ip_failure_limit: int = ROOM_PASSWORD_PER_IP_FAILURE_LIMIT,
        builder_per_ip_limit: int = BUILDER_PER_IP_LIMIT,
        builder_per_ip_window: int = BUILDER_PER_IP_WINDOW_SECONDS,
        builder_global_limit: int = BUILDER_GLOBAL_LIMIT,
        builder_global_window: int = BUILDER_GLOBAL_WINDOW_SECONDS,
        ai_concurrency: int = AI_CONCURRENCY_LIMIT,
        ai_wait_seconds: float = AI_SLOT_WAIT_SECONDS,
        limiter: SlidingWindowLimiter | None = None,
    ) -> None:
        self.login_per_ip_limit = login_per_ip_limit
        self.login_per_ip_window = login_per_ip_window
        self.login_global_limit = login_global_limit
        self.login_global_window = login_global_window
        self.write_per_ip_limit = write_per_ip_limit
        self.write_per_ip_window = write_per_ip_window
        self.write_global_limit = write_global_limit
        self.write_global_window = write_global_window
        self.room_password_free_failures = max(0, room_password_free_failures)
        self.room_password_backoff_base = room_password_backoff_base
        self.room_password_backoff_cap = room_password_backoff_cap
        self.room_password_failure_window = room_password_failure_window
        self.room_password_per_ip_failure_limit = room_password_per_ip_failure_limit
        self.builder_per_ip_limit = builder_per_ip_limit
        self.builder_per_ip_window = builder_per_ip_window
        self.builder_global_limit = builder_global_limit
        self.builder_global_window = builder_global_window
        self.ai_wait_seconds = ai_wait_seconds
        self._limiter = limiter or SlidingWindowLimiter()
        self._ai_slots = asyncio.Semaphore(max(1, ai_concurrency))

    async def handle(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        ip = (request.remote or "unknown")[:128]

        if request.method == "POST" and request.path in _LOGIN_PATHS:
            denied = self._check_pair(
                "login-ip",
                ip,
                self.login_per_ip_limit,
                self.login_per_ip_window,
                "login-global",
                self.login_global_limit,
                self.login_global_window,
            )
            if denied:
                return _rate_limited_response(denied)
        elif request.method == "POST" and (room_match := _ROOM_PASSWORD_PATH.match(request.path)):
            game = canonical_game_key(request.match_info.get("game_key") or room_match.group(1))[:256]
            denied = self._room_password_wait(ip, game)
            if denied:
                return _rate_limited_response(denied)
            response = await handler(request)
            if response.status == 403:  # wrong password: only failures count
                self._record_room_password_failure(ip, game)
            return response
        elif request.method == "POST" and _BUILDER_PATH.match(request.path):
            denied = self._check_pair(
                "builder-ip",
                ip,
                self.builder_per_ip_limit,
                self.builder_per_ip_window,
                "builder-global",
                self.builder_global_limit,
                self.builder_global_window,
            )
            if denied:
                return _rate_limited_response(denied)
        elif request.method in _WRITE_METHODS and request.path.startswith("/api/"):
            denied = self._check_pair(
                "write-ip",
                ip,
                self.write_per_ip_limit,
                self.write_per_ip_window,
                "write-global",
                self.write_global_limit,
                self.write_global_window,
            )
            if denied:
                return _rate_limited_response(denied)

        if not _is_ai_request(request):
            return await handler(request)

        try:
            await asyncio.wait_for(self._ai_slots.acquire(), timeout=self.ai_wait_seconds)
        except TimeoutError:
            return _rate_limited_response(max(1, math.ceil(self.ai_wait_seconds)))
        try:
            return await handler(request)
        finally:
            self._ai_slots.release()

    def _room_password_wait(self, ip: str, game: str) -> int:
        """Seconds this IP must still wait before another room password attempt."""
        window = self.room_password_failure_window
        now = self._limiter.now()
        per_ip = self._limiter.recent("room-password-fail-ip", ip, window)
        if len(per_ip) >= self.room_password_per_ip_failure_limit:
            return max(1, math.ceil(window - (now - per_ip[0])))
        failures = self._limiter.recent("room-password-fail-ip-game", f"{ip}|{game}", window)
        # The first ``free`` failures cost nothing; each later one doubles the
        # spacing required before the next attempt, up to the cap.
        excess = len(failures) - self.room_password_free_failures - 1
        if excess < 0:
            return 0
        delay = min(self.room_password_backoff_cap, self.room_password_backoff_base * (2 ** min(excess, 30)))
        remaining = failures[-1] + delay - now
        return max(1, math.ceil(remaining)) if remaining > 0 else 0

    def _record_room_password_failure(self, ip: str, game: str) -> None:
        window = self.room_password_failure_window
        self._limiter.record("room-password-fail-ip", ip, window)
        self._limiter.record("room-password-fail-ip-game", f"{ip}|{game}", window)

    def _check_pair(
        self,
        ip_scope: str,
        ip: str,
        ip_limit: int,
        ip_window: int,
        global_scope: str,
        global_limit: int,
        global_window: int,
    ) -> int:
        per_ip = self._limiter.check(ip_scope, ip, ip_limit, ip_window)
        if not per_ip.allowed:
            return per_ip.retry_after
        global_decision = self._limiter.check(global_scope, "*", global_limit, global_window)
        return 0 if global_decision.allowed else global_decision.retry_after


def _is_ai_request(request: web.Request) -> bool:
    if request.path in _AI_EXACT_PATHS:
        return request.method == "POST"
    if not request.path.startswith("/api/games/"):
        return False
    if request.method == "PUT" and "/swipe/" in request.path:
        return True
    return request.method == "POST" and request.path.endswith(_AI_GAME_SUFFIXES)


def _rate_limited_response(retry_after: int) -> web.Response:
    retry_after = max(1, retry_after)
    return web.json_response(
        {
            "ok": False,
            "error": (
                "操作太频繁，为避免连续请求影响游戏，系统暂时拦截了本次操作。"
                f"请等待约 {retry_after} 秒后再试。"
            ),
            "retry_after": retry_after,
        },
        status=429,
        headers={
            "Retry-After": str(retry_after),
            "Cache-Control": "no-store",
        },
    )


ABUSE_GUARD_KEY = web.AppKey("abuse_guard", AbuseGuard)


@web.middleware
async def abuse_guard_middleware(request: web.Request, handler):
    guard = request.app.get(ABUSE_GUARD_KEY)
    if guard is None:
        return await handler(request)
    return await guard.handle(request, handler)
