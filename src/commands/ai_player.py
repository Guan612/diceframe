"""AI-hosted player seats declare ordinary actions in exploration rounds.

An ``ai`` seat is a *player*, not a GM: the server produces that character's
action, and the action then travels the exact path a human declaration travels.
This module owns only the part that is specific to the AI controller:

* *when* an action may be produced -- only after the human gate is satisfied
  (``GameInstance.human_actions_ready``), never while a human is still pending,
  and always before the round advances;
* *what the model may see* -- the existing player-safe context builder, so the
  prompt contains the seat's own character sheet, the public story and the
  actions already declared this round, and never GM truth;
* *how many calls* -- one plain-text call per AI seat, sequentially in sorted
  uid order, so a later seat sees the earlier AI declarations of the same pass;
* *what is written* -- plain prose through ``GameInstance.add_action``.

Everything else (checks, DCs, world legality, economy, narration) stays in the
existing pipeline: the model never returns a rules result, so there is nothing
here that could grant an AI seat authority a human seat does not have.

Boundaries:

- ``src/engine/player_control.py`` stays deterministic; no LLM code lives there.
- No second check planner and no direct ``action_queue`` append: the action goes
  through the canonical submission seam and the existing Check Planner handles it.
- Failure is non-blocking: a provider error, timeout or unusable output is logged
  with the literal ``AI_ACTION_SKIPPED`` marker, recorded in the returned
  per-seat results, and the pass (and the round) continues.
- A control handover while a call is in flight discards the result: the seat must
  still be ``ai``, in the same run and round, with the same control revision and
  at the same phase, or nothing at all is written.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.engine.game_instance import GameInstance, GameState
from src.engine.language import DEFAULT_LANGUAGE, localized_text
from src.engine.player_control import ai_controlled_players, get_control
from src.llm.context_builder import build_player_safe_context
from src.llm.parser import sanitize_narration

logger = logging.getLogger("trpg")

# 行动记录上的来源标记；与 ``control`` 一样只是元数据，绝不是规则权威。
AI_ACTION_SOURCE = "ai_player"

# 失败隔离的可观察标记（日志与返回结果共用同一个字面量）。
SKIP_MARKER = "AI_ACTION_SKIPPED"
# 竞争失守（run/round/控制权在飞行中变化）时丢弃结果的标记。
DISCARD_MARKER = "AI_ACTION_DISCARDED"

MAX_AI_ACTION_CHARS = 1000
DEFAULT_MAX_TOKENS = 768
DEFAULT_TEMPERATURE = 0.8

_ACTION_PROMPT = {
    "zh-CN": (
        "你是本局的一名玩家，扮演角色「{name}」（席位 {uid}）。你只代表这一个角色，"
        "不做 GM 叙述，也不替任何人决定结果。\n\n"
        "硬性约束：\n"
        "1. 只输出这个角色本轮想做的一件事，用 1–3 句自然的第一人称行动描述"
        "（例如「我去检查教堂后门，同时提醒阿岚注意右侧的窗户。」）。\n"
        "2. 只输出行动文本本身：不要 JSON、标签、工具调用、解释、标题或前后缀。\n"
        "3. 不要输出任何规则结果：不写 DC、难度、加值、伤害、骰点或成功/失败判断——"
        "这些由服务端结算。\n"
        "4. 只使用上下文里这个角色理应知道的信息：自己的角色卡、公开剧情、以及本轮"
        "已经公开的行动；不得引用秘密、其他角色的私有信息或尚未发生的情节。\n"
        "5. 不替其他角色行动、说话或决定结果，只声明自己的尝试。\n"
        "6. 行动文本使用简体中文。"
    ),
    "en": (
        "You are one player at this table, playing {name} (seat {uid}). You speak only "
        "for this character: you are not the GM and you never decide anything for "
        "anyone else.\n\n"
        "Hard constraints:\n"
        "1. Output exactly one intended action for this character, in 1-3 natural "
        "first-person sentences (for example: \"I check the church's back door and "
        "warn A-Lan about the window on the right.\").\n"
        "2. Output the action text only: no JSON, tags, tool calls, explanation, "
        "headings or prefixes.\n"
        "3. Never state a rules result: no DC, difficulty, modifier, damage, dice "
        "value or success/failure verdict. The server settles all of that.\n"
        "4. Use only what this character can legitimately know from the context: its "
        "own character sheet, the public story so far, and the actions already "
        "declared this round. Never cite secrets, another character's private "
        "information, or events that have not happened yet.\n"
        "5. Do not act, speak or decide for other characters; declare only your own "
        "attempt.\n"
        "6. Write the action text in English."
    ),
    "ja": (
        "あなたはこの卓のプレイヤーの一人で、キャラクター「{name}」（席 {uid}）を演じます。"
        "このキャラクターの立場だけで発言し、GM の語りはせず、他人の結果も決めません。\n\n"
        "厳守事項：\n"
        "1. このキャラクターがこのラウンドに行うことを一つだけ、自然な一人称の 1〜3 文で"
        "出力すること。\n"
        "2. 出力は行動テキストのみ。JSON、タグ、ツール呼び出し、説明、見出し、接頭辞は"
        "付けないこと。\n"
        "3. ルール結果は一切書かないこと：DC、難易度、修正値、ダメージ、出目、成功/失敗の"
        "判定はサーバーが確定します。\n"
        "4. 文脈からこのキャラクターが正当に知り得る情報だけを使うこと：自分のキャラクター"
        "シート、公開された物語、このラウンドで既に公開された行動。秘密、他キャラクターの"
        "非公開情報、まだ起きていない出来事を引用しないこと。\n"
        "5. 他キャラクターの行動・発言・結果を代行せず、自分の試みだけを宣言すること。\n"
        "6. 行動テキストは日本語で書くこと。"
    ),
    "de": (
        "Du bist ein Spieler an diesem Tisch und spielst {name} (Sitz {uid}). Du "
        "sprichst nur für diese Figur: Du bist nicht der GM und entscheidest nichts "
        "für andere.\n\n"
        "Feste Einschränkungen:\n"
        "1. Gib genau eine beabsichtigte Aktion dieser Figur in 1-3 natürlichen Sätzen "
        "in der Ich-Form aus.\n"
        "2. Gib nur den Aktionstext aus: kein JSON, keine Tags, keine Tool-Aufrufe, "
        "keine Erklärung, keine Überschriften oder Präfixe.\n"
        "3. Nenne niemals ein Regelergebnis: kein DC, keine Schwierigkeit, keinen "
        "Modifikator, keinen Schaden, keinen Würfelwert und kein Erfolgs-/Misserfolgs"
        "urteil. Das entscheidet der Server.\n"
        "4. Verwende nur, was diese Figur aus dem Kontext rechtmäßig wissen kann: ihren "
        "eigenen Charakterbogen, die öffentliche Handlung und die in dieser Runde "
        "bereits erklärten Aktionen. Zitiere keine Geheimnisse, keine privaten "
        "Informationen anderer Figuren und keine noch nicht eingetretenen Ereignisse.\n"
        "5. Handle, sprich und entscheide nicht für andere Figuren; erkläre nur den "
        "eigenen Versuch.\n"
        "6. Schreibe den Aktionstext auf Deutsch."
    ),
}

_DECLARED_ACTIONS_HEADING = {
    "zh-CN": "【本轮已经公开的行动】",
    "en": "## Actions already declared this round",
    "ja": "## このラウンドで既に公開された行動",
    "de": "## In dieser Runde bereits erklärte Aktionen",
}
_NO_DECLARED_ACTIONS = {
    "zh-CN": "（本轮还没有其他公开行动）",
    "en": "(no other public action has been declared this round)",
    "ja": "（このラウンドで他に公開された行動はまだありません）",
    "de": "(in dieser Runde wurde noch keine andere öffentliche Aktion erklärt)",
}
_OWN_CHARACTER_HEADING = {
    "zh-CN": "【你的角色】",
    "en": "## Your character",
    "ja": "## あなたのキャラクター",
    "de": "## Deine Figur",
}
_OWN_CHARACTER_REQUEST = {
    "zh-CN": "{name}（{uid}）\n请以 {name} 的身份，给出这一轮的行动。",
    "en": "{name} ({uid})\nDeclare {name}'s action for this round.",
    "ja": "{name}（{uid}）\n{name} として、このラウンドの行動を宣言してください。",
    "de": "{name} ({uid})\nErkläre die Aktion von {name} für diese Runde.",
}


def build_ai_player_prompt(instance: GameInstance, uid: str) -> str:
    """System prompt for one AI-hosted seat: a player, never the GM."""

    language = getattr(instance, "language", DEFAULT_LANGUAGE)
    return localized_text(language, _ACTION_PROMPT).format(
        name=character_name(instance, uid), uid=uid,
    )


def build_ai_player_request(instance: GameInstance, uid: str) -> str:
    """Untrusted request block: public actions so far + which seat must act."""

    language = getattr(instance, "language", DEFAULT_LANGUAGE)
    declared = declared_actions_text(instance)
    if not declared:
        declared = localized_text(language, _NO_DECLARED_ACTIONS)
    return "\n".join([
        localized_text(language, _DECLARED_ACTIONS_HEADING),
        declared,
        "",
        localized_text(language, _OWN_CHARACTER_HEADING),
        localized_text(language, _OWN_CHARACTER_REQUEST).format(
            name=character_name(instance, uid), uid=uid,
        ),
    ])


def declared_actions_text(instance: GameInstance) -> str:
    """The public actions already declared this round, in queue order.

    Only seats on the roster are listed, and only after this pass appended an AI
    action: a later AI seat therefore sees the human declarations and the AI
    declarations produced earlier in the same pass, exactly like a player reading
    the public timeline.
    """

    lines: list[str] = []
    for action in instance.action_queue:
        uid = str(action.get("user_id") or "")
        if uid not in instance.players:
            continue
        text = _one_line(str(action.get("text") or ""))
        if not text:
            continue
        lines.append(f"- {character_name(instance, uid)}（{uid}）：{text}")
    return "\n".join(lines)


def character_name(instance: GameInstance, uid: str) -> str:
    return str((instance.players.get(uid) or {}).get("character_name") or uid)


async def fill_ai_player_actions(
    instance: GameInstance,
    *,
    llm_client: Any,
    prompt_composer: Any = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> list[dict[str, Any]]:
    """Let every AI-hosted seat declare one action for the current round.

    The caller must invoke this only at the canonical submission seam, after the
    human gate is satisfied and before the round advances; the function re-checks
    both conditions itself so a repeated or mis-timed call is a no-op.  One LLM
    call is made per seat, sequentially, in sorted uid order.  The returned list
    records one outcome per seat (``added`` / ``skipped`` / ``discarded`` /
    ``duplicate``) for observability; failures never raise out of this function.
    """

    results: list[dict[str, Any]] = []
    if llm_client is None or not hasattr(llm_client, "call"):
        return results
    if instance.state != GameState.ACTIVE_ACTION or not instance.human_actions_ready():
        return results
    provider_name = str(getattr(llm_client, "default", "") or "")
    for uid in _ai_seats(instance):
        results.append(await _fill_one(
            instance,
            uid,
            llm_client=llm_client,
            prompt_composer=prompt_composer,
            provider_name=provider_name,
            max_tokens=max_tokens,
            temperature=temperature,
        ))
    return results


def _ai_seats(instance: GameInstance) -> list[str]:
    """AI-hosted seats in stable uid order, capped by the table's player limit."""

    uids = ai_controlled_players(instance)
    limit = max(0, int(getattr(instance, "max_players", 0) or 0))
    return uids[:limit] if limit else uids


