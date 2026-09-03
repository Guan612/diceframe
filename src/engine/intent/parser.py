"""Narrative/intent text parsing primitives shared by the economy guards.

这些正则与金额解析原属 economy_effects，现下沉到 engine 作为 intent 层的
解析基座：ruleset-neutral，不依赖任何具体规则系统；规则只需通过
``currency_labels_for_rule`` 投影自己的货币称谓。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from src.engine.intent.models import PurchaseIntent

PURCHASE_INTENT_RE = re.compile(
    r"(?:买下|买了|购买|购入|买入|付费|支付|缴纳|花费|订购|租用|换购|purchase|buy|bought|pay|paid|spend)",
    re.IGNORECASE,
)
FREE_PURCHASE_RE = re.compile(r"(?:免费|无需付费|不用钱|免费领取|free|no charge)", re.IGNORECASE)
PURCHASE_CONFIRM_RE = re.compile(
    r"(?:成交|买了|买下|购买|确认购买|接受报价|就要这个|行|可以|同意|付钱|结账|"
    r"deal|accept|accepted|confirm|confirmed|buy it|take it|pay|yes|"
    r"成約|購入|承知|支払う|了解です|はい|了承)", re.IGNORECASE,
)
PURCHASE_OFFER_RE = re.compile(
    r"(?:需要|需|售价|价格|费用|收费|cost|price|charge)", re.IGNORECASE,
)
_PAYMENT_VERB_RE = re.compile(
    r"(?:掏|拿出|递给?|付|支付|付钱|结账|给钱|花费|spend|pay|buy|purchase|bought|paid)",
    re.IGNORECASE,
)


def currency_labels(extra_labels: Iterable[str] | None = None) -> tuple[str, ...]:
    """Return canonical rule labels plus legacy aliases for text recognition.

    Narrative parsing is only a repair/fail-closed guard; the persisted
    currency schema remains authoritative.  Rule-provided labels let the same
    guard work for custom economies (USD, credits, gems, etc.) without adding
    ruleset branches to the generic engine.
    """

    labels = {
        "金币", "金子", "金", "gold", "credits", "credit", "dollars", "dollar",
    }
    for label in extra_labels or ():
        value = str(label or "").strip()
        if value:
            labels.add(value)
    return tuple(sorted(labels, key=len, reverse=True))


def currency_labels_for_rule(rule: Any) -> tuple[str, ...]:
    """Project declared rule currency IDs/names into the generic text guard."""

    system = getattr(rule, "currency_system", None)
    if not isinstance(system, dict) and isinstance(rule, dict):
        system = rule.get("currency_system")
    units = system.get("units", []) if isinstance(system, dict) else []
    labels: list[str] = []
    if isinstance(units, list):
        for unit in units:
            if isinstance(unit, dict):
                labels.extend(
                    str(unit.get(key) or "").strip()
                    for key in ("id", "name", "label")
                    if str(unit.get(key) or "").strip()
                )
    return currency_labels(labels)


def currency_amount_pattern(extra_labels: Iterable[str] | None = None) -> re.Pattern[str]:
    labels = "|".join(re.escape(label) for label in currency_labels(extra_labels))
    return re.compile(
        rf"(?P<amount>[0-9]+|[零〇一二三四五六七八九十百千万两]+)"
        rf"\s*(?:枚|个)?\s*(?:{labels})",
        re.IGNORECASE,
    )


def charge_pattern(extra_labels: Iterable[str] | None = None) -> re.Pattern[str]:
    labels = "|".join(re.escape(label) for label in currency_labels(extra_labels))
    return re.compile(
        rf"(?:需要|需|必须|须|售价|价格|费用|收费|支付|付费|购买|买下|花费|缴纳|"
        rf"cost|price|charge|pay|purchase|spend)[^。！？\n]{{0,24}}?"
        rf"(?:[一二三四五六七八九十百千万两\d]+)\s*(?:枚|个)?\s*(?:{labels})"
        rf"|(?:[一二三四五六七八九十百千万两\d]+)\s*(?:{labels})"
        rf"[^。！？\n]{{0,16}}?"
        rf"(?:需要|需|支付|付费|购买|买下|花费|缴纳|cost|price|charge|pay|purchase|spend)",
        re.IGNORECASE,
    )


def completed_payment_pattern(extra_labels: Iterable[str] | None = None) -> re.Pattern[str]:
    labels = "|".join(re.escape(label) for label in currency_labels(extra_labels))
    return re.compile(
        rf"(?:掏出|拿出|数出|数了|递出|放下|交出|付出|支付了?|缴纳了?|付清|花费了?)\s*"
        rf"(?:[一二三四五六七八九十百千万两\d]+)\s*(?:枚|个)?\s*(?:{labels})"
        rf"|(?:paid|spent|handed over|paid out)\s+"
        rf"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:{labels})",
        re.IGNORECASE,
    )


def _chinese_amount(value: str) -> int | None:
    """Parse the small Chinese numerals commonly used in narrative prices."""

    if value.isdigit():
        return int(value)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    total = 0
    section = 0
    number = 0
    for char in value:
        if char in digits:
            number = digits[char]
        elif char in units:
            unit = units[char]
            if unit == 10000:
                section = (section + number) * unit
                total += section
                section = 0
            else:
                section += (number or 1) * unit
            number = 0
        else:
            return None
    return total + section + number


def currency_amounts(
    narration: str,
    extra_labels: Iterable[str] | None = None,
) -> list[int]:
    amounts: list[int] = []
    for match in currency_amount_pattern(extra_labels).finditer(str(narration or "")):
        amount = _chinese_amount(match.group("amount"))
        if amount is not None and amount > 0:
            amounts.append(amount)
    return amounts


def item_context_from_action(
    text: str,
    extra_labels: Iterable[str] | None = None,
) -> str:
    """Derive a loose item hint from one player action.

    去掉金额、货币与购买动词后剩下的片段作为商品指代；只用于澄清展示与
    宽松绑定，永远不作为价格或身份的权威来源。
    """

    cleaned = currency_amount_pattern(extra_labels).sub(" ", str(text or ""))
    cleaned = re.sub(r"[（(][^）)]*[)）]", " ", cleaned)
    cleaned = PURCHASE_INTENT_RE.sub(" ", cleaned)
    cleaned = _PAYMENT_VERB_RE.sub(" ", cleaned)
    return re.sub(r"^[\s，,。.、：:；;'-]+|[\s，,。.、：:；;'-]+$", "", cleaned)


def parse_purchase_intents(
    action_records: Iterable[Any],
    players: Any,
    extra_labels: Iterable[str] | None = None,
) -> list[PurchaseIntent]:
    """Parse each player's own action into one purchase intent.

    每个 actor 独立解析：意图只来自玩家自己的行动文本，AI 输出不参与。
    没有购买动词的行动不产生意图。
    """

    intents: list[PurchaseIntent] = []
    for action in action_records:
        if not isinstance(action, dict):
            continue
        actor_uid = str(action.get("user_id") or "")
        text = str(action.get("text") or "")
        if not actor_uid or actor_uid not in players:
            continue
        if not PURCHASE_INTENT_RE.search(text):
            continue
        amounts = currency_amounts(text, extra_labels)
        intents.append(PurchaseIntent(
            actor_uid=actor_uid,
            action_text=text,
            item_context=item_context_from_action(text, extra_labels),
            amount_candidates=tuple(sorted(set(amounts))),
        ))
    return intents
