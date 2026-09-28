"""Ruleset slot migration, live aliases and the existing unbound-save projection."""

from copy import deepcopy
from dataclasses import fields

import pytest

from src.engine.game_instance import GameInstance
from src.engine.module_state import ModuleStateError
from src.engine.modules import ruleset_runtime as module
from src.migrations.instance import (
    CURRENT_INSTANCE_SCHEMA_VERSION, _migrate_v33_to_v34, migrate_game_state_payload,
)

VALUES = {
    "ruleset_runtime": {"id": "core:dnd2024", "version": 1, "state_schema_version": 1},
    "ruleset_state": {"state_schema_version": 1, "version": 3, "combat": {"status": "active"}},
    "event_ledger": [{"batch_id": "battle-1", "events": [{"type": "opaque", "value": [1]}]}],
}
KEYS = {"ruleset_runtime": "binding", "ruleset_state": "state", "event_ledger": "event_ledger"}


def new_instance(**kwargs):
    return GameInstance(game_key=("test", "ruleset-runtime", "bot"), **kwargs)


def populated_instance():
    instance = new_instance()
    for key, value in deepcopy(VALUES).items():
        setattr(instance, key, value)
    return instance


def test_migration_moves_fields_without_mutating_input_and_is_idempotent():
    original = {"instance_schema_version": 33, **deepcopy(VALUES), "opaque": {"items": [1]}}
    before = deepcopy(original)
    migrated = migrate_game_state_payload(original)
    assert original == before
    assert migrated["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    assert migrated["modules"][module.MODULE_NAME] == {
        "schema_version": 1, **{KEYS[key]: value for key, value in VALUES.items()},
    }
    assert not VALUES.keys() & migrated.keys()
    assert migrate_game_state_payload(migrated) == migrated
    step = _migrate_v33_to_v34(deepcopy(original))
    assert _migrate_v33_to_v34(deepcopy(step)) == step
    migrated["modules"][module.MODULE_NAME]["event_ledger"][0]["events"].clear()
    assert original == before


@pytest.mark.parametrize("slot", [{}, {"schema_version": 1, "binding": {"id": "custom"}}, {"schema_version": 99, "opaque": [1]}])
def test_existing_slot_wins(slot):
    original = {"instance_schema_version": 33, **VALUES, "modules": {module.MODULE_NAME: slot}}
    before = deepcopy(original)
    migrated = migrate_game_state_payload(original)
    assert migrated["modules"][module.MODULE_NAME] == slot
    assert not VALUES.keys() & migrated.keys()
    assert original == before


@pytest.mark.parametrize("field,invalid", [
    ("ruleset_runtime", None), ("ruleset_runtime", [1]),
    ("ruleset_state", None), ("ruleset_state", "bad"),
    ("event_ledger", None), ("event_ledger", {}),
])
def test_invalid_types_repaired_identically_in_ensure_and_migration(field, invalid):
    values = {**deepcopy(VALUES), field: invalid}
    raw = {"schema_version": 1, **{KEYS[key]: value for key, value in values.items()}}
    assert module.ensure(raw) is raw
    assert raw[KEYS[field]] == ([] if field == "event_ledger" else {})
    migrated = migrate_game_state_payload({"instance_schema_version": 33, **values})
    assert migrated["modules"][module.MODULE_NAME] == raw


@pytest.mark.parametrize("raw", [None, [], 12, "bad"])
def test_missing_or_malformed_slots_materialize_defaults(raw):
    instance = new_instance(modules={module.MODULE_NAME: raw})
    assert instance.modules[module.MODULE_NAME] == module.fresh()
    assert module.ensure(raw) == module.fresh()
    assert module.ensure({"schema_version": 1}) == module.fresh()
    migrated = migrate_game_state_payload({"instance_schema_version": 33, "modules": raw})
    assert migrated["modules"][module.MODULE_NAME] == module.fresh()


def test_contents_remain_opaque_to_generic_engine():
    raw = {"schema_version": 1, "binding": {"custom": [1]},
           "state": {"state_schema_version": 999, "custom": [None]},
           "event_ledger": [None, 4, {"custom": [1]}], "extra": [2]}
    objects = dict(raw)
    assert module.ensure(raw) is raw
    assert all(raw[key] is value for key, value in objects.items())
    instance = new_instance(modules={module.MODULE_NAME: raw})
    assert GameInstance.from_dict(instance.to_dict()).modules[module.MODULE_NAME] == raw


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


def test_properties_use_live_slot_and_bound_roundtrip_has_one_storage_owner():
    instance = populated_instance()
    other = new_instance()
    slot = instance.modules[module.MODULE_NAME]
    assert slot is not other.modules[module.MODULE_NAME]
    assert not VALUES.keys() & {item.name for item in fields(instance)}
    assert not VALUES.keys() & vars(instance).keys()
    for field, value in deepcopy(VALUES).items():
        setattr(instance, field, value)
        assert slot[KEYS[field]] is value
        assert getattr(instance, field) is slot[KEYS[field]]
    assert instance.ruleset_runtime is not slot
    assert module.persisted_state(instance) is slot
    encoded = instance.to_dict()
    assert not VALUES.keys() & encoded.keys()
    restored = GameInstance.from_dict(deepcopy(encoded))
    assert restored.ruleset_state == instance.ruleset_state
    assert restored.event_ledger == instance.event_ledger
    assert restored.modules[module.MODULE_NAME] == slot
    instance.replace_persisted_state_from(restored)
    assert instance.modules[module.MODULE_NAME] == slot


