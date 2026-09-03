"""Intent 层的结构化模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PurchaseIntent:
    """One actor's stated purchase intent, parsed from their own action text.

    ``item_context`` 是去掉金额与购买动词后的商品指代片段（供澄清展示与
    宽松绑定），``amount_candidates`` 是该 actor 行动里出现的全部金额——
    多于一个时视为无法唯一确认。意图只是证据，不是交易事实。
    """

    actor_uid: str
    action_text: str
    item_context: str
    amount_candidates: tuple[int, ...]