async def _fill_one(
    instance: GameInstance,
    uid: str,
    *,
    llm_client: Any,
    prompt_composer: Any,
    provider_name: str,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    if not instance.is_alive(uid):
        # 死亡席位不能行动（add_action 也会拒绝），不必浪费一次模型调用。
        return _outcome(uid, "skipped", "deceased")
    round_number = int(instance.round_number or 0)
    if _existing_ai_action(instance, uid, round_number) is not None:
        # 幂等：同一 (run, round, uid) 至多一条 AI 行动。重复服务调用、SSE 重连
        # 或重试都会走到这里，而不是产生第二条行动。
        return _outcome(uid, "duplicate", "already_declared")
    run_id = str(getattr(instance, "run_id", "") or "")
    control = get_control(instance, uid)

    system_prompt = build_ai_player_prompt(instance, uid)
    request = build_ai_player_request(instance, uid)
    try:
        context = await _build_player_context(
            instance, uid, system_prompt, request,
            prompt_composer=prompt_composer, provider_name=provider_name,
        )
        response = await llm_client.call(
            system_prompt, context, temperature=temperature, max_tokens=max_tokens,
        )
    except Exception as exc:
        # 供应商错误 / 超时只影响这一个席位：不重试（沿用客户端自身的重试），
        # 不抛给调用方，本轮继续。
        return _skip(uid, f"call_failed:{type(exc).__name__}")
    tokens = int(getattr(response, "total_tokens", 0) or 0)
    instance.record_llm_usage(tokens, calls=1)

    text = _action_text(response)
    if not text:
        return _skip(uid, "unusable_output", tokens=tokens)

    stale = _stale_reason(instance, uid, run_id, round_number, control)
    if stale:
        logger.warning(
            "%s uid=%s round=%s reason=%s", DISCARD_MARKER, uid, round_number, stale,
        )
        return _outcome(uid, "discarded", stale, tokens=tokens)

    metadata = {
        "source": AI_ACTION_SOURCE,
        "control_revision": int(control["revision"]),
        "generated_for_round": round_number,
    }
    added = await instance.add_action(
        uid,
        text,
        source=AI_ACTION_SOURCE,
        action_metadata=metadata,
        defer_out_of_phase=False,
    )
    if not added:
        # 行动管线在锁内拒绝了写入（重写历史、阶段变化）：什么都不写。
        return _skip(uid, "action_rejected", tokens=tokens)
    return _outcome(uid, "added", "", tokens=tokens)


async def _build_player_context(
    instance: GameInstance,
    uid: str,
    system_prompt: str,
    request: str,
    *,
    prompt_composer: Any,
    provider_name: str,
) -> str:
    """Reuse the project's player-safe context builder; never a GM context.

    No lorebook entries are passed: an AI seat gets no knowledge channel that a
    human seat does not already have through the public timeline.
    """

    if prompt_composer is not None:
        return await prompt_composer.build_player_safe_context(
            instance, system_prompt, [], request, uid, provider_name=provider_name,
        )
    return await build_player_safe_context(
        instance, system_prompt, [], request, uid, provider_name=provider_name,
    )


def _stale_reason(
    instance: GameInstance,
    uid: str,
    run_id: str,
    round_number: int,
    control: dict[str, Any],
) -> str:
    """Why the in-flight result must be discarded, or ``""`` when it is current.

    All four captured identities (run, round, seat, control revision) must still
    match; the action phase is checked as well because a result produced for a
    round that already advanced must never be written into the next one.
    """

    if str(getattr(instance, "run_id", "") or "") != run_id:
        return "run_changed"
    if int(instance.round_number or 0) != round_number:
        return "round_changed"
    if uid not in instance.players:
        return "seat_removed"
    if get_control(instance, uid) != control:
        return "control_changed"
    if instance.state != GameState.ACTIVE_ACTION:
        return "phase_changed"
    return ""


def _existing_ai_action(
    instance: GameInstance, uid: str, round_number: int,
) -> dict[str, Any] | None:
    for action in instance.action_queue:
        if str(action.get("user_id") or "") != uid:
            continue
        metadata = action.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if str(metadata.get("source") or "") != AI_ACTION_SOURCE:
            continue
        if _metadata_round(metadata) == round_number:
            return action
    return None


def _metadata_round(metadata: dict[str, Any]) -> int:
    try:
        return int(metadata.get("generated_for_round"))
    except (TypeError, ValueError):
        return -1


def _action_text(response: Any) -> str:
    raw = str(getattr(response, "narration", "") or getattr(response, "content", "") or "")
    return sanitize_narration(raw).strip()[:MAX_AI_ACTION_CHARS].strip()


def _one_line(text: str, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _skip(uid: str, reason: str, *, tokens: int = 0) -> dict[str, Any]:
    logger.warning("%s uid=%s reason=%s", SKIP_MARKER, uid, reason)
    return _outcome(uid, "skipped", reason, tokens=tokens)


def _outcome(uid: str, status: str, reason: str, *, tokens: int = 0) -> dict[str, Any]:
    return {"uid": uid, "status": status, "reason": reason, "tokens": tokens}


__all__ = [
    "AI_ACTION_SOURCE",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_TEMPERATURE",
    "DISCARD_MARKER",
    "MAX_AI_ACTION_CHARS",
    "SKIP_MARKER",
    "build_ai_player_prompt",
    "build_ai_player_request",
    "character_name",
    "declared_actions_text",
    "fill_ai_player_actions",
]
