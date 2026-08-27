# -*- coding: utf-8 -*-
"""连接安全 API：Web Transport 状态、切换事务与自签证书管理。

切换成功后复用统一的 graceful restart（runtime_control），不建立第二套
重启机制。所有修改操作要求 X-TRPG-Confirm 确认头，并写入运行日志审计。
"""

from __future__ import annotations

import asyncio
import logging
import signal

from aiohttp import web

from src.webui.routes._common import _require_confirmed_request

logger = logging.getLogger("trpg")


def _get_service(request: web.Request):
    return request.app["security_transport"]


def _target_origin(request: web.Request, scheme: str) -> str:
    host = request.headers.get("Host") or request.host
    if not host:
        host = "127.0.0.1"
    return f"{scheme}://{host}"


async def _schedule_restart(request: web.Request) -> None:
    """响应 flush 后进入统一 graceful restart（与 /api/system/restart 相同路径）。"""
    await asyncio.sleep(0.5)
    signal.raise_signal(signal.SIGINT)


async def api_security_transport_get(request: web.Request) -> web.Response:
    return web.json_response(_get_service(request).get_status())


async def api_security_transport_prepare(request: web.Request) -> web.Response:
    denied = _require_confirmed_request(request)
    if denied is not None:
        return denied
    body = await request.json()
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "请求体必须是 JSON 对象"}, status=400)
    result = _get_service(request).prepare(str(body.get("mode") or ""))
    if result.get("ok"):
        logger.info("连接安全：已准备本地 HTTPS 候选证书（指纹 %s...）",
                    str(result.get("certificate", {}).get("fingerprint_sha256", ""))[:23])
    return web.json_response(result, status=200 if result.get("ok") else 400)


async def api_security_transport_activate(request: web.Request) -> web.Response:
    denied = _require_confirmed_request(request)
    if denied is not None:
        return denied
    body = await request.json()
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "请求体必须是 JSON 对象"}, status=400)
    result = _get_service(request).activate(str(body.get("token") or ""))
    if not result.get("ok"):
        return web.json_response(result, status=400)
    logger.info("连接安全：已启用 %s，等待重启生效", result.get("tls_mode"))
    result["target_origin"] = _target_origin(request, str(result.get("target_scheme") or "http"))
    control = request.app["runtime_control"]
    if not control["restart_requested"]:
        control["restart_requested"] = True
        control["restart_task"] = asyncio.create_task(_schedule_restart(request))
    return web.json_response(result)


async def api_security_transport_disable(request: web.Request) -> web.Response:
    denied = _require_confirmed_request(request)
    if denied is not None:
        return denied
    result = _get_service(request).disable()
    if not result.get("ok"):
        return web.json_response(result, status=400)
    logger.info("连接安全：已关闭 HTTPS，证书文件保留，等待重启生效")
    result["target_origin"] = _target_origin(request, "http")
    control = request.app["runtime_control"]
    if not control["restart_requested"]:
        control["restart_requested"] = True
        control["restart_task"] = asyncio.create_task(_schedule_restart(request))
    return web.json_response(result)


async def api_security_self_signed_regenerate(request: web.Request) -> web.Response:
    denied = _require_confirmed_request(request)
    if denied is not None:
        return denied
    result = _get_service(request).regenerate_self_signed()
    if not result.get("ok"):
        return web.json_response(result, status=400)
    certificate = result.get("certificate", {})
    logger.info(
        "连接安全：已重新生成本地证书（新指纹 %s...，旧指纹 %s...）",
        str(certificate.get("fingerprint_sha256", ""))[:23],
        str(result.get("previous_fingerprint", ""))[:23] or "无",
    )
    return web.json_response(result)


def register_security(app: web.Application) -> None:
    app.router.add_get("/api/system/security/transport", api_security_transport_get)
    app.router.add_post("/api/system/security/transport/prepare", api_security_transport_prepare)
    app.router.add_post("/api/system/security/transport/activate", api_security_transport_activate)
    app.router.add_post("/api/system/security/transport/disable", api_security_transport_disable)
    app.router.add_post(
        "/api/system/security/certificates/self-signed/regenerate",
        api_security_self_signed_regenerate,
    )
