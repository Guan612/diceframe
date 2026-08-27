"""Authenticated Web/API boundary for authoritative ruleset gameplay intents."""

from __future__ import annotations

import logging
import random
from copy import deepcopy
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from src.compat.dnd2024_adventure_bindings import (
    apply_unreleased_adventure_binding_migration,
)
from src.webui.services.ruleset_builder import validate_draft_shape
from src.rulesets.contracts import (
    AuthoritativeIntentHooks,
    AutomaticIntentRuntime,
)
from src.webui.services import adventures

if TYPE_CHECKING:
    from src.webui.api import WebAPI


logger = logging.getLogger("trpg")


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "code": code, "error": message}


def _ruleset_timeline_text(batch: dict[str, Any], instance: Any) -> str:
    """Create one short public timeline entry for an authoritative ruleset batch."""
    intent_type = str(batch.get("intent_type") or "")
    event_types = {
        str(event.get("type") or "")
        for event in batch.get("events", [])
        if isinstance(event, dict)
    }
    chinese = not str(getattr(instance, "language", "") or "").lower().startswith("en")
    if "dnd2024.combat.started" in event_types:
        return "遭遇战开始：当前剧情已进入战斗。" if chinese else "Encounter started: the current story has entered combat."
    if "dnd2024.combat.ended" in event_types:
        return "遭遇战结束：可以回到当前冒险继续剧情。" if chinese else "Encounter ended: return to the current adventure."
    if intent_type == "tutorial.choose":
        return "剧情选择已记录，当前冒险已推进。" if chinese else "Story choice recorded; the current adventure advanced."
    if intent_type == "party_decision.submit":
        return "已收到队伍成员的行动意图，等待队伍决策。" if chinese else "A party intent was received; waiting for the group decision."
    if intent_type == "party_decision.resolve":
        return "队伍决定已记录，当前冒险已推进。" if chinese else "The party decision was recorded; the current adventure advanced."
    if intent_type.startswith("session_zero."):
        return "开团约定已更新。" if chinese else "Session agreement updated."
    if intent_type.startswith("campaign."):
        return "战役记录状态已更新。" if chinese else "Campaign record state updated."
    return "规则行动已由服务器结算。" if chinese else "Rules action resolved by the server."


