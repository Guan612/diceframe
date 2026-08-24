from __future__ import annotations

import random

from src.engine.game_instance import GameInstance
from src.rulesets.dnd2024.runtime import Dnd2024Runtime


def _character(runtime: Dnd2024Runtime, preset_id: str, name: str) -> dict:
    choices = runtime.builder_choices(None, {"locale": "en"})
    preset = next(item for item in choices["quick_presets"] if item["id"] == preset_id)
    return runtime.finalize_character(
        None, {**preset["draft"], "locale": "en", "name": name},
    )


def _instance(*, multiplayer: bool = False) -> tuple[Dnd2024Runtime, GameInstance]:
    runtime = Dnd2024Runtime()
    instance = GameInstance(
        game_key=("test", "dnd2024-campaign", "bot"),
        rule_id="dnd2024_srd", gm_uid="gm", language="en",
    )
    gm = _character(runtime, "stalwart_guardian", "Arden")
    instance.players["gm"] = {"character_name": "Arden", "character_sheet": gm}
    if multiplayer:
        ally = _character(runtime, "curious_arcanist", "Mira")
        instance.players["ally"] = {"character_name": "Mira", "character_sheet": ally}
    assert instance.bind_ruleset_runtime(gm["rule_binding"])
    return runtime, instance


def _submit(
    runtime: Dnd2024Runtime, instance: GameInstance, intent_type: str,
    submitted_by: str = "gm", **fields,
) -> dict:
    version = int(instance.ruleset_state.get("version", 0) or 0)
    intent = {
        "intent_id": f"intent-{intent_type}-{version}",
        "type": intent_type,
        "expected_version": version,
        "submitted_by": submitted_by,
        **fields,
    }
    resolved = runtime.resolve_intent(instance, intent, random.Random(7))
    assert resolved["ok"] is True, resolved
    applied = runtime.apply_event_batch(instance, resolved["event_batch"])
    assert applied["applied"] is True
    return resolved


def _agreement(runtime: Dnd2024Runtime, instance: GameInstance) -> None:
    defaults = runtime.gameplay_view(instance, "gm", True)["campaign"][
        "session_zero_defaults"
    ]
    _submit(runtime, instance, "session_zero.propose", agreement=defaults)
    for uid in instance.players:
        _submit(runtime, instance, "session_zero.respond", uid, response="accept")
    _submit(runtime, instance, "session_zero.lock")


def test_session_zero_requires_every_player_and_revisions_reset_consent() -> None:
    runtime, instance = _instance(multiplayer=True)
    defaults = runtime.gameplay_view(instance, "gm", True)["campaign"][
        "session_zero_defaults"
    ]
    _submit(runtime, instance, "session_zero.propose", agreement=defaults)
    _submit(runtime, instance, "session_zero.respond", "gm", response="accept")

    denied = runtime.validate_intent(instance, {
        "intent_id": "lock-too-soon", "type": "session_zero.lock",
        "expected_version": 2, "submitted_by": "gm",
    })
    assert denied["ok"] is False
    assert "every player" in denied["error"]

    _submit(runtime, instance, "session_zero.respond", "ally", response="accept")
    changed = {**defaults, "tone": "Hopeful mystery"}
    _submit(runtime, instance, "session_zero.propose", agreement=changed)
    state = runtime.gameplay_view(instance, "gm", True)["campaign"]["session_zero"]
    assert state["revision"] == 2
    assert state["responses"] == {}
    for uid in instance.players:
        _submit(runtime, instance, "session_zero.respond", uid, response="accept")
    _submit(runtime, instance, "session_zero.lock")
    locked = runtime.gameplay_view(instance, "ally", False)["campaign"]["session_zero"]
    assert locked["status"] == "locked"
    assert locked["agreement"]["tone"] == "Hopeful mystery"


def test_solo_quick_start_uses_safe_defaults_and_enters_first_tutorial_step() -> None:
    runtime, instance = _instance()
    instance.solo_mode = True
    actions = runtime.available_intents(instance, "gm")

    assert "session_zero.quick_start" in {item["type"] for item in actions}
    _submit(runtime, instance, "session_zero.quick_start")

    campaign = runtime.gameplay_view(instance, "gm", True)["campaign"]
    assert campaign["session_zero"]["status"] == "locked"
    assert campaign["session_zero"]["agreement"]["difficulty"] == "standard"
    assert campaign["session_zero"]["agreement"]["pvp_policy"] == "consent"
    assert campaign["tutorial"]["status"] == "active"
    assert campaign["tutorial"]["current_step"] is not None
    assert "session_zero.quick_start" not in {
        item["type"] for item in runtime.available_intents(instance, "gm")
    }


