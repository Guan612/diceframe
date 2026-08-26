from __future__ import annotations

from dataclasses import dataclass

from src.engine.game_instance import GameInstance
from src.rulesets.dnd2024.combat import Dnd2024CombatEngine
from src.rulesets.dnd2024.play import EncounterAccess
from src.rulesets.dnd2024.runtime import Dnd2024Runtime


@dataclass
class SequenceRng:
    values: list[int]

    def randint(self, minimum: int, maximum: int) -> int:
        value = self.values.pop(0) if self.values else minimum
        assert minimum <= value <= maximum
        return value


def _character(runtime: Dnd2024Runtime, preset_id: str, name: str) -> dict:
    choices = runtime.builder_choices(None, {"locale": "en"})
    preset = next(item for item in choices["quick_presets"] if item["id"] == preset_id)
    return runtime.finalize_character(
        None, {**preset["draft"], "locale": "en", "name": name},
    )


def _instance(*, wizard: bool = False) -> tuple[Dnd2024CombatEngine, GameInstance]:
    return _preset_instance("curious_arcanist" if wizard else "stalwart_guardian")


def _preset_instance(preset_id: str) -> tuple[Dnd2024CombatEngine, GameInstance]:
    runtime = Dnd2024Runtime()
    instance = GameInstance(
        game_key=("test", "dnd2024-combat", "bot"),
        rule_id="dnd2024_srd", gm_uid="gm", language="en",
    )
    first = _character(runtime, preset_id, "Arden")
    instance.players["gm"] = {"character_name": "Arden", "character_sheet": first}
    assert instance.bind_ruleset_runtime(first["rule_binding"])
    return Dnd2024CombatEngine(
        runtime.load_bundle("en"), EncounterAccess.sandbox(),
    ), instance


def _goblin(*, position: int = 5) -> dict:
    return {
        "id": "goblin-1", "name": "Goblin", "hp": 18, "armor_class": 12,
        "speed": 30, "position": position, "initiative_modifier": 2,
        "abilities": {"str": 8, "dex": 14, "con": 10, "int": 10, "wis": 8, "cha": 8},
        "saving_throws": {"dex": 2, "wis": -1, "con": 0},
        "attacks": [{
            "id": "scimitar", "name": "Scimitar", "attack_bonus": 4,
            "damage": "1d6+2", "damage_type": "slashing", "range": 5,
        }],
    }


def _start(engine: Dnd2024CombatEngine, instance: GameInstance, *, position: int = 5) -> dict:
    intent = {
        "intent_id": "start-1", "type": "combat.start", "expected_version": 0,
        "submitted_by": "gm", "enemies": [_goblin(position=position)],
    }
    resolved = engine.resolve_intent(instance, intent, SequenceRng([20, 1]))
    assert resolved["ok"] is True
    applied = engine.apply_batch(instance, resolved["event_batch"])
    assert applied["applied"] is True
    assert instance.ruleset_state["combat"]["initiative"][0] == "player:gm"
    return resolved["event_batch"]


def test_weapon_attack_is_server_rolled_atomic_and_idempotent() -> None:
    engine, instance = _instance()
    _start(engine, instance)
    intent = {
        "intent_id": "attack-1", "type": "attack", "expected_version": 1,
        "submitted_by": "gm", "actor_id": "player:gm", "target_id": "enemy:goblin-1",
        "weapon_ref": "item:greatsword",
    }

    resolved = engine.resolve_intent(instance, intent, SequenceRng([15, 4, 5]))
    applied = engine.apply_batch(instance, resolved["event_batch"])
    hp_after = instance.ruleset_state["combat"]["enemies"]["goblin-1"]["hp"]
    replayed = engine.apply_batch(instance, resolved["event_batch"])

    assert applied["state_version"] == 2
    assert hp_after == 6
    assert replayed["duplicate"] is True
    assert instance.ruleset_state["combat"]["enemies"]["goblin-1"]["hp"] == hp_after
    assert instance.ruleset_state["combat"]["economy"]["action"] == 0


def test_catalog_preset_replaces_client_enemy_payload() -> None:
    engine, instance = _instance()
    intent = {
        "intent_id": "catalog-start", "type": "combat.start", "expected_version": 0,
        "submitted_by": "gm", "encounter_preset_id": "goblin_patrol",
        "enemies": [{"id": "forged", "hp": 9999, "armor_class": 1, "attacks": []}],
    }
    resolved = engine.resolve_intent(instance, intent, SequenceRng([20, 1]))
    assert resolved["ok"] is True
    started = next(
        event for event in resolved["event_batch"]["events"]
        if event["type"] == "dnd2024.combat.started"
    )
    assert set(started["enemies"]) == {"goblin-warrior-1"}
    assert started["enemies"]["goblin-warrior-1"]["hp"] == 10


