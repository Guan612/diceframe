from __future__ import annotations

from typing import Any

import pytest

from src.commands.round_llm import call_llm_with_tag_retry
from src.engine.game_instance import GameInstance
from src.llm.client import LLMResponse


class CompressionLLM:
    default = "compression-test"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def call(self, system_prompt: str, user_message: str, **kwargs) -> LLMResponse:
        self.calls.append({"system_prompt": system_prompt, "user_message": user_message, "kwargs": kwargs})
        if "请压缩以下 TRPG GM 正文" in user_message:
            content = "李玄清压低声音，指出银针与祭品名录都指向白马寺藏经阁。夜风骤停，绢帛上新名字正在浮现，若不立刻潜入查明阵法根源，下一具无面尸很快就会出现。"
        else:
            long_text = "李玄清展开绢帛。" * 100
            content = (
                f"{long_text}\n---\n"
                "KEY_ITEM:u1:摄魂银针\n"
                "QUICK_ACTIONS:潜入藏经阁|追踪银针黑气\n"
                "MEMORY:摄魂银针可反向追踪施术者"
            )
        return LLMResponse(
            content=content,
            narration=content.split("---", 1)[0].strip(),
            state_update=None,
            memory_delta=None,
            info_asymmetry=None,
            plot_update=None,
            total_tokens=10,
            is_narration_only=False,
            provider_used="compression-test",
        )


class EnglishCompressionLLM:
    default = "compression-test"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def call(self, system_prompt: str, user_message: str, **kwargs) -> LLMResponse:
        self.calls.append({"system_prompt": system_prompt, "user_message": user_message, "kwargs": kwargs})
        if "Compress the following TRPG GM narration" in user_message:
            content = "Alaric lowers his voice, pointing to the silver needle and the list of offerings as both pointing to the hidden archive of the White Horse Temple. The night wind dies; a new name is surfacing on the silk scroll."
        else:
            long_text = "Alaric unrolls the silk scroll. " * 100
            content = (
                f"{long_text}\n---\n"
                "KEY_ITEM:u1:Silver Needle\n"
                "QUICK_ACTIONS:Sneak into the archive|Follow the needle's trail\n"
                "MEMORY:The silver needle can trace the caster"
            )
        return LLMResponse(
            content=content,
            narration=content.split("---", 1)[0].strip(),
            state_update=None,
            memory_delta=None,
            info_asymmetry=None,
            plot_update=None,
            total_tokens=10,
            is_narration_only=False,
            provider_used="compression-test",
        )


@pytest.mark.asyncio
async def test_long_narration_is_compressed_without_reparsing_tags():
    llm = CompressionLLM()
    instance = GameInstance(game_key=("web", "compression", "bot"))

    response, data = await call_llm_with_tag_retry(
        llm,
        instance,
        "你是测试 GM。",
        "上下文",
        "hp_based",
        "",
        1024,
    )

    assert len(llm.calls) == 2
    assert llm.calls[1]["kwargs"]["max_tokens"] == 1024
    assert "白马寺藏经阁" in response.narration
    assert len(response.narration) < 260
    assert data["state_update"]["loot"][0]["item"] == "摄魂银针"
    assert data["quick_actions"] == ["潜入藏经阁", "追踪银针黑气"]
    assert "KEY_ITEM:u1:摄魂银针" in response.content


@pytest.mark.asyncio
async def test_long_english_narration_compresses_to_english_target():
    """英文叙事用英文压缩目标（~900 字符 ≈ 150 词），不是中文的 260 字符。"""
    llm = EnglishCompressionLLM()
    instance = GameInstance(game_key=("web", "compression-en", "bot"))
    instance.language = "en"

    response, data = await call_llm_with_tag_retry(
        llm,
        instance,
        "You are a test GM.",
        "context",
        "hp_based",
        "",
        1024,
    )

    assert len(llm.calls) == 2
    # 压缩 prompt 携带英文目标（~150 words），而非中文的 260 字符
    assert "~150 words" in llm.calls[1]["user_message"]
    assert "White Horse Temple" in response.narration
    assert data["state_update"]["loot"][0]["item"] == "Silver Needle"
    assert data["quick_actions"] == ["Sneak into the archive", "Follow the needle's trail"]
    assert "KEY_ITEM:u1:Silver Needle" in response.content


@pytest.mark.asyncio
async def test_unregistered_language_falls_back_to_chinese_limits():
    """未登记压缩配置的语言回退中文目标（future-proof：加语言只需登记字典条目）。"""
    llm = CompressionLLM()
    instance = GameInstance(game_key=("web", "compression-ja", "bot"))
    instance.language = "ja"  # 尚未登记的语言

    response, data = await call_llm_with_tag_retry(
        llm,
        instance,
        "你是测试 GM。",
        "上下文",
        "hp_based",
        "",
        1024,
    )

    assert len(llm.calls) == 2
    # 回退中文目标：压缩后叙事 < 260 字符，且走中文压缩 prompt
    assert "请压缩以下 TRPG GM 正文" in llm.calls[1]["user_message"]
    assert len(response.narration) < 260


@pytest.mark.asyncio
async def test_compress_failure_truncates_hard():
    """P2-C：压缩 LLM 失败时按目标长度硬截断，而非保留超长原文。"""
    from types import SimpleNamespace
    from src.commands.round_llm import _compress_long_narration

    class FailingLLM:
        default = "fail"

        async def call(self, **kwargs):
            raise RuntimeError("compress boom")

    inst = GameInstance(("web", "compress_fail", "bot"))
    long_text = "李玄清展开绢帛。" * 200
    response = SimpleNamespace(
        narration=long_text,
        content=long_text,
        state_update=None, memory_delta=None, info_asymmetry=None, plot_update=None,
        is_narration_only=True,
    )
    await _compress_long_narration(FailingLLM(), "gm_prompt", response, "动作文本", "hp_based", 2048)

    assert "…" in response.narration
    assert len(response.narration) <= 261  # soft 260 + 省略号
    assert response.narration != long_text