def test_campaign_record_needs_explicit_confirmation_and_respects_gm_visibility() -> None:
    runtime, instance = _instance(multiplayer=True)
    _agreement(runtime, instance)
    proposed = _submit(
        runtime, instance, "campaign.propose", kind="fact",
        title="Hidden cause", summary="The bell was sabotaged.", visibility="gm",
    )
    proposal_id = next(
        event["proposal_id"] for event in proposed["event_batch"]["events"]
        if event["type"] == "dnd2024.campaign.proposal_created"
    )

    player_view = runtime.gameplay_view(instance, "ally", False)["campaign"]
    gm_view = runtime.gameplay_view(instance, "gm", True)["campaign"]
    assert player_view["proposals"] == []
    assert gm_view["proposals"][0]["status"] == "pending"
    assert player_view["entities"]["fact"] == []

    _submit(
        runtime, instance, "campaign.proposal.resolve",
        proposal_id=proposal_id, option="confirm",
    )
    gm_view = runtime.gameplay_view(instance, "gm", True)["campaign"]
    player_view = runtime.gameplay_view(instance, "ally", False)["campaign"]
    assert gm_view["entities"]["fact"][0]["title"] == "Hidden cause"
    assert player_view["entities"]["fact"] == []


def test_guided_adventure_runs_to_completion_with_combat_gate_and_summaries() -> None:
    runtime, instance = _instance()
    _agreement(runtime, instance)
    _submit(
        runtime, instance, "tutorial.start", adventure_id="lanterns_of_greymoor",
    )
    _submit(runtime, instance, "tutorial.choose", choice_id="inspect_cold_ash")
    _submit(runtime, instance, "tutorial.choose", choice_id="reassure_mira")
    _submit(runtime, instance, "tutorial.choose", choice_id="follow_small_tracks")

    blocked = runtime.validate_intent(instance, {
        "intent_id": "skip-combat", "type": "tutorial.choose",
        "expected_version": instance.ruleset_state["version"],
        "submitted_by": "gm", "choice_id": "secure_the_glade",
    })
    assert blocked["ok"] is False
    assert "objective" in blocked["error"]

    gameplay = runtime.gameplay_view(instance, "gm", True)
    preset = next(
        item for item in gameplay["encounter_presets"] if item["id"] == "first_skirmish"
    )
    _submit(runtime, instance, "combat.start", enemies=preset["enemies"])
    _submit(runtime, instance, "combat.end")
    _submit(runtime, instance, "tutorial.choose", choice_id="secure_the_glade")
    final = _submit(runtime, instance, "tutorial.choose", choice_id="share_the_truth")

    campaign = runtime.gameplay_view(instance, "gm", True)["campaign"]
    assert campaign["tutorial"]["status"] == "completed"
    assert len(campaign["chapter_summaries"]) == 3
    assert any(item["id"] == "fact:shrine_truth_shared" for item in campaign["entities"]["fact"])
    task = next(item for item in campaign["entities"]["task"] if item["id"] == "task:recover_way_lantern")
    assert task["status"] == "completed"
    assert sum(
        event["type"] == "dnd2024.chapter.summarized"
        for batch in instance.event_ledger for event in batch["events"]
    ) == 3
    assert any(
        event["type"] == "dnd2024.tutorial.completed"
        for event in final["event_batch"]["events"]
    )
    llm_view = runtime.build_llm_view(instance)
    assert llm_view["ruleset_authority"]["campaign"]["tutorial"]["status"] == "completed"


def test_campaign_intent_replay_is_idempotent() -> None:
    runtime, instance = _instance()
    defaults = runtime.gameplay_view(instance, "gm", True)["campaign"][
        "session_zero_defaults"
    ]
    intent = {
        "intent_id": "session-replay", "type": "session_zero.propose",
        "expected_version": 0, "submitted_by": "gm", "agreement": defaults,
    }
    resolved = runtime.resolve_intent(instance, intent, random.Random(1))
    runtime.apply_event_batch(instance, resolved["event_batch"])
    replay = runtime.resolve_intent(instance, intent, random.Random(2))
    reapplied = runtime.apply_event_batch(instance, replay["event_batch"])

    assert replay["replayed"] is True
    assert reapplied["duplicate"] is True
    assert instance.ruleset_state["version"] == 1