def test_prepared_spell_consumes_slot_and_cannot_trust_client_damage() -> None:
    engine, instance = _instance(wizard=True)
    _start(engine, instance, position=30)
    intent = {
        "intent_id": "spell-1", "type": "cast_spell", "expected_version": 1,
        "submitted_by": "gm", "actor_id": "player:gm", "target_id": "enemy:goblin-1",
        "spell_ref": "spell:magic_missile", "slot_level": 1, "damage": 9999,
    }

    resolved = engine.resolve_intent(instance, intent, SequenceRng([1, 2, 3]))
    engine.apply_batch(instance, resolved["event_batch"])

    canonical = instance.get_character_sheet("gm")["ruleset_character"]
    assert canonical["spellcasting"]["class"]["slots_current"] == {"1": 1}
    assert instance.ruleset_state["combat"]["enemies"]["goblin-1"]["hp"] == 9
    assert any(
        event["type"] == "dnd2024.spell.cast"
        for event in resolved["event_batch"]["events"]
    )


def test_move_out_of_reach_creates_a_pending_reaction_decision() -> None:
    engine, instance = _instance()
    _start(engine, instance)
    intent = {
        "intent_id": "move-1", "type": "move", "expected_version": 1,
        "submitted_by": "gm", "actor_id": "player:gm", "distance": -10,
    }

    resolved = engine.resolve_intent(instance, intent, SequenceRng([]))
    engine.apply_batch(instance, resolved["event_batch"])

    assert resolved["pending_decision"]["kind"] == "opportunity_attack"
    assert instance.ruleset_state["combat"]["positions"]["player:gm"] == 0
    assert instance.ruleset_state["combat"]["pending_decisions"][0]["movement"]["distance"] == -10

    decision_intent = {
        "intent_id": "decision-1", "type": "decision.resolve", "expected_version": 2,
        "submitted_by": "gm", "decision_id": "decision:move-1", "option": "resolve",
    }
    decided = engine.resolve_intent(instance, decision_intent, SequenceRng([15, 4]))
    engine.apply_batch(instance, decided["event_batch"])

    assert instance.ruleset_state["combat"]["positions"]["player:gm"] == -10
    assert instance.ruleset_state["combat"]["pending_decisions"] == []
    assert instance.ruleset_state["combat"]["reactions"]["enemy:goblin-1"] == 0
    assert instance.get_character_sheet("gm")["ruleset_character"]["resources"]["hp"] < 12


def test_natural_twenty_death_save_restores_one_hp() -> None:
    engine, instance = _instance()
    canonical = instance.get_character_sheet("gm")["ruleset_character"]
    canonical["resources"]["hp"] = 0
    canonical["conditions"] = {
        "unconscious": {"source": "zero_hp"},
        "death_saves": {"successes": 0, "failures": 1},
    }
    _start(engine, instance)
    intent = {
        "intent_id": "death-1", "type": "death_save", "expected_version": 1,
        "submitted_by": "gm", "actor_id": "player:gm",
    }

    resolved = engine.resolve_intent(instance, intent, SequenceRng([20]))
    engine.apply_batch(instance, resolved["event_batch"])

    updated = instance.get_character_sheet("gm")["ruleset_character"]
    assert updated["resources"]["hp"] == 1
    assert "unconscious" not in updated["conditions"]
    assert updated["conditions"]["death_saves"] == {"successes": 0, "failures": 0}


def test_spell_targets_respect_hostile_and_allied_relationships() -> None:
    engine, instance = _instance(wizard=True)
    _start(engine, instance, position=30)
    invalid = engine.validate_intent(instance, {
        "intent_id": "friendly-fire-1", "type": "cast_spell", "expected_version": 1,
        "submitted_by": "gm", "actor_id": "player:gm", "target_id": "player:gm",
        "spell_ref": "spell:magic_missile", "slot_level": 1,
    })

    assert invalid["ok"] is False
    assert "hostile" in invalid["error"]


