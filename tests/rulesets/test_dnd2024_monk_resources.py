"""Monk Focus Points on the existing canonical resource and rest lifecycle.

Focus is not a new resource table: it is ``resources.class.focus_points``,
created by ``Dnd2024RestEngine.sync_resources`` at the granting level, resized
by advancement, and recovered by the existing short/long rest engine.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from src.engine.game_instance import GameInstance
from src.rulesets.dnd2024.runtime import Dnd2024Runtime

from dnd2024_monk_common import (
    SequenceRng,
    advance,
    capability_intent,
    focus_state,
    monk_instance,
    monk_sheet,
    start_combat,
)


def _character(runtime: Dnd2024Runtime, level: int = 2) -> dict:
    return monk_sheet(runtime, level=level)["ruleset_character"]


def _consume_focus(instance: GameInstance, uid: str = "gm") -> None:
    sheet = deepcopy(instance.get_character_sheet(uid))
    sheet["ruleset_character"]["resources"]["class"]["focus_points"]["current"] -= 1
    instance.set_character_sheet(uid, sheet)


def test_creating_a_monk_initializes_focus_at_the_granting_level() -> None:
    runtime = Dnd2024Runtime()

    level_one = _character(runtime, 1)
    level_two = _character(runtime, 2)

    assert "focus_points" not in level_one["resources"]["class"]
    assert level_two["resources"]["class"]["focus_points"] == {
        "current": 2,
        "maximum": 2,
        "source_ref": "srd-5.2.1:p50:monks-focus",
    }


def test_focus_never_goes_below_zero() -> None:
    runtime = Dnd2024Runtime()
    engine, instance = monk_instance(runtime, monk_sheet(runtime, level=2))
    start_combat(engine, instance)

    # 2 点专注：先用疾风连击花掉 1 点，再用带专注的坚守防御花掉第 2 点。
    engine.apply_batch(instance, engine.resolve_intent(
        instance,
        capability_intent(engine, instance, "flurry_of_blows", intent_id="f-1"),
        SequenceRng([15, 4, 15, 4]),
    )["event_batch"])
    assert focus_state(instance)["current"] == 1
    instance.ruleset_state["combat"]["economy"]["bonus_action"] = 1
    engine.apply_batch(instance, engine.resolve_intent(
        instance,
        capability_intent(
            engine, instance, "patient_defense_focus", intent_id="pdf-1", target_id="",
        ),
        SequenceRng([]),
    )["event_batch"])
    assert focus_state(instance)["current"] == 0

    instance.ruleset_state["combat"]["economy"]["bonus_action"] = 1
    rejected = engine.validate_intent(
        instance, capability_intent(engine, instance, "flurry_of_blows", intent_id="f-2"),
    )

    assert rejected["ok"] is False
    assert "not enough Focus Points" in rejected["error"]
    assert focus_state(instance)["current"] == 0


def test_client_cannot_forge_focus() -> None:
    runtime = Dnd2024Runtime()
    engine, instance = monk_instance(runtime, monk_sheet(runtime, level=2))
    start_combat(engine, instance)

    resolved = engine.resolve_intent(instance, capability_intent(
        engine, instance, "flurry_of_blows", intent_id="f-1",
        focus_points=99, resource={"id": "focus_points", "amount": 0},
        costs=[{"kind": "resource", "name": "Focus Points", "amount": 0}],
    ), SequenceRng([15, 4, 15, 4]))
    engine.apply_batch(instance, resolved["event_batch"])

    # 伪造的 payload 字段对权威成本没有任何影响：仍然恰好扣 1 点。
    assert focus_state(instance) == {
        "current": 1, "maximum": 2, "source_ref": "srd-5.2.1:p50:monks-focus",
    }
    assert instance.ruleset_state["combat"]["economy"]["bonus_action"] == 0


def test_advancement_resizes_focus_without_refilling_a_legal_current() -> None:
    runtime = Dnd2024Runtime()
    sheet = monk_sheet(runtime, level=2)
    sheet["ruleset_character"]["resources"]["class"]["focus_points"]["current"] = 1

    advanced = advance(runtime, sheet, 3)
    focus = advanced["ruleset_character"]["resources"]["class"]["focus_points"]

    # 上限按职业表提高，合法 current 被保留（只补上限差值）。
    assert (focus["current"], focus["maximum"]) == (2, 3)


def test_advancement_clamps_a_current_above_the_new_maximum() -> None:
    runtime = Dnd2024Runtime()
    sheet = monk_sheet(runtime, level=2)
    sheet["ruleset_character"]["resources"]["class"]["focus_points"] = {
        "current": 99,
        "maximum": 99,
        "source_ref": "srd-5.2.1:p50:monks-focus",
    }

    advanced = advance(runtime, sheet, 3)
    focus = advanced["ruleset_character"]["resources"]["class"]["focus_points"]

    assert focus["maximum"] == 3
    assert 0 <= focus["current"] <= focus["maximum"]


def test_short_rest_restores_focus() -> None:
    runtime = Dnd2024Runtime()
    sheet = monk_sheet(runtime, level=2)
    sheet["ruleset_character"]["resources"]["class"]["focus_points"]["current"] = 0

    result = runtime.complete_rest(None, sheet, "short", {})
    focus = result["character"]["ruleset_character"]["resources"]["class"]["focus_points"]

    assert focus["current"] == 2
    assert any(
        event.get("type") == "restore_class_resource"
        and event.get("resource_id") == "focus_points"
        for event in result["events"]
    )
    # 短休摘要里就是既有的 resource delta，不需要 Monk 专用弹窗。
    assert result["character"]["class_resources"][0]["current"] == 2


def test_long_rest_restores_focus() -> None:
    runtime = Dnd2024Runtime()
    sheet = monk_sheet(runtime, level=2)
    sheet["ruleset_character"]["resources"]["class"]["focus_points"]["current"] = 0

    result = runtime.complete_rest(None, sheet, "long")
    focus = result["character"]["ruleset_character"]["resources"]["class"]["focus_points"]

    assert focus["current"] == 2
    assert result["character"]["class_resources"][0]["id"] == "focus_points"


def test_missing_focus_is_repaired_by_the_existing_rest_path() -> None:
    # 旧存档升级到支持版本后可能缺少 Focus：由既有 rest/sync 合法补齐。
    runtime = Dnd2024Runtime()
    sheet = monk_sheet(runtime, level=2)
    sheet["ruleset_character"]["resources"]["class"].pop("focus_points")

    result = runtime.complete_rest(None, sheet, "short", {})

    assert result["character"]["ruleset_character"]["resources"]["class"][
        "focus_points"
    ]["maximum"] == 2


def test_focus_survives_a_save_load_roundtrip() -> None:
    runtime = Dnd2024Runtime()
    engine, instance = monk_instance(runtime, monk_sheet(runtime, level=2))
    start_combat(engine, instance)
    engine.apply_batch(instance, engine.resolve_intent(
        instance,
        capability_intent(engine, instance, "flurry_of_blows", intent_id="f-1"),
        SequenceRng([15, 4, 15, 4]),
    )["event_batch"])
    assert focus_state(instance)["current"] == 1

    restored = GameInstance.from_dict(instance.to_dict())
    restored_sheet = restored.get_character_sheet("gm")

    assert restored_sheet["ruleset_character"]["resources"]["class"][
        "focus_points"
    ]["current"] == 1
    assert restored_sheet["class_resources"][0]["current"] == 1


def test_focus_heads_the_projected_class_resource_list() -> None:
    runtime = Dnd2024Runtime()
    sheet = monk_sheet(runtime, level=2)

    assert [(item["id"], item["name"], item["current"], item["maximum"]) for item in
            sheet["class_resources"]] == [("focus_points", "Focus Points", 2, 2)]
    # 1 级还没有专注点：投影里不出现 0/0 的空资源。
    assert monk_sheet(runtime, level=1)["class_resources"] == []


def test_combat_actor_view_exposes_focus_with_its_localized_name() -> None:
    runtime = Dnd2024Runtime()
    engine, instance = monk_instance(runtime, monk_sheet(runtime, level=2))
    start_combat(engine, instance)

    def focus_row() -> dict:
        actor = next(
            item for item in engine.gameplay_view(instance)["combat"]["actors"]
            if item["actor_id"] == "player:gm"
        )
        return next(
            entry for entry in actor["class_resources"] if entry["id"] == "focus_points"
        )

    assert (focus_row()["name"], focus_row()["current"], focus_row()["maximum"]) == (
        "Focus Points", 2, 2,
    )

    engine.apply_batch(instance, engine.resolve_intent(
        instance,
        capability_intent(engine, instance, "flurry_of_blows", intent_id="f-1"),
        SequenceRng([15, 4, 15, 4]),
    )["event_batch"])

    # §34：消费之后同一个战斗视图立刻反映 1/2，不需要重新加载页面。
    assert (focus_row()["current"], focus_row()["maximum"]) == (1, 2)


def test_localized_focus_label_reaches_the_projection() -> None:
    runtime = Dnd2024Runtime()
    sheet = monk_sheet(runtime, level=2, locale="zh-CN")
    feature_ids = [feature["id"] for feature in sheet["class_features"]]

    assert feature_ids == [
        "martial_arts", "monks_focus", "flurry_of_blows", "patient_defense",
        "step_of_the_wind",
    ]
    assert sheet["class_resources"][0]["name"] == "专注点"
    martial_arts = sheet["class_features"][0]
    assert martial_arts["name"] == "武艺"
    assert martial_arts["values"]["unarmed_damage_die"] == "1d6"


@pytest.mark.parametrize("rest", ["short", "long"])
def test_rest_rejects_a_monk_at_zero_hp(rest: str) -> None:
    runtime = Dnd2024Runtime()
    sheet = monk_sheet(runtime, level=2)
    sheet["ruleset_character"]["resources"]["hp"] = 0

    with pytest.raises(ValueError, match="at least 1 HP"):
        runtime.complete_rest(None, sheet, rest)
