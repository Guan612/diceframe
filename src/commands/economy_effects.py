"""Bridge narrative proposals to authoritative economic decisions.

The LLM may describe and propose a transaction, but state changes which depend
on that transaction must not become authoritative until the decision commits.
This module extracts those effects from one parsed response.  The command
orchestrator owns applying them later; the engine economy owns their persisted
decision group.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from src.engine.language import localized_text

_ECONOMY_STATE_KEYS = {"pending_payments", "economy_proposals"}
_DEFERRED_DATA_KEYS = {
    "confirmed",
    "growth_skills",
    "info_asymmetry",
    "memory_delta",
    "milestone_grants",
    "plot_update",
    "quick_actions",
    "scene_image_prompt",
    "xp_rewards",
}

_COMPLETED_PAYMENT_RE = re.compile(
    r"(?:掏出|拿出|交出|付出|支付了?|缴纳了?|付清|花费了?)\s*"
    r"(?:[一二三四五六七八九十百千万两\d]+)\s*(?:枚|个)?\s*(?:金币|金子|金)"
    r"|(?:paid|spent|handed over|paid out)\s+"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+gold",
    re.IGNORECASE,
)
_CONDITIONAL_REWARD_RE = re.compile(
    r"(?:要是|如果|若是|完成[^。！？\n]{0,20}后|之后再|等你|待你|才能|才会|以后|将会|承诺|答应|promise|promises|will pay|\bif\b|\bonce\b|\bafter\b|\bwhen\b|\u3067\u304d\u305f\u3089|\u7d42\u308f\u3063\u305f\u3089)",
    re.IGNORECASE,
)
_COMPLETION_EVIDENCE_RE = re.compile(
    r"(?:完成|成功|击败|打倒|交付|归还|回收|达成|兑现|领取|earned|completed|complete|defeated|delivered|recovered|claimed|critical success|大成功)",
    re.IGNORECASE,
)
_UNBACKED_CHARGE_RE = re.compile(
    r"(?:需要|需|必须|须|售价|价格|费用|收费|支付|付费|购买|买下|花费|缴纳|"
    r"cost|price|charge|pay|purchase|spend)"
    r"[^。！？\n]{0,24}?"
    r"(?:[一二三四五六七八九十百千万两\d]+)\s*(?:枚|个)?\s*(?:金币|金子|金|gold|credits?|dollars?)"
    r"|(?:[一二三四五六七八九十百千万两\d]+)\s*(?:金币|金子|金|gold|credits?|dollars?)"
    r"[^。！？\n]{0,16}?"
    r"(?:需要|需|支付|付费|购买|买下|花费|缴纳|cost|price|charge|pay|purchase|spend)",
    re.IGNORECASE,
)


def _meaningful(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_meaningful(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_meaningful(item) for item in value)
    return value not in {None, "", False, 0}


def has_economy_proposal(data: dict[str, Any]) -> bool:
    state_update = data.get("state_update")
    if not isinstance(state_update, dict):
        return False
    return bool(
        state_update.get("pending_payments")
        or state_update.get("economy_proposals")
    )


def discard_unearned_reward_proposals(
    instance: Any,
    data: dict[str, Any],
    narration: str,
) -> int:
    """Drop rewards that are still conditional promises, before queueing them.

    ``GOLD`` is intentionally still a proposal, but a proposal must represent
    an earned event. A common model failure is to emit GOLD while an NPC is
    merely promising payment after a task is completed. Such a reward is kept
    in the prose but cannot enter the authoritative economy until a later turn
    records completion. Explicit same-turn or previously completed quest state
    is accepted as the completion evidence.
    """

    state_update = data.get("state_update")
    if not isinstance(state_update, dict):
        return 0
    proposals = state_update.get("economy_proposals")
    if not isinstance(proposals, list) or not proposals:
        return 0
    rewards = [item for item in proposals if isinstance(item, dict) and item.get("kind") == "reward"]
    narration_text = str(narration or "")
    if not rewards:
        return 0

    completed_titles: set[str] = set()
    plot_update = data.get("plot_update")
    if isinstance(plot_update, dict):
        for quest in plot_update.get("quests", []):
            if isinstance(quest, dict) and str(quest.get("status") or "").casefold() in {"completed", "complete", "已完成", "完成", "成功"}:
                title = str(quest.get("title") or "").strip().casefold()
                if title:
                    completed_titles.add(title)
    tracker = getattr(instance, "plot_tracker", None)
    for quest in getattr(tracker, "quests", {}).values() if tracker is not None else []:
        status = getattr(getattr(quest, "status", None), "value", getattr(quest, "status", ""))
        if str(status).casefold() in {"completed", "complete", "已完成", "完成", "成功"}:
            title = str(getattr(quest, "title", "") or "").strip().casefold()
            if title:
                completed_titles.add(title)

    kept: list[dict[str, Any]] = []
    dropped = 0
    for proposal in proposals:
        if proposal not in rewards:
            kept.append(proposal)
            continue
        reason = str(proposal.get("reason") or "").casefold()
        if any(title in reason or reason in title for title in completed_titles):
            kept.append(proposal)
            continue
        # A reward needs affirmative completion evidence in the same turn. A
        # conditional/promise phrase takes precedence, even if the model also
        # mentions a future payment elsewhere in the paragraph.
        if (
            _COMPLETION_EVIDENCE_RE.search(narration_text)
            and not _CONDITIONAL_REWARD_RE.search(narration_text)
        ):
            kept.append(proposal)
            continue
        dropped += 1
    state_update["economy_proposals"] = kept
    return dropped


def unearned_reward_notice(language: str) -> str:
    return localized_text(language, {
        "en": "Reward pending: the story described a conditional promise, so no reward proposal was created until the task is confirmed complete.",
        "zh-CN": "奖励待确认：当前剧情只是条件性承诺，任务确认完成前不会生成奖励提案。",
        "ja": "報酬保留中：物語が条件付きの約束を示しているため、任務の完了が確認されるまで報酬提案は作成されません。",
    })


def guard_unbacked_payment_narration(
    narration: str,
    data: dict[str, Any],
    language: str,
) -> str:
    """Prevent prose from claiming a completed payment without authority.

    Currency changes are authoritative only through PAY/TEAM_PAY/economy
    proposals.  Models occasionally narrate handing over coins while omitting
    the protocol tag; leave the balance untouched and make that fact explicit
    instead of presenting a false completed transaction to the player.
    """

    text = str(narration or "").strip()
    if not text or has_economy_proposal(data) or not _COMPLETED_PAYMENT_RE.search(text):
        return text
    notice = {
        "en": "Authority notice: no payment proposal was created, so no gold was deducted. Ask the GM to issue a payment proposal if this fee should be charged.",
        "zh-CN": "权威账本提示：本次没有生成支付提案，因此未扣除金币。若确实需要收费，请由 GM 重新发起支付提案。",
        "ja": "権威台帳の通知：支払い提案が作成されなかったため、ゴールドは差し引かれていません。請求が必要なら GM に支払い提案を出してもらってください。",
    }.get(str(language or "").lower(), "权威账本提示：本次没有生成支付提案，因此未扣除金币。若确实需要收费，请由 GM 重新发起支付提案。")
    return f"{text}\n\n{notice}"


def discard_unbacked_purchase_items(
    data: dict[str, Any],
    narration: str,
) -> int:
    """Fail closed when prose describes a priced purchase without a proposal.

    A model can emit ``LOOT`` while narrating a shop price but omit ``PAY`` /
    ``ECONOMY``.  Granting that loot would make the item authoritative even
    though no payment decision exists.  Drop the transaction-dependent loot;
    the GM can issue a proposal explicitly on a later turn.
    """

    if has_economy_proposal(data) or not _UNBACKED_CHARGE_RE.search(str(narration or "")):
        return 0
    state_update = data.get("state_update")
    if not isinstance(state_update, dict):
        return 0
    loot = state_update.get("loot")
    if not isinstance(loot, list) or not loot:
        return 0
    dropped = len(loot)
    state_update["loot"] = []
    return dropped


def unbacked_purchase_notice(language: str) -> str:
    return localized_text(language, {
        "en": "Purchase items were not granted because no payment proposal was created.",
        "zh-CN": "由于没有生成支付提案，本次购买物品未发放。",
        "ja": "支払い提案が作成されなかったため、購入品は付与されませんでした。",
    })


def defer_narrative_effects(
    data: dict[str, Any],
    response: Any,
) -> dict[str, Any]:
    """Remove decision-dependent effects from the immediate round response."""

    if not has_economy_proposal(data):
        return {}
    state_update = dict(data.get("state_update") or {})
    immediate_state = {
        key: deepcopy(value)
        for key, value in state_update.items()
        if key in _ECONOMY_STATE_KEYS
    }
    deferred_state = {
        key: deepcopy(value)
        for key, value in state_update.items()
        if key not in _ECONOMY_STATE_KEYS and _meaningful(value)
    }
    deferred: dict[str, Any] = {}
    if deferred_state:
        deferred["state_update"] = deferred_state
    data["state_update"] = immediate_state
    response.state_update = immediate_state

    for key in _DEFERRED_DATA_KEYS:
        value = data.get(key)
        if _meaningful(value):
            deferred[key] = deepcopy(value)
        if key in {"memory_delta"}:
            data[key] = {"add": [], "update": [], "forget": []}
        elif key == "plot_update":
            data[key] = {"quests": [], "relations": [], "decisions": []}
        elif key in {"info_asymmetry"}:
            data[key] = {}
        elif key in {"confirmed", "growth_skills", "milestone_grants", "quick_actions"}:
            data[key] = []
        elif key == "xp_rewards":
            data[key] = {}
        else:
            data[key] = ""

    response.memory_delta = data.get("memory_delta", {})
    response.info_asymmetry = data.get("info_asymmetry", {})
    response.plot_update = data.get("plot_update", {})
    return deferred


def pending_decision_notice(language: str) -> str:
    return localized_text(language, {
        "en": (
            "Settlement pending: any narrated goods, services, scene changes, or quest progress "
            "that depend on this transaction have not taken effect yet."
        ),
        "zh-CN": "结算待确认：本次交易关联的物品、服务、场景或任务推进尚未生效。",
        "ja": "決済確認待ち：この取引に関連するアイテム・サービス・場面・クエスト進行はまだ発効していません。",
    })
