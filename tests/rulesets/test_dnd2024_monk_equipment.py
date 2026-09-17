"""Martial Arts equipment eligibility, Monk Weapons, and the inactive profile.

Martial Arts is not a class-level-only benefit: it applies while the Monk wears
no armor, wields no Shield, and wields only Monk Weapons.  Every assertion here
goes through the real bundle, real item refs, and the same authoritative chain
the web layer uses (``available_intents`` -> ``validate_intent`` ->
``resolve_intent`` -> ``apply_batch``); the weapon refs are the project's own
catalog entries, never invented ones.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from src.engine.game_instance import GameInstance
from src.rulesets.dnd2024.combat import Dnd2024CombatEngine
from src.rulesets.dnd2024.features import (
    ClassFeatureError,
    Dnd2024ClassFeatureResolver,
)
from src.rulesets.dnd2024.features.combat import martial_arts_profile
from src.rulesets.dnd2024.runtime import Dnd2024Runtime

from dnd2024_monk_common import (
    SequenceRng,
    capability_actions,
    capability_intent,
    focus_state,
    monk_instance,
    monk_sheet,
    start_combat,
    with_equipment,
)

# 项目现有 catalog 里的真实武器 ref：
# - quarterstaff / sickle：Simple Melee（sickle 带 Light，伤害骰 1d4）
# - scimitar：带 Light 的 Martial Melee
# - longsword / flail：不带 Light 的 Martial Melee（明确不是 Monk Weapon）
# - shortbow：Ranged（不是近战武器）
MONK_WEAPONS = ("item:quarterstaff", "item:sickle", "item:scimitar", "item:shortsword")
NOT_MONK_WEAPONS = ("item:longsword", "item:flail", "item:shortbow")


def _resolver(runtime: Dnd2024Runtime) -> Dnd2024ClassFeatureResolver:
    return Dnd2024ClassFeatureResolver(runtime.load_bundle("en"))


def _canonical_with(refs) -> dict:
    runtime = Dnd2024Runtime()
    sheet = monk_sheet(runtime, level=2)
    return with_equipment(runtime, sheet, *refs)["ruleset_character"]


def _combat(level: int = 2, refs=(), **kwargs):
    runtime = Dnd2024Runtime()
    sheet = with_equipment(runtime, monk_sheet(runtime, level=level), *refs)
    engine, instance = monk_instance(runtime, sheet)
    start_combat(engine, instance, **kwargs)
    return engine, instance


def _attack_action(engine, instance, uid: str = "gm") -> dict:
    return next(
        item for item in engine.available_intents(instance, uid) if item["type"] == "attack"
    )


def _weapon(action: dict, weapon_ref: str) -> dict:
    return next(item for item in action["weapons"] if item["weapon_ref"] == weapon_ref)


def _equipped_weapons(engine, instance, uid: str = "gm") -> list[str]:
    return [
        item["weapon_ref"] for item in _attack_action(engine, instance, uid)["weapons"]
        if item["weapon_ref"] != "unarmed_strike"
    ]


def _apply(engine, instance, intent, rng):
    resolved = engine.resolve_intent(instance, intent, rng)
    assert resolved["ok"] is True, resolved
    applied = engine.apply_batch(instance, resolved["event_batch"])
    assert applied["applied"] is True
    return resolved, applied


# --------------------------------------------------------------------------
# Martial Arts eligibility
# --------------------------------------------------------------------------

@pytest.mark.parametrize("refs", [(), *[(ref,) for ref in MONK_WEAPONS]])
def test_martial_arts_is_active_without_armor_shield_or_an_illegal_weapon(refs) -> None:
    runtime = Dnd2024Runtime()
    resolver = _resolver(runtime)
    character = _canonical_with(refs)

    assert resolver.feature_is_active(
        character,
        next(item for item in resolver.features_for(character) if item.id == "martial_arts"),
    ) is True
    assert resolver.unarmed_strike_die(character) == "1d6"
    assert resolver.unarmed_ability_choice(character) == ("str", "dex")


@pytest.mark.parametrize(
    "refs",
    [
        ("item:chain_mail",),
        ("item:shield",),
        ("item:longsword",),
        ("item:flail",),
        ("item:shortbow",),
        ("item:quarterstaff", "item:longsword"),
        ("item:chain_mail", "item:quarterstaff"),
    ],
)
def test_martial_arts_is_inactive_when_the_equipment_disqualifies_it(refs) -> None:
    runtime = Dnd2024Runtime()
    resolver = _resolver(runtime)
    character = _canonical_with(refs)
    owned = {view.id: view for view in resolver.feature_views(character)}

    # 特性仍然被拥有，只是当前不生效：不再暴露武艺骰与属性选择。
    assert owned["martial_arts"].active is False
    assert dict(owned["martial_arts"].values) == {}
    assert resolver.has_feature(character, "martial_arts") is True
    assert resolver.unarmed_strike_die(character) == ""
    assert resolver.unarmed_ability_choice(character) == ()
    assert resolver.actor_projection(character)["martial_arts_weapon_refs"] == []


def test_monk_weapon_membership_comes_from_the_canonical_weapon_profiles() -> None:
    runtime = Dnd2024Runtime()
    equipment = _resolver(runtime).equipment

    assert [equipment.is_monk_weapon(ref) for ref in MONK_WEAPONS] == [True] * len(MONK_WEAPONS)
    assert [
        equipment.is_monk_weapon(ref) for ref in NOT_MONK_WEAPONS
    ] == [False] * len(NOT_MONK_WEAPONS)
    # 目录里没有的武器不会被猜成 Monk Weapon。
    assert equipment.is_monk_weapon("item:homebrew_blade") is False


# --------------------------------------------------------------------------
# Unarmed Strike with and without Martial Arts
# --------------------------------------------------------------------------

def test_unarmed_strike_uses_the_martial_arts_die_and_the_higher_ability() -> None:
    engine, instance = _combat()
    unarmed = _weapon(_attack_action(engine, instance), "unarmed_strike")

    assert unarmed["damage"] == "1d6"
    assert unarmed["martial_arts"] is True
    assert unarmed["ability_choice"] == ["str", "dex"]

    _apply(engine, instance, {
        "intent_id": "unarmed-1", "type": "attack",
        "expected_version": instance.ruleset_state["version"], "submitted_by": "gm",
        "actor_id": "player:gm", "target_id": "enemy:goblin-1",
        "weapon_ref": "unarmed_strike",
    }, SequenceRng([15, 4]))
    check = next(
        event for event in instance.event_ledger[-1]["events"]
        if event["type"] == "check.resolved"
    )

    # DEX 14 (+2) 高于 STR 12 (+1)：武艺取较高者，再加熟练加值 (+2)。
    assert check["modifier"] == 4


def test_unarmed_strike_falls_back_to_canonical_damage_without_martial_arts() -> None:
    engine, instance = _combat(refs=("item:longsword",))
    unarmed = _weapon(_attack_action(engine, instance), "unarmed_strike")

    assert unarmed["weapon_ref"] == "unarmed_strike"
    assert unarmed["damage"] == "1"
    assert "martial_arts" not in unarmed
    assert "ability_choice" not in unarmed

    _apply(engine, instance, {
        "intent_id": "unarmed-1", "type": "attack",
        "expected_version": instance.ruleset_state["version"], "submitted_by": "gm",
        "actor_id": "player:gm", "target_id": "enemy:goblin-1",
        "weapon_ref": "unarmed_strike",
    }, SequenceRng([15, 1]))
    damage = next(
        event for event in instance.event_ledger[-1]["events"]
        if event["type"] == "resource.changed"
    )

    # 普通徒手打击仍是 STR(+1) 的 1 点钝击，不使用武艺骰、也不取 DEX。
    assert damage["amount"] == 2
    assert damage["damage_type"] == "bludgeoning"


# --------------------------------------------------------------------------
# Monk Weapon: identity is preserved, the benefits are feature-derived
# --------------------------------------------------------------------------

def test_a_simple_monk_weapon_keeps_its_identity_and_gains_the_ability_choice() -> None:
    engine, instance = _combat(refs=("item:quarterstaff",))
    quarterstaff = _weapon(_attack_action(engine, instance), "item:quarterstaff")

    assert _equipped_weapons(engine, instance) == ["item:quarterstaff"]
    # canonical 身份 / 伤害类型 / 射程 / 熟练照旧，只有属性选择与伤害骰是特性投影。
    assert quarterstaff["name"] == "Quarterstaff"
    assert quarterstaff["damage_type"] == "bludgeoning"
    assert quarterstaff["range"] == 5
    assert quarterstaff["category"] == "simple"
    assert quarterstaff["ability_choice"] == ["str", "dex"]
    assert quarterstaff["damage"] == "1d6"

    _apply(engine, instance, {
        "intent_id": "quarterstaff-1", "type": "attack",
        "expected_version": instance.ruleset_state["version"], "submitted_by": "gm",
        "actor_id": "player:gm", "target_id": "enemy:goblin-1",
        "weapon_ref": "item:quarterstaff",
    }, SequenceRng([15, 3]))
    check = next(
        event for event in instance.event_ledger[-1]["events"]
        if event["type"] == "check.resolved"
    )

    assert check["modifier"] == 2 + 2  # DEX +2（武艺取高者） + 熟练 +2
    assert check["kind"] == "attack"


def test_the_martial_arts_die_replaces_a_weaker_monk_weapon_die() -> None:
    engine, instance = _combat(refs=("item:sickle",))
    sickle = _weapon(_attack_action(engine, instance), "item:sickle")

    # 镰刀自己的伤害骰是 1d4，武艺骰 1d6 更优：替换，但保留 weapon_ref 与伤害类型。
    assert sickle["weapon_ref"] == "item:sickle"
    assert sickle["damage"] == "1d6"
    assert sickle["damage_type"] == "slashing"
    assert sickle["martial_arts"] is True

    _apply(engine, instance, {
        "intent_id": "sickle-1", "type": "attack",
        "expected_version": instance.ruleset_state["version"], "submitted_by": "gm",
        "actor_id": "player:gm", "target_id": "enemy:goblin-1",
        "weapon_ref": "item:sickle",
    }, SequenceRng([15, 4]))
    damage = next(
        event for event in instance.event_ledger[-1]["events"]
        if event["type"] == "resource.changed"
    )

    assert damage["amount"] == 4 + 2  # 1d6 骰点 4 + DEX 修正 2


def test_a_light_martial_melee_weapon_is_a_monk_weapon() -> None:
    engine, instance = _combat(refs=("item:scimitar",))
    scimitar = _weapon(_attack_action(engine, instance), "item:scimitar")

    assert scimitar["weapon_ref"] == "item:scimitar"
    assert scimitar["category"] == "martial"
    assert scimitar["light"] is True
    assert scimitar["damage"] == "1d6"
    assert scimitar["damage_type"] == "slashing"
    assert scimitar["ability_choice"] == ["str", "dex"]


def test_a_non_monk_weapon_gets_no_martial_arts_treatment() -> None:
    engine, instance = _combat(refs=("item:longsword",))
    longsword = _weapon(_attack_action(engine, instance), "item:longsword")

    assert longsword["weapon_ref"] == "item:longsword"
    assert longsword["category"] == "martial"
    assert "light" not in longsword
    assert longsword["damage"] == "1d8"
    assert "martial_arts" not in longsword
    assert "ability_choice" not in longsword

    _apply(engine, instance, {
        "intent_id": "longsword-1", "type": "attack",
        "expected_version": instance.ruleset_state["version"], "submitted_by": "gm",
        "actor_id": "player:gm", "target_id": "enemy:goblin-1",
        "weapon_ref": "item:longsword",
    }, SequenceRng([15, 3]))
    check = next(
        event for event in instance.event_ledger[-1]["events"]
        if event["type"] == "check.resolved"
    )

    # 没有武艺就没有 STR/DEX 选择：仍然是近战默认的 STR(+1)。
    assert check["modifier"] == 1


def test_the_automation_never_downgrades_a_weapon_damage_die() -> None:
    """V1 的确定性替换规则：只在武艺骰更优时替换，绝不主动降级。"""

    stronger = martial_arts_profile(
        {"damage": "1d8"}, damage_die="1d6", ability_choice=("str", "dex"),
    )
    weaker = martial_arts_profile(
        {"damage": "1d4"}, damage_die="1d6", ability_choice=("str", "dex"),
    )
    uncomparable = martial_arts_profile(
        {"damage": "1d8+1d6"}, damage_die="1d12", ability_choice=("str", "dex"),
    )

    assert stronger["damage"] == "1d8"
    assert weaker["damage"] == "1d6"
    assert uncomparable["damage"] == "1d8+1d6"
    # 属性选择与武艺标记在两种情况下都由特性投影给出。
    assert stronger["ability_choice"] == ["str", "dex"]
    assert weaker["martial_arts"] is True


# --------------------------------------------------------------------------
# Bonus Unarmed Strike follows Martial Arts eligibility
# --------------------------------------------------------------------------

def test_bonus_unarmed_strike_is_exposed_only_while_martial_arts_is_active() -> None:
    engine, instance = _combat()
    active = {item["capability_id"] for item in capability_actions(engine, instance)}

    assert "bonus_unarmed_strike" in active

    engine, instance = _combat(refs=("item:chain_mail",))
    blocked = {item["capability_id"] for item in capability_actions(engine, instance)}

    assert "bonus_unarmed_strike" not in blocked
    result = engine.validate_intent(
        instance,
        capability_intent(engine, instance, "bonus_unarmed_strike", intent_id="forged"),
    )
    assert result["ok"] is False
    assert "not available to this actor" in result["error"]


# --------------------------------------------------------------------------
# Focus features are a different class feature: they survive Martial Arts
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "refs",
    [("item:chain_mail",), ("item:shield",), ("item:longsword",)],
)
def test_focus_capabilities_survive_an_inactive_martial_arts(refs) -> None:
    engine, instance = _combat(refs=refs)

    assert {item["capability_id"] for item in capability_actions(engine, instance)} == {
        "flurry_of_blows", "patient_defense", "patient_defense_focus",
        "step_of_the_wind", "step_of_the_wind_focus",
    }
    assert focus_state(instance)["current"] == 2


def test_flurry_still_works_and_falls_back_to_the_canonical_unarmed_profile() -> None:
    engine, instance = _combat(refs=("item:longsword",))

    resolved, _applied = _apply(
        engine, instance,
        capability_intent(engine, instance, "flurry_of_blows", intent_id="flurry-1"),
        # 普通徒手打击是固定 1 点伤害，不再掷骰：两次命中只需要两个 d20。
        SequenceRng([15, 15]),
    )
    events = resolved["event_batch"]["events"]
    checks = [event for event in events if event["type"] == "check.resolved"]
    damage = [event for event in events if event["type"] == "resource.changed"]
    focus_events = [
        event for event in events if event["type"] == "dnd2024.class_resource.spent"
    ]

    # 仍然扣 1 点专注 + 1 个附赠动作，仍然是两次 canonical 徒手打击。
    assert len(checks) == 2 and all(event["kind"] == "attack" for event in checks)
    assert [(event["resource_id"], event["amount"]) for event in focus_events] == [
        ("focus_points", 1),
    ]
    assert focus_state(instance)["current"] == 1
    assert instance.ruleset_state["combat"]["economy"]["bonus_action"] == 0
    # 底层档案回到普通徒手打击：1 点基础伤害 + STR 修正 1，而不是武艺骰。
    assert [event["amount"] for event in damage] == [2, 2]
    assert all(event["damage_type"] == "bludgeoning" for event in damage)


# --------------------------------------------------------------------------
# The live equipment path re-projects the feature state
# --------------------------------------------------------------------------

def test_equipping_armor_through_live_reconciliation_disables_martial_arts() -> None:
    runtime = Dnd2024Runtime()
    sheet = monk_sheet(runtime, level=2)
    instance = GameInstance(("web", "monk-equipment", "bot"))
    instance.language = "en"
    instance.players["gm"] = {"character_name": "Monk", "character_sheet": sheet}
    assert sheet["class_features"][0]["id"] == "martial_arts"
    assert sheet["class_features"][0]["active"] is True

    sheet["equipment"].append({
        "name": "Chain Mail", "item_ref": "item:chain_mail",
        "type": "armor", "slot": "body",
    })
    result = runtime.reconcile_character_state(instance, "gm", frozenset({"equipment"}))

    assert result is not None
    refreshed = instance.get_character_sheet("gm")
    martial_arts = next(
        feature for feature in refreshed["class_features"]
        if feature["id"] == "martial_arts"
    )
    # 用户可见投影跟着装备变：武艺不再生效，也不再展示武艺骰。
    assert martial_arts["active"] is False
    assert martial_arts["values"] == {}
    assert refreshed["ruleset_character"]["equipment"]["item_refs"] == ["item:chain_mail"]

    engine = Dnd2024CombatEngine(runtime.load_bundle("en"))
    actor = engine._player_view("gm", refreshed["ruleset_character"])

    assert actor["martial_arts_die"] == ""
    assert actor["martial_arts_weapon_refs"] == []
    assert engine._unarmed_strike(actor)["damage"] == "1"
    assert "bonus_unarmed_strike" not in {
        view.id for view in engine._available_class_capabilities(actor, {"bonus_action": 1})
    }


# --------------------------------------------------------------------------
# Malformed declarations fail closed
# --------------------------------------------------------------------------

def _unknown_weapon_kind(catalog: dict) -> None:
    catalog["classes"]["monk"]["features"][0]["equipment_requirement"]["weapon_kinds"] = [
        "greater_monk_weapon",
    ]


def _unknown_requirement_field(catalog: dict) -> None:
    catalog["classes"]["monk"]["features"][0]["equipment_requirement"]["unarmoured"] = True


def _non_boolean_flag(catalog: dict) -> None:
    catalog["classes"]["monk"]["features"][0]["equipment_requirement"]["unarmored"] = "yes"


@pytest.mark.parametrize(
    "mutate", [_unknown_weapon_kind, _unknown_requirement_field, _non_boolean_flag],
)
def test_malformed_equipment_requirements_fail_closed(mutate) -> None:
    runtime = Dnd2024Runtime()
    bundle = runtime.load_bundle("en")
    entities = deepcopy(bundle.entities)
    mutate(entities["class_feature_catalog"]["srd_class_features"])

    with pytest.raises(ClassFeatureError):
        Dnd2024ClassFeatureResolver(replace(bundle, entities=entities))
