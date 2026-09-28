"""Checks slot migration, identity, codec and reset contracts."""

from copy import deepcopy
from dataclasses import fields
from types import SimpleNamespace

import pytest

from src.engine.game_instance import GameInstance
from src.engine.module_state import ModuleStateError
from src.engine.modules import checks as module
from src.migrations.instance import (
    CURRENT_INSTANCE_SCHEMA_VERSION,
    _migrate_v30_to_v31,
    migrate_game_state_payload,
)

VALUES = {
    "last_check": {"check_id": "latest", "roll": 12},
    "last_checks": [{"check_id": "latest", "roll": 12}],
    "round_checks_prepared": True,
    "manual_roll_requests": [{"id": "manual", "status": "pending"}],
}


def new_instance(**kwargs):
    return GameInstance(game_key=("test", "checks", "bot"), **kwargs)


def test_migration_moves_fields_without_mutating_input_and_is_idempotent():
    original = {"instance_schema_version": 30, **deepcopy(VALUES), "opaque": {"items": [1]}}
    before = deepcopy(original)
    migrated = migrate_game_state_payload(original)
    assert original == before
    assert migrated["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    assert migrated["modules"][module.MODULE_NAME] == {"schema_version": 1, **VALUES}
    assert not VALUES.keys() & migrated.keys()
    assert migrate_game_state_payload(migrated) == migrated
    step = _migrate_v30_to_v31(deepcopy(original))
    assert _migrate_v30_to_v31(deepcopy(step)) == step
    migrated["modules"][module.MODULE_NAME]["last_check"]["roll"] = 20
    assert original == before


@pytest.mark.parametrize("slot", [{}, {"schema_version": 1, **VALUES}, {"schema_version": 99, "opaque": [1]}])
def test_existing_slot_wins(slot):
    original = {"instance_schema_version": 30, **VALUES, "modules": {module.MODULE_NAME: slot}}
    before = deepcopy(original)
    migrated = migrate_game_state_payload(original)
    assert migrated["modules"][module.MODULE_NAME] == slot
    assert not VALUES.keys() & migrated.keys()
    assert original == before


@pytest.mark.parametrize("key,value,expected", [
    ("last_check", [], None), ("last_check", "bad", None), ("last_check", None, None),
    ("last_checks", None, []), ("last_checks", {}, []),
    ("manual_roll_requests", None, []), ("manual_roll_requests", "bad", []),
    ("round_checks_prepared", "yes", True), ("round_checks_prepared", [], False),
    ("round_checks_prepared", 1, True), ("round_checks_prepared", None, False),
])
def test_invalid_fields_normalize_identically_in_migration_and_ensure(key, value, expected):
    values = {**deepcopy(VALUES), key: value}
    wanted = {"schema_version": 1, **values, key: expected}
    raw = {"schema_version": 1, **values}
    assert module.ensure(raw) is raw
    assert raw == wanted
    migrated = migrate_game_state_payload({"instance_schema_version": 30, **values})
    assert migrated["modules"][module.MODULE_NAME] == wanted


@pytest.mark.parametrize("raw", [None, [], 12, "bad"])
def test_missing_or_malformed_slot_materializes_defaults(raw):
    instance = new_instance(modules={module.MODULE_NAME: raw})
    assert instance.modules[module.MODULE_NAME] == module.fresh()
    assert module.ensure(raw) == module.fresh()
    assert module.ensure({"schema_version": 1}) == module.fresh()
    migrated = migrate_game_state_payload({"instance_schema_version": 30, "modules": raw})
    assert migrated["modules"][module.MODULE_NAME] == module.fresh()


def test_ensure_preserves_valid_objects_and_does_not_filter_list_elements():
    raw = {"schema_version": 1, **deepcopy(VALUES)}
    raw["last_checks"].extend([None, 4, "opaque"])
    raw["manual_roll_requests"].extend([None, "opaque"])
    objects = dict(raw)
    assert module.ensure(raw) is raw
    assert all(raw[key] is value for key, value in objects.items())
    instance = GameInstance.from_dict({"game_key": ["test", "checks", "bot"], "state": "waiting",
                                       "instance_schema_version": 30,
                                       **{key: raw[key] for key in VALUES}})
    assert instance.last_checks == raw["last_checks"]
    assert instance.manual_roll_requests == raw["manual_roll_requests"]


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
    restored = GameInstance.from_dict(encoded)
    assert restored.modules[module.MODULE_NAME] == raw


def test_properties_use_live_slot_and_roundtrip_has_one_storage_owner():
    instance = new_instance()
    other = new_instance()
    slot = instance.modules[module.MODULE_NAME]
    assert slot is not other.modules[module.MODULE_NAME]
    assert slot["last_checks"] is not other.last_checks
    assert slot["manual_roll_requests"] is not other.manual_roll_requests
    assert not VALUES.keys() & {item.name for item in fields(instance)}
    assert not VALUES.keys() & vars(instance).keys()
    for key, value in deepcopy(VALUES).items():
        setattr(instance, key, value)
        assert slot[key] is value
        assert getattr(instance, key) is slot[key]
    instance.last_checks.append({"check_id": "in-place"})
    instance.manual_roll_requests[0]["status"] = "cancelled"
    encoded = instance.to_dict()
    assert not VALUES.keys() & encoded.keys()
    restored = GameInstance.from_dict(deepcopy(encoded))
    assert restored.modules[module.MODULE_NAME] == slot
    instance.replace_persisted_state_from(restored)
    assert instance.modules[module.MODULE_NAME] == slot


@pytest.mark.parametrize("prepared", [False, True])
def test_clear_round_preserves_manual_rolls_and_list_identity(prepared):
    instance = new_instance()
    for key, value in deepcopy(VALUES).items():
        setattr(instance, key, value)
    requests, records = instance.manual_roll_requests, instance.last_checks
    module.clear_round(instance, prepared=prepared)
    assert instance.last_check is None
    assert instance.last_checks is records
    assert records == []
    assert instance.round_checks_prepared is prepared
    assert instance.manual_roll_requests is requests
    assert requests == VALUES["manual_roll_requests"]


@pytest.mark.asyncio
async def test_reset_preserves_manual_roll_requests_implicitly():
    instance = new_instance()
    for key, value in deepcopy(VALUES).items():
        setattr(instance, key, value)
    requests = instance.manual_roll_requests
    await instance.reset()
    assert instance.modules[module.MODULE_NAME] == {**module.fresh(), "manual_roll_requests": requests}
    assert instance.manual_roll_requests is requests
    assert requests == VALUES["manual_roll_requests"]


def test_record_sync_and_preparation_preserve_aliasing_contract():
    instance = new_instance()
    check = {"check_id": "record", "roll": 12}
    instance.record_check(check)
    assert instance.last_check is instance.last_checks[-1] is check
    instance.sync_last_check(check)
    assert instance.last_check == check
    assert instance.last_check is not check
    check["roll"] = 20
    assert instance.last_check["roll"] == 12
    instance.complete_round_check_preparation()
    assert instance.last_check is check
    assert instance.round_checks_prepared is True
    module.invalidate_prepared(instance)
    assert instance.round_checks_prepared is False


def test_mark_prepared_with_empty_list_preserves_last_check():
    instance = new_instance()
    instance.last_check = {"check_id": "previous"}
    previous = instance.last_check
    instance.complete_round_check_preparation()
    assert instance.last_check is previous
    assert instance.round_checks_prepared is True


def test_legacy_null_lists_keep_codec_defaults():
    instance = GameInstance.from_dict({
        "instance_schema_version": 30, "game_key": ["test", "checks", "bot"], "state": "waiting",
        "last_checks": None, "manual_roll_requests": None, "round_checks_prepared": "truthy",
    })
    assert instance.last_checks == []
    assert instance.manual_roll_requests == []
    assert instance.round_checks_prepared is True


def test_manual_roll_append_supports_attribute_based_test_doubles():
    instance = SimpleNamespace(modules={}, manual_roll_requests=[])
    request = {"id": "manual"}
    module.add_manual_roll_request(instance, request)
    assert instance.manual_roll_requests[-1] is request
    assert instance.modules == {}
