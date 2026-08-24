"""Authenticated Web/API boundary for authoritative ruleset gameplay intents."""

from __future__ import annotations

import logging
import random
from copy import deepcopy
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from src.webui.services.ruleset_builder import validate_draft_shape
from src.rulesets.contracts import AuthoritativeIntentHooks, NarrativeAdventureRuntime

if TYPE_CHECKING:
    from src.webui.api import WebAPI


logger = logging.getLogger("trpg")


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "code": code, "error": message}


def _context(
    api: "WebAPI", game_key: str, requester_id: str, requester_is_gm: bool,
) -> tuple[Any, Any, Any, str, dict[str, Any] | None]:
    instance = api._reg.get(api._parse_key(game_key))
    if instance is None:
        return None, None, None, "", _error("GAME_NOT_FOUND", "游戏不存在")
    if not requester_id:
        return instance, None, None, "", _error("AUTH_REQUIRED", "需要有效的游戏会话")
    effective_requester = str(instance.gm_uid or "") if requester_is_gm else requester_id
    if not effective_requester:
        return instance, None, None, "", _error("GM_IDENTITY_MISSING", "本局缺少 GM 身份")
    if not requester_is_gm and requester_id not in instance.players:
        return instance, None, None, "", _error("PLAYER_NOT_IN_GAME", "当前玩家不在本局中")
    rule = api._load_rule_for_game(instance)
    if rule is None:
        return instance, None, None, effective_requester, _error(
            "RULE_NOT_FOUND", "本局规则不存在",
        )
    try:
        runtime = api._ruleset_registry.resolve(rule.template)
    except ValueError as exc:
        return instance, rule, None, effective_requester, _error(
            "RULESET_RUNTIME_UNAVAILABLE", str(exc),
        )
    if not runtime.capabilities.authoritative_intents:
        return instance, rule, runtime, effective_requester, _error(
            "RULESET_INTENTS_UNAVAILABLE", "该规则继续使用自由文本回合流程",
        )
    binding = dict(getattr(instance, "ruleset_runtime", {}) or {})
    if binding.get("id") != runtime.runtime_id:
        return instance, rule, runtime, effective_requester, _error(
            "RULESET_BINDING_MISMATCH", "存档未绑定当前权威规则运行时",
        )
    return instance, rule, runtime, effective_requester, None