def test_unbound_state_and_ledger_are_dropped_only_in_save_projection():
    instance = new_instance()
    instance.ruleset_state["rest_session"] = {"status": "collecting", "participants": {"hero": {}}}
    instance.event_ledger.append({"batch_id": "unbound", "events": [1]})
    state, ledger = instance.ruleset_state, instance.event_ledger
    before = deepcopy(instance.modules[module.MODULE_NAME])
    encoded = instance.to_dict()
    assert encoded["modules"][module.MODULE_NAME] == module.fresh()
    assert encoded["modules"][module.MODULE_NAME] is not instance.modules[module.MODULE_NAME]
    assert instance.modules[module.MODULE_NAME] == before
    assert instance.ruleset_state is state
    assert instance.event_ledger is ledger
    assert "rest_session" in state
    restored = GameInstance.from_dict(encoded)
    assert restored.ruleset_runtime == {}
    assert restored.ruleset_state == {}
    assert restored.event_ledger == []


def test_unbound_defaults_roundtrip():
    restored = GameInstance.from_dict(new_instance().to_dict())
    assert restored.modules[module.MODULE_NAME] == module.fresh()


def test_bind_initializes_only_empty_state_and_keeps_ledger():
    instance = new_instance()
    ledger = instance.event_ledger
    binding = {"runtime_id": "core:dnd2024", "runtime_version": 1,
               "content_version": "srd", "state_schema_version": 7}
    assert instance.bind_ruleset_runtime(binding) is True
    assert instance.ruleset_state == {"state_schema_version": 7}
    state = instance.ruleset_state
    assert instance.bind_ruleset_runtime(binding) is True
    assert instance.ruleset_state is state
    assert instance.event_ledger is ledger
    assert instance.bind_ruleset_runtime({**binding, "runtime_id": "other"}) is False


def test_copy_binding_for_new_run_copies_binding_rebuilds_state_and_keeps_ledger():
    source, candidate = populated_instance(), populated_instance()
    ledger = candidate.event_ledger
    module.copy_binding_for_new_run(candidate, source)
    assert candidate.ruleset_runtime == source.ruleset_runtime
    assert candidate.ruleset_runtime is not source.ruleset_runtime
    assert candidate.ruleset_state == {"state_schema_version": 1}
    assert candidate.event_ledger is ledger
    source.ruleset_runtime = {}
    module.copy_binding_for_new_run(candidate, source)
    assert candidate.ruleset_runtime == candidate.ruleset_state == {}


@pytest.mark.asyncio
async def test_reset_preserves_binding_deepcopy_and_clears_ledger_after_state_rebuild():
    instance = populated_instance()
    binding = instance.ruleset_runtime
    observations = []

    class Ledger(list):
        def clear(self):
            observations.append((deepcopy(instance.ruleset_runtime), deepcopy(instance.ruleset_state)))
            super().clear()

    ledger = Ledger(instance.event_ledger)
    instance.event_ledger = ledger
    await instance.reset()
    assert instance.ruleset_runtime == binding
    assert instance.ruleset_runtime is not binding
    assert observations == [(binding, {"state_schema_version": 1})]
    assert instance.event_ledger is ledger
    assert ledger == []


@pytest.mark.parametrize("engine_name", ["campaign", "combat", "exploration"])
def test_unbound_dnd_batches_keep_live_state_and_ledger_but_do_not_persist(engine_name):
    from src.rulesets.dnd2024.runtime import Dnd2024Runtime

    runtime, instance = Dnd2024Runtime(), new_instance()
    if engine_name == "campaign":
        engine = runtime._campaign_engine(instance, "en")
    elif engine_name == "combat":
        engine = runtime._combat_engine(instance, locale="en")
    else:
        engine = runtime._exploration_engine("en")
    batch = {
        "batch_id": "batch_unbound", "intent_id": "unbound", "expected_version": 0,
        "result_version": 1, "events": [{"type": "intent.submitted"}],
    }
    assert engine.apply_batch(instance, batch)["applied"] is True
    assert instance.ruleset_runtime == {}
    assert instance.event_ledger == [batch]
    before = deepcopy(instance.modules[module.MODULE_NAME])
    restored = GameInstance.from_dict(instance.to_dict())
    assert restored.modules[module.MODULE_NAME] == module.fresh()
    assert instance.modules[module.MODULE_NAME] == before


def test_transaction_restore_deepcopies_state_and_ledger_without_touching_binding():
    instance = populated_instance()
    binding = instance.ruleset_runtime
    snapshot = deepcopy(VALUES)
    module.restore_from_transaction(instance, snapshot)
    assert instance.ruleset_runtime is binding
    assert instance.ruleset_state == snapshot["ruleset_state"]
    assert instance.event_ledger == snapshot["event_ledger"]
    instance.ruleset_state["combat"]["status"] = "none"
    instance.event_ledger[0]["events"].clear()
    assert snapshot == VALUES
