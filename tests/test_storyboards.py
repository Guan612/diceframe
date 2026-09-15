"""Shared storyboard normalization and deterministic composition tests."""

from __future__ import annotations

import io
from types import SimpleNamespace

from PIL import Image
import pytest

from src.imagegen.storyboards import (
    build_storyboard_prompt,
    infer_scene_panels,
    normalize_scene_panels,
    overlay_storyboard_dividers,
    public_character_appearances,
    storyboard_layout,
)


def test_normalization_deduplicates_and_counts_only_overflow() -> None:
    panels, compressed = normalize_scene_panels([
        {"participants": "alice", "location": "车站", "description": "雨夜月台"},
        {"participants": "alice", "location": "车站", "description": "雨夜月台"},
        {"participants": "bob", "location": "地下室", "description": "血祭坛"},
        {"participants": "cara", "location": "钟楼", "description": "齿轮"},
        {"participants": "dan", "location": "码头", "description": "浓雾"},
        {"participants": "eve", "location": "森林", "description": "小径"},
        {},
        "invalid",
    ])

    assert [panel["location"] for panel in panels] == ["车站", "地下室", "钟楼", "码头", "森林"]
    assert compressed == 0


def test_layouts_and_prompt_preserve_panel_order() -> None:
    panels = [
        {"participants": ["alice"], "location": "A", "description": "first"},
        {"participants": ["bob"], "location": "B", "description": "second"},
        {"participants": [], "location": "C", "description": "third"},
    ]
    prompt, metadata = build_storyboard_prompt(panels)
    assert storyboard_layout(1) == "single"
    assert storyboard_layout(2) == "two-panel"
    assert storyboard_layout(3) == "three-panel"
    assert storyboard_layout(4) == "four-panel"
    assert storyboard_layout(5) == "five-panel"
    assert storyboard_layout(6) == "six-panel"
    assert storyboard_layout(7) == "six-panel"
    assert metadata["layout"] == "three-panel"
    assert prompt.index("Panel 1") < prompt.index("Panel 2") < prompt.index("Panel 3")
    assert "A" in prompt and "B" in prompt and "C" in prompt


def test_same_location_panels_merge_participants_and_descriptions() -> None:
    panels, compressed = normalize_scene_panels([
        {"participants": ["alice"], "location": "废弃车站", "description": "站在月台"},
        {"participants": ["bob"], "location": "废弃车站。", "description": "检查时刻表"},
    ])

    assert compressed == 0
    assert len(panels) == 1
    assert panels[0]["participants"] == ["alice", "bob"]
    assert "站在月台" in panels[0]["description"]
    assert "检查时刻表" in panels[0]["description"]


def test_single_panel_prompt_forbids_model_generated_splits() -> None:
    prompt, metadata = build_storyboard_prompt([
        {"participants": ["alice", "bob"], "location": "车站", "description": "两人在月台会合"},
    ])

    assert metadata["layout"] == "single"
    assert "single frame" in prompt
    assert "Do not create panels" in prompt
    assert "comic storyboard composition" not in prompt
    assert "gutters between panels" not in prompt


class _PanelLLM:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    async def call(self, system_prompt, user_message, **kwargs):
        self.calls.append((system_prompt, user_message, kwargs))
        return SimpleNamespace(content=self.content)


@pytest.mark.asyncio
async def test_ai_infers_distinct_public_locations_and_exact_player_ids() -> None:
    llm = _PanelLLM(
        '{"panels":['
        '{"participants":["Alice"],"location":"废弃车站","description":"Alice站在雨夜月台"},'
        '{"participants":["bob"],"location":"钟楼地下室","description":"Bob检查石室祭坛"}'
        '],"compressed_count":0}'
    )
    panels, compressed = await infer_scene_panels(
        llm,
        narration="Alice留在废弃车站；与此同时，Bob进入钟楼地下室。",
        actions=[
            {"user_id": "alice", "text": "留在月台观察"},
            {"user_id": "bob", "text": "进入地下室"},
        ],
        current_scene="废弃车站",
        players={
            "alice": {"character_name": "Alice", "private_log": "不可发送"},
            "bob": {"character_name": "Bob"},
        },
        global_prompt="公开画面",
    )

    assert [panel["location"] for panel in panels] == ["废弃车站", "钟楼地下室"]
    assert panels[0]["participants"] == ["alice"]
    assert panels[1]["participants"] == ["bob"]
    assert compressed == 0
    assert "不可发送" not in llm.calls[0][1]