def _response(
    api: "WebAPI", rule: Any, runtime: Any, instance: Any, requester_id: str,
    *, requester_is_gm: bool = False, result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    view = runtime.gameplay_view(instance, requester_id, requester_is_gm)
    actions = runtime.available_intents(instance, requester_id)
    payload: dict[str, Any] = {
        "ok": True,
        "game_key": "|".join(instance.game_key),
        "rule_id": str(rule.rule_id),
        "ruleset_runtime": api._ruleset_registry.describe(rule.template).to_dict(),
        "gameplay": view,
        "available_actions": actions,
    }
    if result is not None:
        payload["result"] = result
    return payload


async def available_actions(
    api: "WebAPI", game_key: str, requester_id: str, requester_is_gm: bool = False,
) -> dict[str, Any]:
    instance, rule, runtime, effective_requester, error = _context(
        api, game_key, requester_id, requester_is_gm,
    )
    if error:
        return error
    async with instance._lock:
        return _response(
            api, rule, runtime, instance, effective_requester,
            requester_is_gm=requester_is_gm,
        )


async def submit_intent(
    api: "WebAPI", game_key: str, requester_id: str, requester_is_gm: bool,
    body: Any,
) -> dict[str, Any]:
    instance, rule, runtime, effective_requester, error = _context(
        api, game_key, requester_id, requester_is_gm,
    )
    if error:
        return error
    try:
        intent = deepcopy(validate_draft_shape(body))
    except ValueError as exc:
        return _error("INVALID_INTENT_SHAPE", str(exc))
    intent["submitted_by"] = effective_requester
    if not isinstance(runtime, AuthoritativeIntentHooks):
        return _error(
            "RULESET_INTENT_HOOKS_UNAVAILABLE",
            "权威规则运行时缺少请求身份与投影边界",
        )
    intent = runtime.prepare_intent_submission(
        intent, effective_requester, requester_is_gm,
    )

    async with instance._lock:
        before = {
            "ruleset_state": deepcopy(instance.ruleset_state),
            "event_ledger": deepcopy(instance.event_ledger),
            "players": deepcopy(instance.players),
            "combat_state": instance.combat_state,
            "combat_active": instance.combat_active,
            "initiative_order": deepcopy(instance.initiative_order),
            "initiative_current": instance.initiative_current,
            "last_activity": instance.last_activity,
        }
        try:
            resolved = runtime.resolve_intent(instance, intent, random.SystemRandom())
            if not resolved.get("ok"):
                return resolved
            batch = resolved.get("event_batch")
            if not isinstance(batch, dict):
                return _error("INVALID_EVENT_BATCH", "规则运行时没有返回有效事件批次")
            applied = runtime.apply_event_batch(instance, batch)
            instance.last_activity = datetime.now(timezone.utc).isoformat()
            await api._reg.save(instance)
        except (ValueError, KeyError, TypeError) as exc:
            instance.ruleset_state = before["ruleset_state"]
            instance.event_ledger = before["event_ledger"]
            instance.players = before["players"]
            instance.combat_state = before["combat_state"]
            instance.combat_active = before["combat_active"]
            instance.initiative_order = before["initiative_order"]
            instance.initiative_current = before["initiative_current"]
            instance.last_activity = before["last_activity"]
            return _error("INTENT_REJECTED", str(exc))
        except Exception:
            instance.ruleset_state = before["ruleset_state"]
            instance.event_ledger = before["event_ledger"]
            instance.players = before["players"]
            instance.combat_state = before["combat_state"]
            instance.combat_active = before["combat_active"]
            instance.initiative_order = before["initiative_order"]
            instance.initiative_current = before["initiative_current"]
            instance.last_activity = before["last_activity"]
            raise
        memory_store = getattr(api, "_mem", None)
        if memory_store:
            for memory in runtime.memory_deltas_from_event_batch(batch, instance):
                try:
                    await memory_store.apply_delta(
                        str(instance.game_key), {"add": [memory]},
                        int(getattr(instance, "round_number", 0) or 0),
                    )
                except Exception:
                    # Long-term memory is a derived projection of the persisted
                    # EventBatch. A projection failure must not roll back or
                    # contradict the already-saved authoritative campaign state.
                    logger.exception("D&D chapter-summary memory projection failed")
        return _response(
            api, rule, runtime, instance, effective_requester,
            requester_is_gm=requester_is_gm,
            result={
                **applied,
                "replayed": bool(resolved.get("replayed", False)),
                "pending_decision": deepcopy(resolved.get("pending_decision")),
            },
        )


async def submit_adventure_narration(
    api: "WebAPI", game_key: str, requester_id: str, requester_is_gm: bool,
    body: Any,
) -> dict[str, Any]:
    instance, rule, runtime, effective_requester, error = _context(
        api, game_key, requester_id, requester_is_gm,
    )
    if error:
        return error
    if not runtime.capabilities.narrative_adventure or not isinstance(
        runtime, NarrativeAdventureRuntime,
    ):
        return _error(
            "NARRATIVE_ADVENTURE_UNAVAILABLE",
            "当前规则未提供自由冒险叙事入口",
        )
    try:
        parsed = validate_draft_shape(body)
    except ValueError as exc:
        return _error("INVALID_ADVENTURE_ACTION", str(exc))
    text = str(parsed.get("text") or "").strip()
    mode = str(parsed.get("mode") or "act").strip()
    operation_id = str(parsed.get("operation_id") or "").strip()
    if not text or len(text) > 1200:
        return _error("INVALID_ADVENTURE_ACTION", "自由行动须为 1 至 1200 字")
    if mode not in {"act", "say", "ask"}:
        return _error("INVALID_ADVENTURE_ACTION", "自由行动类型无效")
    if not operation_id or len(operation_id) > 160:
        return _error("INVALID_OPERATION_ID", "自由行动必须提供有效的 operation_id")
    client = getattr(api, "_llm_client", None)
    if client is None:
        english = str(getattr(instance, "language", "") or "").lower().startswith("en")
        return _error(
            "LLM_NOT_CONFIGURED",
            (
                "The story model is not configured yet. Open Settings and configure a model before continuing."
                if english
                else "尚未配置叙事模型，请先前往设置页配置模型后再继续。"
            ),
        )
    configuration_error = getattr(api, "_llm_configuration_error", None)
    if callable(configuration_error):
        details = configuration_error(str(getattr(instance, "language", "") or "zh-CN"))
        if details:
            result = _error(
                "LLM_NOT_CONFIGURED",
                str(details.get("error") or "尚未配置叙事模型，暂时无法生成冒险回应"),
            )
            result["missing"] = list(details.get("missing") or [])
            return result

    async with instance._lock:
        previous = next(
            (
                item for item in instance.log
                if any(
                    isinstance(action, dict)
                    and action.get("operation_id") == operation_id
                    for action in item.get("actions", [])
                )
            ),
            None,
        )
        if previous is not None:
            return {
                **_response(
                    api, rule, runtime, instance, effective_requester,
                    requester_is_gm=requester_is_gm,
                ),
                "duplicate": True,
                "narration": str(previous.get("gm_response") or ""),
            }
        prepared = runtime.prepare_adventure_narration(
            instance,
            effective_requester,
            {"text": text, "mode": mode},
            str(getattr(instance, "language", "") or ""),
        )
        if not prepared.get("ok"):
            return prepared
        try:
            response = await client.call(
                str(prepared.get("system_prompt") or ""),
                str(prepared.get("user_message") or ""),
                temperature=0.75,
                max_tokens=min(900, max(256, int(getattr(api, "text_gen_max_tokens", 700) or 700))),
            )
        except Exception as exc:
            logger.warning("D&D 2024 自由冒险叙事调用失败: %s", exc)
            english = str(getattr(instance, "language", "") or "").lower().startswith("en")
            return _error(
                "LLM_REQUEST_FAILED",
                (
                    "The story model could not respond. Check the model connection in Settings, then try again; your action was not recorded."
                    if english
                    else "故事模型暂时无法回应。请在设置页检查模型连接后重试；刚才的行动没有被记录。"
                ),
            )
        narration = str(response.narration or response.content or "").strip()
        if not narration:
            return _error("EMPTY_NARRATION", "叙事模型没有返回可显示的内容")
        next_round = max(
            int(getattr(instance, "round_number", 0) or 0) + 1,
            max((int(item.get("round", 0) or 0) for item in instance.log), default=0) + 1,
        )
        now = datetime.now(timezone.utc).isoformat()
        instance.round_number = next_round
        instance.append_log_entry({
            "round": next_round,
            "actions": [{
                "user_id": effective_requester,
                "text": text,
                "source": "ruleset_narrative",
                "mode": mode,
                "operation_id": operation_id,
                "timestamp": now,
            }],
            "gm_response": narration,
            "state_changes": [],
            "check_results": [],
            "swipes": [],
            "current_swipe": 0,
            "timestamp": now,
        })
        instance.last_activity = now
        instance.record_llm_usage(int(getattr(response, "total_tokens", 0) or 0))
        await api._reg.save(instance)
        return {
            **_response(
                api, rule, runtime, instance, effective_requester,
                requester_is_gm=requester_is_gm,
            ),
            "duplicate": False,
            "narration": narration,
        }
