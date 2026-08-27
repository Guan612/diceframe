"""游戏开始、恢复、重置与重开流程。"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from src.commands.protocol_repair import repair_malformed_protocol_response
from src.commands.state_update_applier import StateUpdateApplier
from src.commands.tag_parser import (
    parse_tag_state,
)
from src.commands.tag_json import extract_narration_from_response
from src.commands.tag_summary import summarize_tags
from src.engine.character_utils import reset_character_for_restart
from src.engine.game_instance import GameInstance, GameRegistry, GameState
from src.engine.language import DEFAULT_LANGUAGE, localized_text, normalize_language
from src.engine.narrative_perspective import narrative_perspective_instruction
from src.llm.parser import normalize_tag_protocol, sanitize_narration

logger = logging.getLogger("trpg")


class GameLifecycle:
    """负责游戏生命周期操作，避免 GameHandler 承担所有流程细节。"""

    def __init__(
        self,
        registry: GameRegistry,
        llm_client: Any,
        prompt: Any,
        state_applier: StateUpdateApplier,
        ensure_matcher_for_world: Callable[[str, str], None],
        create_game: Callable[..., Awaitable[GameInstance]],
        load_world_template: Callable[[str, str], dict | None],
        narrative_max_tokens: int,
        brief_max_tokens: int,
    ):
        self.registry = registry
        self.llm_client = llm_client
        self.prompt = prompt
        self.state_applier = state_applier
        self.ensure_matcher_for_world = ensure_matcher_for_world
        self.create_game = create_game
        self.load_world_template = load_world_template
        self.narrative_max_tokens = narrative_max_tokens
        self.brief_max_tokens = brief_max_tokens

    async def start_game(self, instance: GameInstance) -> str:
        """激活游戏，生成开场叙事，进入第一轮。"""
        await instance.activate()
        await instance.start_round()
        self.registry.register(instance)

        if instance.world_id:
            self.ensure_matcher_for_world(instance.world_id, instance.language)

        rule_ctx = self.prompt.load_rule_context(instance, self.load_world_template)
        gm_prompt = self.prompt.compose_gm_prompt(instance, rule_ctx.rule_appendix)
        world_data = rule_ctx.world_data or {}
        world_description = world_data.get("description", "")
        world_setting = world_data.get("world_setting", "")
        starter_scene = world_data.get("starter_scene", "")
        sandbox_world = bool(world_data.get("sandbox"))
        player_lines = []
        for pdata in instance.players.values():
            cs = pdata.get("character_sheet", {})
            player_lines.append(
                f"- {pdata.get('character_name', '冒险者')}："
                f"{cs.get('race', '人类')} {cs.get('class', '冒险者')}"
                f"；背景：{cs.get('background', '') or '未填写'}"
            )
        players_text = "\n".join(player_lines) if player_lines else "尚未创建角色"
        if sandbox_world:
            opening_instruction = localized_text(
                instance.language,
                {
                    "en": (
                        "This is an intentionally blank freeform sandbox with no preset canon, era, "
                        "location, factions, or NPCs. Use only the player character names and backgrounds "
                        "to establish a minimal opening situation, and leave room for the players to define "
                        "the world through play. Do not assume a tavern, medieval fantasy, or any other genre "
                        "unless a character concept establishes it.\n\n"
                        "Write a concise 100-150 word opening that offers an immediate choice."
                    ),
                    "zh-CN": (
                        "这是一个有意保持空白的自由沙盒，没有预设时代、地点、阵营、NPC 或固定世界观。"
                        "只根据玩家已经填写的角色姓名与背景建立最少的开场事实，并允许玩家在行动中继续定义世界。"
                        "除非角色设定明确提到，否则不得默认套用酒馆、中世纪奇幻或其他固定题材。"
                        "\n\n请用 100 至 150 字给出一个简洁、可立即行动的开场。"
                    ),
                    "ja": (
                        "これは意図的に空白のフリーフォームサンドボックスで、事前設定された世界観・時代・"
                        "場所・派閥・NPC はない。プレイヤーが入力したキャラクター名と背景だけを使って、"
                        "最小限のオープニング状況を構築し、プレイを通じて世界を定義していく余地を残すこと。"
                        "キャラクターコンセプトで明示されない限り、酒場や中世ファンタジーなどのジャンルを"
                        "勝手に想定しない。\n\n簡潔な 100〜150 字の、すぐ行動できるオープニングを書くこと。"
                    ),
                },
            )
        else:
            opening_instruction = localized_text(
                instance.language,
                {
                    "en": (
                        "The game has just started. As GM, strictly follow the world setting, era, "
                        "location, and genre above. Describe the opening scene, introduce the "
                        "current environment, and make clear where the player characters are. "
                        "Do not switch to another genre, city, or era without cause.\n\n"
                        "Write about 120-180 English words for the opening scene and naturally "
                        "mention the player character names."
                    ),
                    "zh-CN": (
                        "游戏刚刚开始，请作为 GM 严格沿用上面的世界设定、时代、地点和题材，"
                        "描述开场场景，介绍当前环境和玩家所在的位置。不得无端切换到其他题材、城市或时代。"
                        "\n\n请用 150 字左右描述开场场景，并自然点出玩家角色名。"
                    ),
                    "ja": (
                        "ゲームは始まったばかり。GM として上記の世界設定・時代・場所・ジャンルを厳密に守り、"
                        "オープニングシーンを描写し、現在の環境を紹介し、プレイヤーキャラクターの位置を明確にすること。"
                        "理由なく別のジャンル・都市・時代に切り替えてはならない。\n\n"
                        "120〜180 語程度のオープニングシーンを書き、プレイヤーキャラクター名を自然に言及すること。"
                    ),
                },
            )
        opening_instruction += "\n\n" + narrative_perspective_instruction(
            instance, instance.language,
        )
        welcome_context = (
            f"{gm_prompt}\n\n"
            f"【当前世界】\n"
            f"名称：{instance.world_name}\n"
            f"简介：{world_description or '无'}\n"
            f"世界设定：{world_setting or '无'}\n"
            f"模板开场：{starter_scene or '无'}\n\n"
            f"【玩家角色】\n{players_text}\n\n"
            f"【开场场景】\n"
            f"{opening_instruction}"
        )

        response = None
        try:
            response = await self.llm_client.call(
                system_prompt=gm_prompt,
                user_message=welcome_context,
                temperature=0.8,
                max_tokens=self.narrative_max_tokens,
            )
            response = await repair_malformed_protocol_response(
                self.llm_client,
                response,
                system_prompt=gm_prompt,
                user_message=welcome_context,
                language=instance.language,
                temperature=0.8,
                max_tokens=self.narrative_max_tokens,
            )
            response.content = normalize_tag_protocol(response.content)
            narration = extract_narration_from_response(response)
            if "---" in response.content:
                narration = response.content.split("---", 1)[0].strip()
            narration = sanitize_narration(narration)
            # 开场标签同样需要落地到 instance：NPC 登记、场景、首次战利品等。
            start_data = parse_tag_state(response.content, rule_ctx.combat_model)
        except Exception:
            logger.exception("开场叙事生成失败，已保存可继续的兜底开场")
            narration = localized_text(
                instance.language,
                {
                    "en": (
                        f"{instance.world_name} is ready. The opening narration could not be "
                        "generated, but your game and characters have been saved. Configure or "
                        "retry the model service, then continue when you are ready."
                    ),
                    "zh-CN": (
                        f"《{instance.world_name}》已经创建，角色与存档均已保存。"
                        "本次开场叙事生成失败；请检查模型服务后继续游戏或重试。"
                    ),
                    "ja": (
                        f"『{instance.world_name}』を作成し、キャラクターとセーブを保存しました。"
                        "オープニング生成に失敗したため、モデル設定を確認してから続行または再試行してください。"
                    ),
                },
            )
            start_data = {}
        if start_data.get("state_update"):
            self.state_applier.apply_state_update(instance, start_data["state_update"])
        if start_data.get("plot_update") and instance.plot_tracker:
            try:
                instance.plot_tracker.apply_update(start_data["plot_update"], 0)
            except Exception:
                logger.exception("开场剧情更新异常，已跳过")
        if start_data.get("quick_actions"):
            instance.set_quick_actions(start_data["quick_actions"])
        scene = (start_data.get("state_update") or {}).get("scene_change", "")
        start_label = localized_text(
            getattr(instance, "language", ""),
            {"en": "Game Start", "zh-CN": "游戏开始", "ja": "ゲーム開始"},
        )
        instance.set_scene(scene or start_label)
        if response is not None:
            instance.record_llm_usage(response.total_tokens)
        instance.append_log_entry({
            "round": 0,
            "actions": [{"user_id": "system", "text": start_label}],
            "gm_response": narration,
            "tags_summary": summarize_tags(start_data),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await self.registry.save(instance)
        return narration

    async def resume_game(self, instance: GameInstance) -> str:
        """从 PAUSED 状态恢复游戏，生成「上回说到」续接叙事。"""
        if instance.state != GameState.PAUSED:
            await instance.activate()
            return ""

        recent_log = instance.log[-5:] if instance.log else []
        if not recent_log:
            await instance.start_round()
            return ""

        gm_prompt = self.prompt.compose_gm_prompt(instance)
        history_text = "\n".join(
            f"Round {e.get('round','?')}: {sanitize_narration(e.get('gm_response',''))[:100]}"
            for e in recent_log
        )

        resume_prompt = localized_text(
            instance.language,
            {
                "en": (
                    "You are the GM of a TRPG game that has just resumed from pause. "
                    "Write a brief 'Previously on...' continuation in English, under 80 words. "
                    "Summarize the latest events and naturally lead into the current scene.\n\n"
                    f"Recent log:\n{history_text}\n\n"
                    f"Current scene: {instance.scene}\n"
                    f"Alive players: {', '.join(instance.alive_players) if instance.alive_players else 'none'}\n\n"
                    "Output narration only, without a JSON block."
                ),
                "zh-CN": (
                    f"你是 TRPG 的 GM，游戏刚刚从暂停中恢复。请生成一段不超过100字的「上回说到」续接叙事，"
                    f"概括最近发生的事情并自然推进到当前场景。\n\n"
                    f"最近日志：\n{history_text}\n\n"
                    f"当前场景：{instance.scene}\n"
                    f"存活玩家：{', '.join(instance.alive_players) if instance.alive_players else '无'}\n\n"
                    f"请直接输出叙事文本（不要 JSON 块）。"
                ),
                "ja": (
                    "あなたは TRPG の GM。ゲームは一時停止から再開したばかり。"
                    "「これまでのあらすじ」として、80 語以内の日本語の続きのナレーションを書くこと。"
                    "直近の出来事をまとめ、現在のシーンへ自然につなぐこと。\n\n"
                    f"最近のログ：\n{history_text}\n\n"
                    f"現在のシーン：{instance.scene}\n"
                    f"生存プレイヤー：{', '.join(instance.alive_players) if instance.alive_players else 'なし'}\n\n"
                    "ナレーションのみを出力し、JSON ブロックを付けないこと。"
                ),
            },
        )

        try:
            response = await self.llm_client.call(
                system_prompt=gm_prompt,
                user_message=resume_prompt,
                temperature=0.6,
                max_tokens=self.brief_max_tokens,
            )
            resume_narration = sanitize_narration(response.narration or response.content)
        except Exception:
            logger.exception("续接叙事生成失败")
            resume_narration = localized_text(
                instance.language,
                {
                    "en": f"The GM is back online. Current scene: {instance.scene}. Continue when ready.",
                    "zh-CN": f"GM 已重新上线。当前场景：{instance.scene}。输入 /go 继续冒险。",
                    "ja": f"GM は再起動した。現在のシーン：{instance.scene}。/go で冒険を続行。",
                },
            )

        await instance.start_round()
        await self.registry.save(instance)
        return resume_narration

    async def reset_game(self, instance: GameInstance) -> GameInstance:
        world_id = instance.world_id
        world_name = instance.world_name
        group_name = instance.group_name
        seed = instance.seed_code
        rule_id = instance.rule_id
        language = normalize_language(getattr(instance, "language", DEFAULT_LANGUAGE))
        await instance.reset(keep_seed=True)
        instance = await self.create_game(
            instance.game_key, world_id=world_id, world_name=world_name,
            group_name=group_name, seed_code=seed, rule_id=rule_id, language=language,
        )
        await self._start_reset_instance(instance)
        instance.record_llm_usage(calls=1)
        await self.registry.save(instance)
        return instance

    async def restart_game(self, instance: GameInstance) -> GameInstance:
        """重开世界：重置剧情/场景/日志，保留所有角色卡（回满 HP 和状态）。"""
        saved_players = dict(instance.players)
        for uid, pdata in saved_players.items():
            cs = pdata.get("character_sheet", {})
            pdata["character_sheet"] = reset_character_for_restart(cs)
            saved_players[uid] = pdata

        world_id = instance.world_id
        world_name = instance.world_name
        group_name = instance.group_name
        seed = instance.seed_code
        rule_id = instance.rule_id
        solo = instance.solo_mode
        narrative_perspective = instance.narrative_perspective
        language = normalize_language(getattr(instance, "language", DEFAULT_LANGUAGE))

        await instance.reset(keep_seed=True)
        instance = await self.create_game(
            instance.game_key, world_id=world_id, world_name=world_name,
            group_name=group_name, seed_code=seed, rule_id=rule_id, language=language,
        )
        instance.configure_session(
            solo_mode=solo,
            narrative_perspective=narrative_perspective,
        )
        instance.replace_players(saved_players)

        if not instance.players:
            raise ValueError("重开世界需要至少 1 名角色")

        await self._start_reset_instance(instance)
        instance.record_llm_usage(calls=1)
        await self.registry.save(instance)
        return instance

    async def _start_reset_instance(self, instance: GameInstance) -> str:
        """Resume the gameplay stack already bound to this save."""

        runtime_id = str((instance.ruleset_runtime or {}).get("id") or "")
        if not runtime_id or runtime_id == "core:legacy":
            return await self.start_game(instance)
        await instance.activate()
        self.registry.register(instance)
        world = self.load_world_template(instance.world_id, instance.language) or {}
        initial_scene = str(world.get("starter_scene") or instance.world_name or "").strip()
        if initial_scene:
            instance.set_scene(initial_scene)
        await self.registry.save(instance)
        return ""
