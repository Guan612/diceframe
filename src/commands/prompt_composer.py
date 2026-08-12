"""GM prompt 与上下文构造器。

集中处理基础 GM prompt、规则附录、剧情追踪文本和 context_builder 调用，
避免 process_round / generate_swipe 重复拼装。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.engine.game_instance import GameInstance
from src.engine.language import DEFAULT_LANGUAGE, gm_language_instruction, localized_text
from src.llm.context_builder import build_context
from src.memory.delta import MemoryStore
from src.rules.rule_system import RuleSystem

logger = logging.getLogger("trpg")
_GM_PROMPT_CACHE: dict[str, str] | None = {}


@dataclass
class RulePromptContext:
    """当前世界规则对 prompt / 判定流程的影响。"""

    world_data: dict | None = None
    rule: RuleSystem | None = None
    rule_appendix: str = ""
    combat_model: str = "hp_based"
    dice_system: str = "d20"


class PromptComposer:
    """构造 GM prompt 和 LLM user context。"""

    def __init__(
        self,
        prompts_dir: Path,
        rules_dir: Path,
        memory_store: MemoryStore | None = None,
    ):
        self.prompts_dir = prompts_dir
        self.rules_dir = rules_dir
        self.memory_store = memory_store

    def load_gm_prompt(self, rule_appendix: str = "", language: str = DEFAULT_LANGUAGE) -> str:
        """读取基础 GM prompt，并按需附加当前规则说明。"""
        global _GM_PROMPT_CACHE
        if _GM_PROMPT_CACHE is None:
            _GM_PROMPT_CACHE = {}
        cache_key = localized_text(language, {"en": "en", "zh-CN": "zh-CN", "ja": "ja"})
        if cache_key not in _GM_PROMPT_CACHE:
            filename = (
                "gm_system_en.md" if cache_key == "en"
                else ("gm_system_ja.md" if cache_key == "ja" else "gm_system_zh.md")
            )
            path = self.prompts_dir / filename
            if path.exists():
                _GM_PROMPT_CACHE[cache_key] = path.read_text(encoding="utf-8")
            elif cache_key == "en":
                zh = self.prompts_dir / "gm_system_zh.md"
                _GM_PROMPT_CACHE[cache_key] = (
                    zh.read_text(encoding="utf-8")
                    if zh.exists()
                    else "You are the GM for a TRPG text adventure. Narrate in natural English. The GM prompt file is missing."
                )
            else:
                # ja 等非 en 语言的 prompt 缺失时先回退英文文件，再回退中文。
                # 输出语言仍由 gm_language_instruction 单独控制，不受此回退影响。
                en = self.prompts_dir / "gm_system_en.md"
                zh = self.prompts_dir / "gm_system_zh.md"
                if en.exists():
                    _GM_PROMPT_CACHE[cache_key] = en.read_text(encoding="utf-8")
                elif zh.exists():
                    _GM_PROMPT_CACHE[cache_key] = zh.read_text(encoding="utf-8")
                else:
                    _GM_PROMPT_CACHE[cache_key] = "你是 TRPG 游戏的主持人（GM）。请用流畅中文进行叙述。（GM prompt 文件缺失）"
        prompt = _GM_PROMPT_CACHE[cache_key]
        if rule_appendix:
            heading = localized_text(cache_key, {"en": "## Current Rules", "zh-CN": "## 当前规则", "ja": "## 現在のルール"})
            prompt += f"\n\n{heading}\n{rule_appendix}"
        return prompt

    def load_rule_context(
        self,
        instance: GameInstance,
        load_world_template: Callable[[str], dict],
    ) -> RulePromptContext:
        """加载世界默认规则，并构造规则 prompt 附录。失败时保持旧行为：静默回退默认值。"""
        ctx = RulePromptContext()
        if not instance.world_id:
            return ctx
        try:
            world_data = load_world_template(instance.world_id)
            ctx.world_data = world_data
            if world_data:
                rule = RuleSystem.load_for_world(world_data, self.rules_dir)
                if rule:
                    ctx.rule = rule
                    language = getattr(instance, "language", DEFAULT_LANGUAGE)
                    ctx.rule_appendix = rule.get_gm_prompt_appendix(language)
                    ctx.combat_model = rule.combat_model
                    ctx.dice_system = rule.dice_system
                    difficulty_text = rule.get_difficulty_instructions(instance.difficulty, language)
                    if difficulty_text:
                        ctx.rule_appendix = ctx.rule_appendix + "\n\n" + difficulty_text
        except Exception:
            logger.warning("规则上下文加载失败，回退默认值: world_id=%s", instance.world_id, exc_info=True)
        return ctx

    def load_swipe_rule_context(
        self,
        instance: GameInstance,
        load_world_template: Callable[[str], dict],
    ) -> RulePromptContext:
        """加载 swipe 重生成用规则上下文，保持原先按 rule_path 读取的行为。"""
        ctx = RulePromptContext()
        if not instance.world_id:
            return ctx
        try:
            world_data = load_world_template(instance.world_id)
            ctx.world_data = world_data
            if world_data:
                rule = RuleSystem.load_for_world(world_data, self.rules_dir)
                if rule:
                    ctx.rule = rule
                    language = getattr(instance, "language", DEFAULT_LANGUAGE)
                    ctx.rule_appendix = rule.get_gm_prompt_appendix(language)
                    ctx.combat_model = rule.combat_model
                    ctx.dice_system = rule.dice_system
                    difficulty_text = rule.get_difficulty_instructions(instance.difficulty, language)
                    if difficulty_text:
                        ctx.rule_appendix += "\n\n" + difficulty_text
        except Exception:
            logger.warning("swipe 规则上下文加载失败，回退默认值: world_id=%s", instance.world_id, exc_info=True)
        return ctx

    def compose_gm_prompt(self, instance: GameInstance, rule_appendix: str = "") -> str:
        """构造系统 prompt：基础 prompt + 规则附录 + 剧情追踪。"""
        language = getattr(instance, "language", DEFAULT_LANGUAGE)
        gm_prompt = self.load_gm_prompt(rule_appendix, language)
        plot_text = instance.plot_tracker.format_for_context() if instance.plot_tracker else ""
        if plot_text:
            gm_prompt = gm_prompt + "\n\n" + plot_text
        gm_prompt = gm_prompt + "\n\n" + gm_language_instruction(getattr(instance, "language", "zh-CN"))
        return gm_prompt

    async def build_user_context(
        self,
        instance: GameInstance,
        gm_prompt: str,
        lorebook_matches: list[dict],
        actions_text: str,
        provider_name: str = "",
        world_data: dict | None = None,
        history_override: list[dict] | None = None,
    ) -> str:
        """调用 context_builder 生成本轮 user context。"""
        return await build_context(
            instance,
            gm_prompt,
            lorebook_matches,
            actions_text,
            memory_store=self.memory_store,
            provider_name=provider_name,
            lorebook_budget=world_data.get("lorebook_token_budget", 0) if world_data else 0,
            history_override=history_override,
        )
