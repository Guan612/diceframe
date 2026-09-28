"""Round safety migration, snapshot identity and reset contracts."""

from copy import deepcopy
from dataclasses import fields

import pytest

from src.engine.game_instance import GameInstance
from src.engine.module_state import ModuleStateError
from src.engine.modules import round_safety as module
from src.migrations.instance import (
    CURRENT_INSTANCE_SCHEMA_VERSION,
    _migrate_v31_to_v32,
    migrate_game_state_payload,
)

VALUES = {
    "round_start_snapshot": {"u1": {"hp": 10, "inventory": ["rope"]}},
    "round_entity_snapshot": {"npcs": {"guard": {"hp": 20}}, "opaque": [None, 1]},
    "death_save_outcomes": {"3": {"u1": {"roll": 12}}, "4": {"u1": {"roll": 20}}},
}


def new_instance(**kwargs):
    return GameInstance(game_key=("test", "round-safety", "bot"), **kwargs)


def populated_instance():
    instance = new_instance()
    for key, value in deepcopy(VALUES).items():
        setattr(instance, key, value)
    return instance


def test_migration_moves_fields_without_mutating_input_and_is_idempotent():
    original = {"instance_schema_version": 31, **deepcopy(VALUES), "opaque": {"items": [1]}}
    before = deepcopy(original)
    migrated = migrate_game_state_payload(original)
    assert original == before
    assert migrated["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    assert migrated["modules"][module.MODULE_NAME] == {"schema_version": 1, **VALUES}
    assert not VALUES.keys() & migrated.keys()
    assert migrate_game_state_payload(migrated) == migrated
    step = _migrate_v31_to_v32(deepcopy(original))
    assert _migrate_v31_to_v32(deepcopy(step)) == step
    migrated["modules"][module.MODULE_NAME]["round_start_snapshot"]["u1"]["hp"] = 1
    assert original == before


@pytest.mark.parametrize("slot", [{}, {"schema_version": 1, **VALUES}, {"schema_version": 99, "opaque": [1]}])
def test_existing_slot_wins(slot):
    original = {"instance_schema_version": 31, **VALUES, "modules": {module.MODULE_NAME: slot}}
    before = deepcopy(original)
    migrated = migrate_game_state_payload(original)
    assert migrated["modules"][module.MODULE_NAME] == slot
    assert not VALUES.keys() & migrated.keys()
    assert original == before


@pytest.mark.parametrize("key", list(VALUES))
@pytest.mark.parametrize("value", [None, [], "bad", 12, True])
def test_invalid_fields_default_in_migration_and_ensure(key, value):
    values = {**deepcopy(VALUES), key: value}
    raw = {"schema_version": 1, **values}
    assert module.ensure(raw) is raw
    assert raw == {"schema_version": 1, **values, key: {}}
    migrated = migrate_game_state_payload({"instance_schema_version": 31, **values})
    assert migrated["modules"][module.MODULE_NAME] == raw


@pytest.mark.parametrize("raw", [None, [], 12, "bad"])
def test_missing_or_malformed_slots_materialize_defaults(raw):
    instance = new_instance(modules={module.MODULE_NAME: raw})
    assert instance.modules[module.MODULE_NAME] == module.fresh()
    assert module.ensure(raw) == module.fresh()
    assert module.ensure({"schema_version": 1}) == module.fresh()
    migrated = migrate_game_state_payload({"instance_schema_version": 31, "modules": raw})
    assert migrated["modules"][module.MODULE_NAME] == module.fresh()


def test_valid_dict_contents_are_not_validated_or_filtered():
    raw = {"schema_version": 1, **{key: {"opaque": [None, 4, "bad"]} for key in VALUES}}
    objects = dict(raw)
    assert module.ensure(raw) is raw
    assert all(raw[key] is value for key, value in objects.items())
    restored = GameInstance.from_dict({
        "game_key": ["test", "round-safety", "bot"], "state": "waiting",
        "instance_schema_version": 31, **{key: raw[key] for key in VALUES},
    })
    assert restored.modules[module.MODULE_NAME] == raw


def test_future_instance_version_is_rejected():
    with pytest.raises(ValueError, match="unsupported game instance schema"):
        GameInstance.from_dict({"instance_schema_version": CURRENT_INSTANCE_SCHEMA_VERSION + 1})


def test_unknown_module_version_is_preserved_and_access_fails_closed():
    raw = {"schema_version": 99, "opaque": [1]}
    assert module.ensure(raw) is raw
    instance = new_instance(modules={module.MODULE_NAME: raw})
    before = deepcopy(instance.modules)
    for key, value in VALUES.items():
        with pytest.raises(ModuleStateError):
            getattr(instance, key)
        with pytest.raises(ModuleStateError):
            setattr(instance, key, value)
    assert instance.modules == before
    encoded = instance.to_dict()
    assert encoded["modules"][module.MODULE_NAME] == raw
    assert GameInstance.from_dict(encoded).modules[module.MODULE_NAME] == raw


def test_properties_use_live_slot_and_roundtrip_has_one_storage_owner():
    instance = populated_instance()
    other = new_instance()
    slot = instance.modules[module.MODULE_NAME]
    assert slot is not other.modules[module.MODULE_NAME]
    assert not VALUES.keys() & {item.name for item in fields(instance)}
    assert not VALUES.keys() & vars(instance).keys()
    for key, value in deepcopy(VALUES).items():
        setattr(instance, key, value)
        assert slot[key] is value
        assert getattr(instance, key) is slot[key]
        assert getattr(instance, key) is not getattr(other, key)
    instance.round_start_snapshot["u1"]["inventory"].append("sword")
    encoded = instance.to_dict()
    assert not VALUES.keys() & encoded.keys()
    restored = GameInstance.from_dict(deepcopy(encoded))
    assert restored.modules[module.MODULE_NAME] == slot
    instance.replace_persisted_state_from(restored)
    assert instance.modules[module.MODULE_NAME] == slot


def test_capture_replaces_snapshots_without_copying():
    instance = populated_instance()
    players = {"u2": {"hp": 15}}
    entities = {"npcs": {"guard": {"hp": 10}}}
    module.capture_players(instance, players)
    module.replace_entity_snapshot(instance, entities)
    assert instance.round_start_snapshot is players
    assert instance.modules[module.MODULE_NAME]["round_start_snapshot"] is players
    assert instance.round_entity_snapshot is entities
    assert instance.modules[module.MODULE_NAME]["round_entity_snapshot"] is entities


def test_clear_snapshots_keeps_cache_and_preserves_snapshot_identity():
    instance = populated_instance()
    objects = {key: getattr(instance, key) for key in VALUES}
    module.clear_snapshots(instance)
    assert instance.round_start_snapshot == {}
    assert instance.round_entity_snapshot == {}
    assert instance.death_save_outcomes == VALUES["death_save_outcomes"]
    assert all(getattr(instance, key) is value for key, value in objects.items())


def test_discard_round_clears_all_three_in_original_order():
    instance = populated_instance()
    cleared = []

    class TracedDict(dict):
        def __init__(self, key, value):
            super().__init__(value)
            self.key = key

        def clear(self):
            cleared.append(self.key)
            super().clear()

    objects = {key: TracedDict(key, value) for key, value in VALUES.items()}
    for key, value in objects.items():
        setattr(instance, key, value)
    module.discard_round(instance)
    assert cleared == ["death_save_outcomes", "round_start_snapshot", "round_entity_snapshot"]
    assert instance.modules[module.MODULE_NAME] == module.fresh()
    assert all(getattr(instance, key) is value for key, value in objects.items())


@pytest.mark.parametrize("round_key", ["4", "5"])
def test_keep_death_saves_replaces_outer_dict_but_reuses_current_cache(round_key):
    instance = populated_instance()
    previous = instance.death_save_outcomes
    cache = previous.get(round_key, {})
    module.keep_death_saves_for(instance, round_key)
    assert instance.death_save_outcomes == {round_key: cache}
    assert instance.death_save_outcomes is not previous
    if round_key in previous:
        assert instance.death_save_outcomes[round_key] is previous[round_key]
    assert previous == VALUES["death_save_outcomes"]


def test_death_save_cache_returns_same_live_object_for_existing_and_new_rounds():
    instance = populated_instance()
    old = instance.death_save_outcomes["4"]
    assert module.death_save_cache(instance, "4") is old
    new = module.death_save_cache(instance, "5")
    assert new is module.death_save_cache(instance, "5")
    assert new is instance.death_save_outcomes["5"]
    new["u2"] = {"roll": 10}
    assert instance.modules[module.MODULE_NAME]["death_save_outcomes"]["5"]["u2"]["roll"] == 10


@pytest.mark.asyncio
async def test_reset_preserves_death_save_outcomes_implicitly():
    instance = populated_instance()
    cache = instance.death_save_outcomes
    await instance.reset()
    assert instance.modules[module.MODULE_NAME] == {**module.fresh(), "death_save_outcomes": cache}
    assert instance.death_save_outcomes is cache
    assert cache == VALUES["death_save_outcomes"]


def test_log_entry_snapshot_shape_stays_independent_of_instance_slot():
    instance = populated_instance()
    instance.log.append({"round": 3, "round_start_snapshot": {"u1": {"hp": 7}}})
    encoded = instance.to_dict()
    assert encoded["log"][0]["round_start_snapshot"] == {"u1": {"hp": 7}}
    restored = GameInstance.from_dict(deepcopy(encoded))
    assert restored.log == instance.log
    assert restored.round_start_snapshot == VALUES["round_start_snapshot"]