@pytest.mark.asyncio
async def test_ai_uncertain_result_stays_single_scene() -> None:
    llm = _PanelLLM(
        '{"panels":[{"participants":[],"location":"车站大厅",'
        '"description":"队伍在大厅调查"}]}'
    )
    panels, compressed = await infer_scene_panels(
        llm,
        narration="队伍在大厅分别查看门窗和柜台。",
        actions=[],
        current_scene="车站大厅",
        players={"alice": {}, "bob": {}},
    )

    assert len(panels) == 1
    assert panels[0]["participants"] == ["alice", "bob"]
    assert compressed == 0


@pytest.mark.asyncio
async def test_ai_multi_panel_hallucination_without_location_evidence_is_rejected() -> None:
    llm = _PanelLLM(
        '{"panels":['
        '{"participants":["alice"],"location":"车站大厅","description":"查看门窗"},'
        '{"participants":["bob"],"location":"不存在的地下室","description":"检查祭坛"}'
        ']}'
    )
    panels, compressed = await infer_scene_panels(
        llm,
        narration="Alice 和 Bob 都在车站大厅，分别查看门窗和柜台。",
        actions=[],
        current_scene="车站大厅",
        players={"alice": {}, "bob": {}},
    )

    assert len(panels) == 1
    assert panels[0]["location"] == "车站大厅"
    assert compressed == 0


def test_public_character_appearance_is_scoped_and_prompt_is_panel_specific() -> None:
    players = {
        "alice": {
            "character_name": "艾琳",
            "character_sheet": {
                "race": "人类",
                "class": "调查员",
                "appearance": "黑色短发，戴圆框眼镜，穿深色风衣。",
                "private_log": "不要把这段秘密送给图片模型。",
            },
        },
        "bob": {
            "character_name": "布鲁",
            "character_sheet": {
                "race": "改造人",
                "class": "艺术家",
                "background": "白金色尖刺重甲，左臂是锯子。",
            },
        },
    }
    appearances = public_character_appearances(players)
    assert "黑色短发" in appearances["alice"]
    assert "秘密" not in appearances["alice"]
    assert "白金色尖刺重甲" in appearances["bob"]

    prompt, _ = build_storyboard_prompt([
        {"participants": ["alice"], "location": "车站", "description": "雨夜月台"},
        {"participants": ["bob"], "location": "地下室", "description": "石室祭坛"},
    ], character_appearances=appearances)
    first = prompt.index("黑色短发")
    second = prompt.index("白金色尖刺重甲")
    assert first < second
    assert prompt.index("Panel 1") < first < prompt.index("Panel 2")
    assert prompt.count("黑色短发") == 1


def test_dividers_are_deterministic_and_contrast_adaptive() -> None:
    source = io.BytesIO()
    Image.new("RGB", (400, 200), "white").save(source, format="PNG")
    result = Image.open(io.BytesIO(overlay_storyboard_dividers(source.getvalue(), 3)))
    assert result.getpixel((266, 10)) == (28, 31, 35)
    assert result.getpixel((100, 100)) == (255, 255, 255)
    assert result.getpixel((300, 100)) == (28, 31, 35)
    dark = io.BytesIO()
    Image.new("RGB", (400, 200), (20, 20, 20)).save(dark, format="PNG")
    dark_result = Image.open(io.BytesIO(overlay_storyboard_dividers(dark.getvalue(), 3)))
    assert dark_result.getpixel((266, 10)) == (238, 240, 244)


def test_six_panel_dividers_form_a_three_by_two_grid() -> None:
    source = io.BytesIO()
    Image.new("RGB", (600, 400), "white").save(source, format="PNG")
    result = Image.open(io.BytesIO(overlay_storyboard_dividers(source.getvalue(), 6)))
    assert result.getpixel((200, 40)) == (28, 31, 35)
    assert result.getpixel((400, 40)) == (28, 31, 35)
    assert result.getpixel((40, 200)) == (28, 31, 35)
    assert result.getpixel((100, 100)) == (255, 255, 255)
