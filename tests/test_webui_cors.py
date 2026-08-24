from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.webui.cors import cors_middleware, parse_cors_origins
from src.webui.session import SessionManager, session_middleware


def test_parse_cors_origins_rejects_wildcards_and_paths():
    assert parse_cors_origins("https://play.example.com, https://other.example.com/") == {
        "https://play.example.com",
        "https://other.example.com",
    }
    assert parse_cors_origins("*, https://play.example.com") == {"https://play.example.com"}
    assert parse_cors_origins("https://play.example.com/path") == set()


async def _ok(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


@pytest.mark.asyncio
async def test_cors_preflight_and_credentials_cookie(tmp_path):
    app = web.Application(middlewares=[cors_middleware, session_middleware])
    app["cors_origins"] = frozenset({"https://play.example.com"})
    app["session_manager"] = SessionManager(tmp_path)
    app.router.add_route("*", "/api/config", _ok)

    async with TestClient(TestServer(app)) as client:
        preflight = await client.options(
            "/api/config",
            headers={
                "Origin": "https://play.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        assert preflight.status == 204
        assert preflight.headers["Access-Control-Allow-Origin"] == "https://play.example.com"
        assert preflight.headers["Access-Control-Allow-Credentials"] == "true"

        response = await client.get("/api/config", headers={"Origin": "https://play.example.com"})
        assert response.status == 200
        assert response.headers["Access-Control-Allow-Origin"] == "https://play.example.com"
        assert "SameSite=None" in response.headers["Set-Cookie"]
        assert "Secure" in response.headers["Set-Cookie"]