def test_failed_save_applies_condition_but_successful_save_does_not() -> None:
    failed_engine, failed_instance = _instance(wizard=True)
    _start(failed_engine, failed_instance, position=30)
    failed = failed_engine.resolve_intent(failed_instance, {
        "intent_id": "sleep-fail", "type": "cast_spell", "expected_version": 1,
        "submitted_by": "gm", "actor_id": "player:gm",
        "target_id": "enemy:goblin-1", "spell_ref": "spell:sleep", "slot_level": 1,
    }, SequenceRng([1]))
    failed_engine.apply_batch(failed_instance, failed["event_batch"])

    success_engine, success_instance = _instance(wizard=True)
    _start(success_engine, success_instance, position=30)
    succeeded = success_engine.resolve_intent(success_instance, {
        "intent_id": "sleep-success", "type": "cast_spell", "expected_version": 1,
        "submitted_by": "gm", "actor_id": "player:gm",
        "target_id": "enemy:goblin-1", "spell_ref": "spell:sleep", "slot_level": 1,
    }, SequenceRng([20]))
    success_engine.apply_batch(success_instance, succeeded["event_batch"])

    assert "incapacitated" in failed_instance.ruleset_state["combat"]["enemies"]["goblin-1"]["conditions"]
    assert "incapacitated" not in success_instance.ruleset_state["combat"]["enemies"]["goblin-1"]["conditions"]


def test_failed_concentration_save_removes_owned_conditions() -> None:
    engine, instance = _preset_instance("kindly_bulwark")
    _start(engine, instance)
    cast = engine.resolve_intent(instance, {
        "intent_id": "bless-1", "type": "cast_spell", "expected_version": 1,
        "submitted_by": "gm", "actor_id": "player:gm", "target_id": "player:gm",
        "spell_ref": "spell:bless", "slot_level": 1,
    }, SequenceRng([]))
    engine.apply_batch(instance, cast["event_batch"])
    ended = engine.resolve_intent(instance, {
        "intent_id": "end-1", "type": "end_turn", "expected_version": 2,
        "submitted_by": "gm", "actor_id": "player:gm",
    }, SequenceRng([]))
    engine.apply_batch(instance, ended["event_batch"])
    attacked = engine.resolve_intent(instance, {
        "intent_id": "enemy-attack-1", "type": "attack", "expected_version": 3,
        "submitted_by": "gm", "actor_id": "enemy:goblin-1", "target_id": "player:gm",
        "attack_id": "scimitar",
    }, SequenceRng([20, 4, 4, 1]))
    engine.apply_batch(instance, attacked["event_batch"])

    canonical = instance.get_character_sheet("gm")["ruleset_character"]
    assert canonical["spellcasting"]["class"]["concentration"] is None
    assert "blessed" not in canonical["conditions"]


def test_only_one_slot_spell_can_be_cast_on_a_turn() -> None:
    engine, instance = _preset_instance("kindly_bulwark")
    canonical = instance.get_character_sheet("gm")["ruleset_character"]
    canonical["resources"]["hp"] -= 1
    canonical["spellcasting"]["class"]["prepared_spell_refs"].append("spell:healing_word")
    _start(engine, instance, position=30)
    healed = engine.resolve_intent(instance, {
        "intent_id": "healing-word-1", "type": "cast_spell", "expected_version": 1,
        "submitted_by": "gm", "actor_id": "player:gm", "target_id": "player:gm",
        "spell_ref": "spell:healing_word", "slot_level": 1,
    }, SequenceRng([2, 2]))
    engine.apply_batch(instance, healed["event_batch"])
    second = engine.validate_intent(instance, {
        "intent_id": "guiding-bolt-1", "type": "cast_spell", "expected_version": 2,
        "submitted_by": "gm", "actor_id": "player:gm", "target_id": "enemy:goblin-1",
        "spell_ref": "spell:guiding_bolt", "slot_level": 1,
    })

    assert second["ok"] is False
    assert "only one spell slot" in second["error"]


def test_normal_healing_cannot_revive_a_dead_character() -> None:
    engine, instance = _preset_instance("kindly_bulwark")
    caster = instance.get_character_sheet("gm")["ruleset_character"]
    caster["spellcasting"]["class"]["prepared_spell_refs"].append("spell:healing_word")
    fallen = _character(Dnd2024Runtime(), "stalwart_guardian", "Fallen Ally")
    fallen_canonical = fallen["ruleset_character"]
    fallen_canonical["resources"]["hp"] = 0
    fallen_canonical.setdefault("conditions", {})["dead"] = {"source": "test"}
    instance.players["ally"] = {
        "character_name": "Fallen Ally", "character_sheet": fallen,
    }
    started = engine.resolve_intent(instance, {
        "intent_id": "start-dead-target", "type": "combat.start", "expected_version": 0,
        "submitted_by": "gm", "enemies": [_goblin(position=30)],
    }, SequenceRng([1, 20, 1]))
    engine.apply_batch(instance, started["event_batch"])
    assert instance.ruleset_state["combat"]["initiative"][0] == "player:gm"

    result = engine.validate_intent(instance, {
        "intent_id": "healing-dead-1", "type": "cast_spell", "expected_version": 1,
        "submitted_by": "gm", "actor_id": "player:gm", "target_id": "player:ally",
        "spell_ref": "spell:healing_word", "slot_level": 1,
    })

    assert result["ok"] is False
    assert "resurrection" in result["error"]


