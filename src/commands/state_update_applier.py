"""LLM state_update 应用器。

从 game_handler 拆出的场景/战利品状态写入逻辑；
玩家字段更新拆到 player_state_applier，NPC 状态拆到 npc_state_applier，
战利品分类规则加载拆到 item_category_resolver，疯狂状态倒计时拆到 madness_tracker。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from src.compat.callbacks import load_world_template as load_world_template_compat
from src.engine.game_instance import GameInstance
from src.commands.item_category_resolver import ItemCategoryResolver
from src.commands.madness_tracker import MadnessTracker
from src.commands.npc_state_applier import NpcStateApplier
from src.commands.player_state_applier import PlayerStateApplier
from src.commands.state_items import (
    classify_item,
    grant_classified_item,
)
from src.rules.rule_system import RuleSystem
from src.engine.economy import queue_proposal

logger = logging.getLogger("trpg")

_MAX_LOOT_PER_ROUND = 20


def discard_unresolved_player_damage(instance: GameInstance, update: dict) -> None:
    """丢弃没有服务端失败检定依据的模型伤害标签。

    战斗伤害由战斗结算器直接写入 HP；环境、陷阱等不确定伤害则必须先有
    服务端 CheckResult。模型仍可负责叙事，但不能在玩家未失败、甚至没有
    检定时凭空把 HP 扣到 0。函数原地修改解析结果，确保实际状态、日志摘要
    与前端展示一致。
    """
    if not isinstance(update, dict):
        return
    failed_uids = {
        str(check.get("actor_uid") or "")
        for check in (instance.last_checks or [])
        if str(check.get("verdict") or "") in {"失败", "大失败", "failure", "fumble"}
    }
    players_update = update.get("players")
    if not isinstance(players_update, dict):
        return
    for uid, player_update in list(players_update.items()):
        if not isinstance(player_update, dict):
            continue
        hp_change = player_update.get("hp_change")
        if isinstance(hp_change, (int, float)) and hp_change < 0 and uid not in failed_uids:
            player_update.pop("hp_change", None)
            logger.warning(
                "模型伤害缺少失败检定依据，已丢弃: uid=%s change=%s round=%d",
                uid, hp_change, instance.round_number,
            )
        if not player_update:
            players_update.pop(uid, None)


class StateUpdateApplier:
    """将 LLM 输出的 state_update 应用到游戏状态。"""

    def __init__(
        self,
        rules_dir: Path,
        worlds_dir: Path | None,
        load_world_template: Callable[[str, str], dict],
    ):
        self._madness = MadnessTracker()
        self._players = PlayerStateApplier(self._madness)
        self._npcs = NpcStateApplier()
        self._item_cats = ItemCategoryResolver(rules_dir, worlds_dir, load_world_template)
        self._rules_dir = rules_dir
        self._load_world_template = load_world_template

    def _load_rule(self, instance: GameInstance) -> RuleSystem | None:
        try:
            language = str(getattr(instance, "language", "") or "")
            world_data = load_world_template_compat(
                self._load_world_template,
                str(instance.world_id or ""),
                language,
            ) or {}
            return RuleSystem.load_for_world(world_data, self._rules_dir, language)
        except ValueError:
            raise
        except Exception:
            logger.warning("STAT 规则加载失败: world_id=%s", instance.world_id, exc_info=True)
            return None

    def apply_state_update(
        self,
        instance: GameInstance,
        update: dict,
        allowed_player_uids: set | None = None,
    ) -> list[dict[str, Any]]:
        """将 LLM 输出的 state_update 应用到游戏状态。"""
        queued_proposals: list[dict[str, Any]] = []
        # 玩家状态更新（带当前规则，供 STAT 资源结算与阈值触发器使用）
        self._players.apply_players(
            instance,
            update.get("players", {}),
            rule=self._load_rule(instance),
            allowed_player_uids=allowed_player_uids,
        )

        # NPC 状态更新
        self._npcs.apply_npcs(instance, update.get("npcs", {}))

        # 场景变换
        scene_change = update.get("scene_change")
        if scene_change:
            instance.set_scene(scene_change)

        # 战利品 - 按规则 JSON 的 item_categories 智能分类；规则未定义时用内置回退
        rule_cats = self._item_cats.load_categories(instance)

        loot_entries = update.get("loot", [])
        if len(loot_entries) > _MAX_LOOT_PER_ROUND:
            logger.warning(
                "单轮战利品（LOOT/KEY_ITEM）共 %d 条，超过上限 %d，已保留前 %d 条",
                len(loot_entries),
                _MAX_LOOT_PER_ROUND,
                _MAX_LOOT_PER_ROUND,
            )
            loot_entries = loot_entries[:_MAX_LOOT_PER_ROUND]
        for loot in loot_entries:
            uid = loot.get("player", "")
            item_name = loot.get("item", "")
            if uid not in instance.players:
                continue
            cs = instance.get_character_sheet(uid)
            # 遍历所有品类关键字匹配
            category = loot.get("category") or classify_item(item_name, rule_cats)
            grant_classified_item(cs, item_name, category)

        # 待确认支付（PAY tag 不直接扣金币，转入 pending 等玩家确认）
        for proposal_index, pay in enumerate(update.get("pending_payments", [])):
            uid = pay.get("uid", "")
            amount = int(pay.get("amount", 0) or 0)
            if not uid or amount <= 0 or uid not in instance.players:
                continue
            recipient_uid = str(pay.get("recipient_uid") or uid)
            if recipient_uid not in instance.players:
                continue
            rewards = []
            for item_name in pay.get("items", [])[:8]:
                item_name = str(item_name).strip()[:120]
                if item_name:
                    rewards.append({
                        "name": item_name,
                        "category": classify_item(item_name, rule_cats),
                    })
            queued_proposals.append(queue_proposal(
                instance,
                kind="purchase" if rewards else "payment",
                payer_uid=uid,
                recipient_uid=recipient_uid,
                amount=amount,
                rewards=rewards,
                reason=pay.get("reason") or (
                    f"购买 {'、'.join(item['name'] for item in rewards)}"
                    if rewards else "GM 建议支付"
                ),
                source="pay_tag",
                source_ref=f"round:{instance.run_id}:{instance.round_number}:pay:{proposal_index}:{uid}:{amount}:{recipient_uid}:{'|'.join(item['name'] for item in rewards)}",
                approval_policy="payer",
            ))

        for proposal_index, proposal in enumerate(update.get("economy_proposals", [])):
            uid = str(proposal.get("uid") or "")
            amount = int(proposal.get("amount", 0) or 0)
            kind = str(proposal.get("kind") or "")
            contributors = [
                {"uid": str(item.get("uid") or ""), "amount": int(item.get("amount", 0) or 0)}
                for item in (proposal.get("contributors") or [])
                if isinstance(item, dict)
            ]
            is_team_fee = (
                kind == "fee"
                and str(proposal.get("approval_policy") or "") == "all_contributors"
                and len(contributors) >= 2
                and all(
                    item["uid"] in instance.players and item["amount"] > 0
                    for item in contributors
                )
                and sum(item["amount"] for item in contributors) == amount
            )
            if not is_team_fee and (uid not in instance.players or kind not in {"payment", "reward"}):
                continue
            reason = str(proposal.get("reason") or "经济提案")[:240]
            source = str(proposal.get("source") or "narrative")
            if kind == "reward":
                # Reward identity intentionally omits the round: repeating the same
                # target, amount and explicit cause in a later response is still the
                # same narrative reward, not a fresh grant.
                source_ref = f"narrative-reward:{instance.run_id}:{uid}:{amount}:{reason.casefold()}"
            else:
                contributor_ref = "|".join(
                    f"{item['uid']}={item['amount']}" for item in contributors
                )
                source_ref = (
                    f"round:{instance.run_id}:{instance.round_number}:economy:"
                    f"{proposal_index}:{kind}:{uid}:{amount}:{contributor_ref}:{reason.casefold()}"
                )
            queued_proposals.append(queue_proposal(
                instance,
                kind=kind,
                payer_uid=uid if kind == "payment" else "",
                recipient_uid=uid if kind == "reward" else uid,
                amount=amount,
                reason=reason,
                source=source,
                source_ref=source_ref,
                approval_policy=(
                    "all_contributors" if is_team_fee
                    else "gm" if kind == "reward"
                    else "payer"
                ),
                contributors=contributors if is_team_fee else None,
                visibility="party" if is_team_fee else "private",
            ))
        return queued_proposals

    def apply_madness(self, instance: GameInstance, uid: str, cs: dict, loss: int) -> None:
        """兼容旧内部调用；实际逻辑已拆到 MadnessTracker。"""
        self._madness.apply_madness(instance, uid, cs, loss)

    def tick_madness(self, instance: GameInstance) -> None:
        """兼容旧内部调用；实际逻辑已拆到 MadnessTracker。"""
        self._madness.tick_madness(instance)
