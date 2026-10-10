"""Reset/restart keep the game's identity and rebuild its run state.

Regression coverage for:

- restart/reset of an Adventure v2 game silently falling back to the v1 path
  (play_mode, content_binding refs and v2 progress were not carried/rebuilt);
- a failing v2 initialization on restart must leave the previous run current;
- the opening ``plot_update`` of a new game being dropped (no tracker yet);
- ``switch_world`` renaming the game, diverging World identities and
  bypassing the authoritative write gate.
"""

from __future__ import annotations

import asyncio

import pytest

from src.engine.modules import content_binding
from src.engine.world_state import world_facts
from src.llm.client import LLMResponse
from test_golden_e2e_54pr import (  # noqa: F401  (fixture re-export)
    ADVENTURE_ID,
    _complete_node,
    _created_golden,
    golden,
)
from webapi_harness import web_api  # noqa: F401


# ---- 1: restart/reset keep identity and re-initialize Adventure v2 ---------


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["restart_game", "reset_game"])
async def test_new_run_keeps_identity_and_reinitializes_v2_progress(golden, transition) -> None:
    created = await _created_golden(golden)
    game_key = created["game_key"]
    before = golden.instance(game_key)
    assert before.play_mode == "adventure"
    world_ref = content_binding.world_ref(before)
    book_refs = content_binding.book_refs(before)
    assert world_ref
    await _complete_node(golden, created, "gate")
    assert before.adventure_progress["completed_nodes"] == ["gate"]

    await getattr(golden.api, transition)(game_key)
    after = golden.instance(game_key)

    assert after is not before
    assert after.run_id != before.run_id
    assert after.play_mode == "adventure"
    assert after.adventure_binding["adventure_id"] == ADVENTURE_ID
    assert content_binding.world_ref(after) == world_ref
    assert content_binding.book_refs(after) == book_refs
    # Fresh v2 progress for the new run, plus the atomically materialized seed.
    assert after.adventure_progress["active_nodes"] == ["gate"]
    assert after.adventure_progress.get("completed_nodes", []) == []
    assert world_facts(after.world_state)["location:cellar.door"]["value"] == "locked"
    # Survives a save/load round trip.
    payload = after.to_dict()
    assert payload["play_mode"] == "adventure"
    assert payload["adventure_progress"]["active_nodes"] == ["gate"]


@pytest.mark.asyncio
async def test_failed_v2_initialization_keeps_previous_run_current(golden, monkeypatch) -> None:
    created = await _created_golden(golden)
    game_key = created["game_key"]
    before = golden.instance(game_key)
    await _complete_node(golden, created, "gate")
    progress = dict(before.adventure_progress)
    run_id = before.run_id

    def failing(_instance):
        raise RuntimeError("seed failure")

    monkeypatch.setattr(golden.api._handler._lifecycle, "_initialize_adventure_run", failing)
    with pytest.raises(RuntimeError, match="seed failure"):
        await golden.api.restart_game(game_key)

    current = golden.instance(game_key)
    assert current is before
    assert current.run_id == run_id
    assert current.adventure_progress == progress


# ---- 3: opening plot_update is applied for a brand-new game ----------------


@pytest.mark.asyncio
async def test_opening_plot_update_is_applied_to_new_game(web_api, monkeypatch) -> None:
    api, _lorebook, registry, llm, _worlds = web_api

    async def opening(*, system_prompt, user_message, **kwargs):
        return LLMResponse(
            content="你们在遗迹前醒来。\n---\nQUEST:调查遗迹:active\nSCENE:遗迹入口",
            narration="你们在遗迹前醒来。",
            state_update=None, memory_delta=None, info_asymmetry=None,
            plot_update=None, total_tokens=5, is_narration_only=False,
            provider_used="fake",
        )

    monkeypatch.setattr(llm, "call", opening)
    created = await api.create_game(
        "template_world", "Opening",
        players=[{"character_name": "Hero", "attributes": {"str": 10}}],
    )
    assert created["ok"] is True, created
    instance = registry.get(api._parse_key(created["game_key"]))

    assert instance.plot_tracker is not None
    assert [quest.title for quest in instance.plot_tracker.quests.values()] == ["调查遗迹"]
    recovered = await registry.load(instance.game_key)
    assert [quest.title for quest in recovered.plot_tracker.quests.values()] == ["调查遗迹"]


# ---- 5: switch_world keeps the title and one World identity ----------------


@pytest.mark.asyncio
async def test_switch_world_keeps_title_and_moves_world_ref(web_api) -> None:
    api, lorebook, registry, _llm, _worlds = web_api
    created = await api.create_game(
        "template_world", "我的跑团",
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
    )
    lorebook.create_world("custom_book_only", "只在世界书库里的世界", description="")

    result = await api.switch_world(created["game_key"], "custom_book_only")
    instance = registry.get(api._parse_key(created["game_key"]))

    assert result["ok"] is True
    assert result["world_display_name"] == "只在世界书库里的世界"
    assert instance.world_name == "我的跑团"
    assert result["world_name"] == "我的跑团"
    assert instance.world_id == "custom_book_only"
    assert content_binding.world_ref(instance)["id"] == "custom_book_only"
    assert content_binding.world_ref(instance)["source_id"] == "custom_book_only"
    assert instance.to_dict()["modules"]["content_binding"]["world_ref"]["id"] == "custom_book_only"


@pytest.mark.asyncio
async def test_switch_world_is_rejected_during_historical_rewrite(web_api) -> None:
    api, lorebook, registry, _llm, _worlds = web_api
    created = await api.create_game(
        "template_world", "我的跑团",
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
    )
    lorebook.create_world("custom_book_only", "只在世界书库里的世界", description="")
    instance = registry.get(api._parse_key(created["game_key"]))
    before = instance.to_dict()

    async with instance.historical_rewrite() as acquired:
        assert acquired is True
        # A different request task, as in production (the gate is task-reentrant).
        result = await asyncio.create_task(
            api.switch_world(created["game_key"], "custom_book_only"),
        )

    assert result["ok"] is False
    assert result["code"] == "REWRITE_IN_PROGRESS"
    assert instance.to_dict() == before
