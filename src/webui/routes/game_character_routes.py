"""Character and live-advancement routes."""

from __future__ import annotations

import logging

from aiohttp import web

from src.webui.api import can_modify_character
from src.webui.routes._common import (
    _get_api,
    _require_confirmed_request,
)

logger = logging.getLogger("trpg")
from src.webui.routes.game_route_common import (
    _broadcast_ruleset_change,
    _gm_only_inst,
    _should_rebind_player_session,
)


async def api_char_update(request: web.Request) -> web.Response:
    gk = request.match_info["game_key"]
    uid = request.match_info["user_id"]
    body = await request.json()
    api = _get_api(request)
    inst = api.get_game_instance(gk)
    if not inst:
        return web.json_response({"error": "游戏不存在"}, status=404)
    session_uid = request.get("user_id", "")
    if not can_modify_character(
        session_uid,
        uid,
        inst.gm_uid,
        owner=bool(request.get("owner_authenticated", False)),
    ):
        return web.json_response({"error": "无权修改他人角色卡"}, status=403)
    return web.json_response(await api.update_character(gk, uid, body))


async def api_ruleset_character_profile_update(request: web.Request) -> web.Response:
    """Patch non-mechanical profile data for a ruleset-authoritative character."""
    gk = request.match_info["game_key"]
    uid = request.match_info["user_id"]
    api = _get_api(request)
    inst = api.get_game_instance(gk)
    if not inst:
        return web.json_response({"ok": False, "error": "游戏不存在"}, status=404)
    session_uid = request.get("user_id", "")
    if not can_modify_character(
        session_uid,
        uid,
        inst.gm_uid,
        owner=bool(request.get("owner_authenticated", False)),
    ):
        return web.json_response(
            {"ok": False, "error": "无权修改他人角色卡"}, status=403
        )
    body = await request.json()
    result = await api.update_ruleset_character_profile(gk, uid, body)
    if result.get("ok"):
        return web.json_response(result)
    code = str(result.get("error_code") or "")
    status = 404 if code == "CHARACTER_NOT_FOUND" else 422
    return web.json_response(result, status=status)


async def api_ruleset_character_adopt_card(request: web.Request) -> web.Response:
    gk = request.match_info["game_key"]
    uid = request.match_info["user_id"]
    api = _get_api(request)
    inst = api.get_game_instance(gk)
    if not inst:
        return web.json_response({"ok": False, "error": "游戏不存在"}, status=404)
    session_uid = request.get("user_id", "")
    if not can_modify_character(
        session_uid,
        uid,
        inst.gm_uid,
        owner=bool(request.get("owner_authenticated", False)),
    ):
        return web.json_response(
            {"ok": False, "error": "无权修改他人角色卡"}, status=403
        )
    body = await request.json()
    result = await api.adopt_ruleset_character_card(
        gk, uid, str(body.get("card_id") or ""),
    )
    if result.get("ok"):
        return web.json_response(result)
    code = str(result.get("error_code") or "")
    status = 404 if code == "CHARACTER_NOT_FOUND" else 422
    return web.json_response(result, status=status)


async def _api_live_character_advancement(
    request: web.Request,
    action: str,
) -> web.Response:
    gk = request.match_info["game_key"]
    uid = request.match_info["user_id"]
    api = _get_api(request)
    inst = api.get_game_instance(gk)
    if not inst:
        return web.json_response({"ok": False, "error": "游戏不存在"}, status=404)
    session_uid = request.get("user_id", "")
    runtime_id = str((getattr(inst, "ruleset_runtime", {}) or {}).get("id") or "")
    can_advance = (
        session_uid == uid
        if runtime_id == "core:dnd2024"
        else can_modify_character(
            session_uid,
            uid,
            inst.gm_uid,
            owner=bool(request.get("owner_authenticated", False)),
        )
    )
    if not can_advance:
        return web.json_response(
            {"ok": False, "error": "无权修改他人角色卡"}, status=403
        )
    body = await request.json()
    try:
        result = (
            await api.apply_live_character_advancement(gk, uid, body)
            if action == "apply"
            else api.preview_live_character_advancement(gk, uid, body)
        )
    except ValueError as exc:
        result = {"ok": False, "code": "INVALID_ADVANCEMENT", "error": str(exc)}
    code = str(result.get("code") or "")
    status = (
        200
        if result.get("ok")
        else 404
        if code in {"GAME_NOT_FOUND", "CHARACTER_NOT_FOUND"}
        else 409
        if code == "STALE_CHARACTER_REVISION"
        else 422
    )
    return web.json_response(result, status=status)