def test_cantrip_scales_at_level_five_and_spell_can_end_combat() -> None:
    engine, instance = _instance(wizard=True)
    canonical = instance.get_character_sheet("gm")["ruleset_character"]
    canonical["build"]["level"] = 5
    _start(engine, instance, position=30)
    ray = engine.resolve_intent(instance, {
        "intent_id": "ray-1", "type": "cast_spell", "expected_version": 1,
        "submitted_by": "gm", "actor_id": "player:gm", "target_id": "enemy:goblin-1",
        "spell_ref": "spell:ray_of_frost", "slot_level": 0,
    }, SequenceRng([20, 1, 1, 1, 1]))
    damage_event = next(
        event for event in ray["event_batch"]["events"]
        if event["type"] == "resource.changed"
    )
    assert len(damage_event["rolls"]) == 4  # critical doubles the level-5 2d8 cantrip

    victory_engine, victory_instance = _instance(wizard=True)
    _start(victory_engine, victory_instance, position=30)
    victory_instance.ruleset_state["combat"]["enemies"]["goblin-1"]["hp"] = 3
    missile = victory_engine.resolve_intent(victory_instance, {
        "intent_id": "missile-win", "type": "cast_spell", "expected_version": 1,
        "submitted_by": "gm", "actor_id": "player:gm", "target_id": "enemy:goblin-1",
        "spell_ref": "spell:magic_missile", "slot_level": 1,
    }, SequenceRng([1, 1, 1]))
    victory_engine.apply_batch(victory_instance, missile["event_batch"])
    assert victory_instance.ruleset_state["combat"]["status"] == "ended"


def test_stable_actor_remains_unconscious_and_skips_death_save() -> None:
    engine, instance = _instance()
    canonical = instance.get_character_sheet("gm")["ruleset_character"]
    canonical["resources"]["hp"] = 0
    canonical["conditions"] = {
        "unconscious": {"source": "zero_hp"},
        "stable": {"duration": "until_healed"},
        "death_saves": {"successes": 3, "failures": 0},
    }
    _start(engine, instance)
    actions = engine.available_intents(instance, "gm")

    assert [action["type"] for action in actions] == ["end_turn"]
    assert "unconscious" in canonical["conditions"]


def test_enemy_turn_is_declared_by_server_and_returns_control_to_player() -> None:
    engine, instance = _instance()
    _start(engine, instance, position=5)
    ended = engine.resolve_intent(instance, {
        "intent_id": "player-end", "type": "end_turn", "expected_version": 1,
        "submitted_by": "gm", "actor_id": "player:gm",
    }, SequenceRng([]))
    engine.apply_batch(instance, ended["event_batch"])

    attack = engine.next_automatic_intent(instance)
    assert attack is not None
    assert attack["type"] == "attack"
    assert attack["actor_id"] == "enemy:goblin-1"
    assert attack["target_id"] == "player:gm"
    resolved = engine.resolve_intent(instance, attack, SequenceRng([15, 3]))
    engine.apply_batch(instance, resolved["event_batch"])
    assert instance.get_character_sheet("gm")["ruleset_character"]["resources"]["hp"] < 12

    finish = engine.next_automatic_intent(instance)
    assert finish is not None and finish["type"] == "end_turn"
    resolved_finish = engine.resolve_intent(instance, finish, SequenceRng([]))
    engine.apply_batch(instance, resolved_finish["event_batch"])
    assert instance.ruleset_state["combat"]["initiative"][
        instance.ruleset_state["combat"]["turn_index"]
    ] == "player:gm"


def test_llm_view_uses_canonical_state_and_resolved_event_batch() -> None:
    runtime = Dnd2024Runtime()
    engine, instance = _instance()
    instance.get_character_sheet("gm")["hp"] = 9999
    batch = _start(engine, instance)

    view = runtime.build_llm_view(instance)

    assert view["players"]["gm"]["character_sheet"]["hp"] == 12
    authority = view["ruleset_authority"]
    assert authority["runtime_id"] == "core:dnd2024"
    assert authority["latest_event_batch"]["batch_id"] == batch["batch_id"]
    assert "combat_enemies" not in view