def _append_ruleset_timeline_entry(instance: Any, batch: dict[str, Any]) -> None:
    intent_type = str(batch.get("intent_type") or "")
    chinese = not str(getattr(instance, "language", "") or "").lower().startswith("en")
    action_labels = {
        "tutorial.choose": ("推进当前剧情", "Advance the current story"),
        "party_decision.submit": ("提交队伍决策意图", "Submit a party decision intent"),
        "party_decision.resolve": ("结算队伍决定", "Resolve the party decision"),
        "tutorial.start": ("开始教学冒险", "Start the guided adventure"),
        "combat.start": ("进入剧情遭遇战", "Enter the story encounter"),
        "combat.end": ("结束遭遇战", "End the encounter"),
        "attack": ("进行攻击", "Make an attack"),
        "cast_spell": ("施放法术", "Cast a spell"),
        "move": ("移动位置", "Move position"),
        "end_turn": ("结束回合", "End the turn"),
    }
    event_types = {
        str(event.get("type") or "")
        for event in batch.get("events", [])
        if isinstance(event, dict)
    }
    if "dnd2024.combat.started" in event_types:
        action_text = ("进入剧情遭遇战", "Enter the story encounter")[0 if chinese else 1]
    elif "dnd2024.combat.ended" in event_types:
        action_text = ("结束剧情遭遇战", "Finish the story encounter")[0 if chinese else 1]
    else:
        action_text = action_labels.get(intent_type, ("推进高级规则剧情", "Advance the rules story"))[0 if chinese else 1]
    submitted_by = next(
        (
            str(event.get("submitted_by") or "")
            for event in batch.get("events", [])
            if isinstance(event, dict) and event.get("type") == "intent.submitted"
        ),
        "",
    )
    next_round = max(
        int(getattr(instance, "round_number", 0) or 0) + 1,
        max((int(item.get("round", 0) or 0) for item in instance.log), default=0) + 1,
    )
    instance.round_number = next_round
    instance.append_log_entry({
        "round": next_round,
        "actions": [{
            "user_id": submitted_by,
            "text": action_text,
            "source": "ruleset_authority",
            "intent_type": intent_type,
            "operation_id": str(batch.get("intent_id") or ""),
        }],
        "gm_response": _ruleset_timeline_text(batch, instance),
        "state_changes": [
            str(event.get("type") or "")
            for event in batch.get("events", [])
            if isinstance(event, dict) and str(event.get("type") or "") != "intent.submitted"
        ],
        "check_results": [],
        "swipes": [],
        "current_swipe": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def _is_public_story_milestone(batch: dict[str, Any]) -> bool:
    """Keep the shared story feed readable; turn-by-turn mechanics stay in combat."""
    event_types = {
        str(event.get("type") or "")
        for event in batch.get("events", [])
        if isinstance(event, dict)
    }
    return bool(event_types.intersection({
        "dnd2024.tutorial.started",
        "dnd2024.tutorial.choice_applied",
        "dnd2024.tutorial.completed",
        "dnd2024.party_decision.resolved",
        "dnd2024.combat.started",
        "dnd2024.combat.ended",
    }))


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


async def _ensure_compatible_adventure_binding(
    api: "WebAPI", runtime: Any, instance: Any,
) -> dict[str, Any] | None:
    binding = dict(getattr(instance, "adventure_binding", {}) or {})
    if not binding:
        return None
    try:
        expected = adventures.resolve_binding_for_runtime(
            api,
            str(binding.get("adventure_id") or ""),
            runtime,
            str(getattr(instance, "world_id", "") or ""),
            str(getattr(instance, "language", "") or ""),
        )
    except ValueError as exc:
        return _error("INCOMPATIBLE_ADVENTURE", str(exc))
    if binding == expected:
        return None
    if str(getattr(runtime, "runtime_id", "") or "") != "core:dnd2024":
        return _error(
            "INCOMPATIBLE_ADVENTURE",
            "bound adventure package is missing or has changed",
        )
    migrated = apply_unreleased_adventure_binding_migration(instance, expected)
    if migrated is None:
        return _error(
            "INCOMPATIBLE_ADVENTURE",
            "bound adventure package is missing or has changed",
        )
    if migrated:
        await api._reg.save(instance)
    return None



async def available_actions(
    api: "WebAPI", game_key: str, requester_id: str, requester_is_gm: bool = False,
) -> dict[str, Any]:
    instance, rule, runtime, effective_requester, error = _context(
        api, game_key, requester_id, requester_is_gm,
    )
    if error:
        return error
    async with instance._lock:
        binding_error = await _ensure_compatible_adventure_binding(
            api, runtime, instance,
        )
        if binding_error:
            return binding_error
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
        binding_error = await _ensure_compatible_adventure_binding(
            api, runtime, instance,
        )
        if binding_error:
            return binding_error
        before = {
            "ruleset_state": deepcopy(instance.ruleset_state),
            "event_ledger": deepcopy(instance.event_ledger),
            "players": deepcopy(instance.players),
            "combat_state": instance.combat_state,
            "combat_active": instance.combat_active,
            "initiative_order": deepcopy(instance.initiative_order),
            "initiative_current": instance.initiative_current,
            "last_activity": instance.last_activity,
            "log": deepcopy(instance.log),
            "round_number": instance.round_number,
        }
        try:
            rng = random.SystemRandom()
            resolved = runtime.resolve_intent(instance, intent, rng)
            if not resolved.get("ok"):
                return resolved
            batch = resolved.get("event_batch")
            if not isinstance(batch, dict):
                return _error("INVALID_EVENT_BATCH", "规则运行时没有返回有效事件批次")
            applied = runtime.apply_event_batch(instance, batch)
            if applied.get("applied") and _is_public_story_milestone(batch):
                _append_ruleset_timeline_entry(instance, batch)
            automatic_batches: list[dict[str, Any]] = []
            automatic_results: list[dict[str, Any]] = []
            if isinstance(runtime, AutomaticIntentRuntime):
                for _ in range(256):
                    automatic_intent = runtime.next_automatic_intent(instance)
                    if automatic_intent is None:
                        break
                    automatic = runtime.resolve_intent(instance, automatic_intent, rng)
                    if not automatic.get("ok"):
                        raise ValueError(
                            str(automatic.get("error") or "automatic combat intent was rejected")
                        )
                    automatic_batch = automatic.get("event_batch")
                    if not isinstance(automatic_batch, dict):
                        raise ValueError("automatic combat intent returned no event batch")
                    automatic_applied = runtime.apply_event_batch(instance, automatic_batch)
                    if not automatic_applied.get("applied"):
                        raise ValueError("automatic combat intent did not advance state")
                    automatic_batches.append(deepcopy(automatic_batch))
                    automatic_results.append(deepcopy(automatic_applied))
                    if _is_public_story_milestone(automatic_batch):
                        _append_ruleset_timeline_entry(instance, automatic_batch)
                else:
                    raise ValueError("automatic combat turn exceeded the safety limit")
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
            instance.log = before["log"]
            instance.round_number = before["round_number"]
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
            instance.log = before["log"]
            instance.round_number = before["round_number"]
            raise
        memory_store = getattr(api, "_mem", None)
        resolved_batches = [batch, *automatic_batches]
        if memory_store:
            for memory in [
                memory
                for resolved_batch in resolved_batches
                for memory in runtime.memory_deltas_from_event_batch(resolved_batch, instance)
            ]:
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
                "automatic_event_batches": automatic_batches,
                "automatic_results": automatic_results,
                "resolved_event_batches": resolved_batches,
            },
        )