async def api_live_character_advancement_preview(request: web.Request) -> web.Response:
    return await _api_live_character_advancement(request, "preview")


async def api_live_character_advancement_apply(request: web.Request) -> web.Response:
    return await _api_live_character_advancement(request, "apply")


async def api_live_advancement_control(request: web.Request) -> web.Response:
    game_key = request.match_info["game_key"]
    _, denied = _gm_only_inst(request, game_key)
    if denied is not None:
        return denied
    result = await _get_api(request).control_live_advancement(
        game_key, await request.json(),
    )
    await _broadcast_ruleset_change(request, game_key, result)
    code = str(result.get("code") or "")
    status = (
        200
        if result.get("ok")
        else 404
        if code
        in {
            "GAME_NOT_FOUND",
            "CHARACTER_NOT_FOUND",
        }
        else 422
    )
    return web.json_response(result, status=status)


async def api_live_character_rest(request: web.Request) -> web.Response:
    gk = request.match_info["game_key"]
    uid = request.match_info["user_id"]
    api = _get_api(request)
    inst = api.get_game_instance(gk)
    if not inst:
        return web.json_response({"ok": False, "error": "游戏不存在"}, status=404)
    if not can_modify_character(
        request.get("user_id", ""),
        uid,
        inst.gm_uid,
        owner=bool(request.get("owner_authenticated", False)),
    ):
        return web.json_response(
            {"ok": False, "error": "无权修改他人角色卡"}, status=403
        )
    payload = await request.json()
    result = await (
        api.ruleset_rest_resolve_live_party(gk, uid, payload)
        if not inst.solo_mode
        else api.ruleset_rest_resolve_live(gk, uid, payload)
    )
    await _broadcast_ruleset_change(request, gk, result)
    code = str(result.get("code") or "")
    status = (
        200
        if result.get("ok")
        else 404
        if code in {"GAME_NOT_FOUND", "CHARACTER_NOT_FOUND"}
        else 409
        if code == "STALE_CHARACTER_REVISION"
        else 422
    )
    return web.json_response(result, status=status)


async def api_char_delete(request: web.Request) -> web.Response:
    denied = _require_confirmed_request(request)
    if denied is not None:
        return denied
    gk = request.match_info["game_key"]
    uid = request.match_info["user_id"]
    api = _get_api(request)
    inst = api.get_game_instance(gk)
    if not inst:
        return web.json_response({"error": "游戏不存在"}, status=404)
    session_uid = request.get("user_id", "")
    if not can_modify_character(
        session_uid,
        uid,
        inst.gm_uid,
        owner=bool(request.get("owner_authenticated", False)),
    ):
        return web.json_response({"error": "无权删除他人角色"}, status=403)
    return web.json_response(await api.delete_character(gk, uid))


async def api_npc_portrait_update(request: web.Request) -> web.Response:
    gk = request.match_info["game_key"]
    npc_id = request.match_info["npc_id"]
    api = _get_api(request)
    inst = api.get_game_instance(gk)
    if not inst:
        return web.json_response({"error": "游戏不存在"}, status=404)
    if request.get("user_id", "") != inst.gm_uid:
        return web.json_response({"error": "仅 GM 可修改 NPC 头像"}, status=403)
    body = await request.json()
    return web.json_response(
        await api.update_npc_portrait(gk, npc_id, body.get("portrait"))
    )


async def api_player_create(request: web.Request) -> web.Response:
    gk = request.match_info["game_key"]
    body = await request.json()
    api = _get_api(request)
    inst = api.get_game_instance(gk)
    if not inst:
        return web.json_response({"ok": False, "error": "游戏不存在"}, status=404)
    session_uid = request.get("user_id", "")
    requested_uid = str(body.get("user_id") or "").strip()
    join_as_new = bool(body.get("join_as_new")) and not requested_uid
    force_uid = "" if join_as_new else session_uid
    result = await api.create_player(
        gk, body, force_uid=force_uid, assign_new_id=join_as_new
    )
    # 换设备恢复：普通玩家可按链接恢复身份；GM 点击玩家操作链接时不能改绑成玩家。
    if _should_rebind_player_session(
        session_uid, inst.gm_uid, requested_uid, result, join_as_new
    ):
        mgr = request.app.get("session_manager")
        token = request.get("session_token")
        if mgr and token:
            mgr.rebind(token, result.get("user_id", ""))
    return web.json_response(result)
