"""Application service for read-only player questions to the AI GM."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from src.webui.api import WebAPI

logger = logging.getLogger("trpg")


class KPQuestionResult(TypedDict):
    payload: dict[str, Any]
    status: int


def _result(payload: dict[str, Any], status: int = 200) -> KPQuestionResult:
    return {"payload": payload, "status": status}


async def ask(
    api: "WebAPI",
    game_key: str,
    actor_uid: str,
    question: str,
) -> KPQuestionResult:
    """Answer a table-talk question without persisting or mutating the game."""
    instance = api._reg.get(api._parse_key(game_key))
    if not instance:
        return _result({
            "ok": False,
            "code": "GAME_NOT_FOUND",
            "error": "游戏不存在，请刷新后重试",
        }, 404)
    if actor_uid not in instance.players:
        return _result({
            "ok": False,
            "code": "PLAYER_NOT_IN_GAME",
            "error": "请先认领本局角色，再向 KP 询问",
        }, 403)
    question = str(question or "").strip()
    if not question:
        return _result({
            "ok": False,
            "code": "EMPTY_QUESTION",
            "error": "请输入要询问 KP 的问题",
        }, 400)
    handler = getattr(api, "_handler", None)
    answerer = getattr(handler, "answer_kp_question", None)
    if not callable(answerer):
        return _result({
            "ok": False,
            "code": "LLM_NOT_CONFIGURED",
            "error": "KP 模型尚未配置或不可用",
        }, 503)

    try:
        generated = await answerer(instance, actor_uid, question)
    except Exception:
        logger.exception("KP 桌外询问生成失败: game=%s actor=%s", game_key, actor_uid)
        return _result({
            "ok": False,
            "code": "LLM_REQUEST_FAILED",
            "error": "KP 暂时无法回答，请稍后重试",
        }, 502)

    answer = str((generated or {}).get("answer") or "").strip()
    if not answer:
        return _result({
            "ok": False,
            "code": "EMPTY_ANSWER",
            "error": "KP 没有返回可显示的回答，请重试",
        }, 502)
    return _result({
        "ok": True,
        "kind": "kp_table_talk",
        "answer": answer,
        "advanced": False,
        "action_consumed": False,
        "round_number": instance.round_number,
        "provider_used": str((generated or {}).get("provider_used") or ""),
        "total_tokens": int((generated or {}).get("total_tokens", 0) or 0),
    })
