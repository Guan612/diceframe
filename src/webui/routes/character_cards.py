"""角色卡路由 handler：列表 / 保存 / 更新 / 删除 / 导入。"""

from __future__ import annotations

from aiohttp import web

from src.webui.routes._common import _get_api, _require_confirmed_request


async def api_character_cards(request: web.Request) -> web.Response:
    return web.json_response(_get_api(request).list_character_cards())


async def api_game_character_cards(request: web.Request) -> web.Response:
    api = _get_api(request)
    if not api.game_detail(request.match_info["game_key"]):
        return web.json_response({"error": "游戏不存在"}, status=404)
    return web.json_response(api.list_character_cards())


async def api_character_card_save(request: web.Request) -> web.Response:
    body = await request.json()
    result = _get_api(request).save_character_card(body)
    return web.json_response(result, status=200 if result.get("ok") else 422)


async def api_character_card_update(request: web.Request) -> web.Response:
    body = await request.json()
    return web.json_response(_get_api(request).update_character_card(request.match_info["card_id"], body))


async def api_character_card_profile_update(request: web.Request) -> web.Response:
    body = await request.json()
    result = _get_api(request).update_ruleset_character_card_profile(
        request.match_info["card_id"], body,
    )
    if result.get("ok"):
        return web.json_response(result)
    code = str(result.get("error_code") or "")
    status = 404 if code == "CHARACTER_NOT_FOUND" else 422
    return web.json_response(result, status=status)


async def _api_character_card_advancement(request: web.Request, action: str) -> web.Response:
    from src.webui.services import ruleset_advancement

    body = await request.json()
    method = getattr(ruleset_advancement, f"{action}_card")
    try:
        result = method(_get_api(request), request.match_info["card_id"], body)
    except ValueError as exc:
        result = {"ok": False, "code": "INVALID_ADVANCEMENT", "error": str(exc)}
    if result.get("ok"):
        status = 200
    elif result.get("code") == "CHARACTER_NOT_FOUND":
        status = 404
    elif result.get("code") == "STALE_CHARACTER_REVISION":
        status = 409
    else:
        status = 422
    return web.json_response(result, status=status)


async def api_character_card_advancement_preview(request: web.Request) -> web.Response:
    return await _api_character_card_advancement(request, "preview")


async def api_character_card_advancement_apply(request: web.Request) -> web.Response:
    return await _api_character_card_advancement(request, "apply")


async def api_character_card_delete(request: web.Request) -> web.Response:
    denied = _require_confirmed_request(request)
    if denied is not None:
        return denied
    return web.json_response(_get_api(request).delete_character_card(request.match_info["card_id"]))


async def api_character_card_import(request: web.Request) -> web.Response:
    body = await request.json()
    result = await _get_api(request).import_character_card(
        file_data=body.get("file_data", ""),
        file_name=body.get("file_name", "card.json"),
        target=str(body.get("target") or "character_card"),
        world_id=str(body.get("world_id") or ""),
    )
    return web.json_response(result, status=200 if result.get("ok") else 422)


async def api_character_card_export(request: web.Request) -> web.Response:
    body = await request.json()
    result = _get_api(request).export_character_cards(body.get("card_ids") or [])
    if not result.get("ok"):
        return web.json_response(result, status=400)
    filename = str(result.get("filename") or "characters.json")
    return web.Response(
        body=result["payload"],
        content_type=result.get("content_type", "application/json"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def register_character_cards(app: web.Application) -> None:
    app.router.add_get("/api/character-cards", api_character_cards)
    app.router.add_get("/api/games/{game_key}/character-cards", api_game_character_cards)
    app.router.add_post("/api/character-cards", api_character_card_save)
    app.router.add_route("PUT", "/api/character-cards/{card_id}", api_character_card_update)
    app.router.add_patch(
        "/api/character-cards/{card_id}/profile", api_character_card_profile_update,
    )
    app.router.add_post(
        "/api/character-cards/{card_id}/advancement/preview",
        api_character_card_advancement_preview,
    )
    app.router.add_post(
        "/api/character-cards/{card_id}/advancement/apply",
        api_character_card_advancement_apply,
    )
    app.router.add_route("DELETE", "/api/character-cards/{card_id}", api_character_card_delete)
    app.router.add_post("/api/character-cards/import", api_character_card_import)
    app.router.add_post("/api/character-cards/export", api_character_card_export)
