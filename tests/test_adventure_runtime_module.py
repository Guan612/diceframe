"""Adventure runtime slot: migration, proxies, play-mode derivation and reset contracts."""

from copy import deepcopy
from dataclasses import fields

import pytest

from src.engine.game_instance import GameInstance
from src.engine.module_state import ModuleStateError
from src.engine.modules import adventure_runtime_state as module
from src.migrations.instance import (
    CURRENT_INSTANCE_SCHEMA_VERSION,
    _migrate_v38_to_v39,
    migrate_game_state_payload,
)
from tests.test_game_instance_reset_characterization import _make_populated_instance

KEY = ["test", "adventure-runtime", "bot"]
BINDING = {"adventure_id": "adv-1", "version": "1", "format": "v2", "world_id": "w"}
PROGRESS = {
    "active_nodes": ["vault"],
    "completed_nodes": ["gate"],
    "objectives": {"find_key": "done"},
    "history": [{"node": "gate", "opaque": [None, 1]}],
}
FIELDS = {"adventure_progress", "play_mode"}


def new_instance(**kwargs):
    return GameInstance(game_key=tuple(KEY), **kwargs)


def legacy_payload(**extra):
    return {
        "game_key": KEY, "state": "waiting", "instance_schema_version": 38,
        "adventure_binding": deepcopy(BINDING),
        "adventure_progress": deepcopy(PROGRESS), "play_mode": "adventure",
        **extra,
    }


# ---- migration -----------------------------------------------------------------


def test_migration_moves_fields_without_mutating_input_and_is_idempotent():
    original = legacy_payload(opaque={"items": [1]})
    before = deepcopy(original)
    migrated = migrate_game_state_payload(original)
    assert original == before
    assert migrated["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    assert migrated["modules"][module.MODULE_NAME] == {
        "schema_version": 1, "progress": PROGRESS, "play_mode": "adventure",
    }
    assert not FIELDS & migrated.keys()
    assert migrated["adventure_binding"] == BINDING
    assert migrate_game_state_payload(migrated) == migrated
    step = _migrate_v38_to_v39(deepcopy(original))
    assert _migrate_v38_to_v39(deepcopy(step)) == step
    migrated["modules"][module.MODULE_NAME]["progress"]["active_nodes"].append("x")
    assert original == before


@pytest.mark.parametrize("slot", [
    {}, {"schema_version": 1, "progress": {"active_nodes": ["a"]}, "play_mode": "free"},
    {"schema_version": 99, "opaque": [1]},
])
def test_existing_slot_wins(slot):
    original = legacy_payload(modules={module.MODULE_NAME: slot})
    before = deepcopy(original)
    migrated = migrate_game_state_payload(original)
    assert migrated["modules"][module.MODULE_NAME] == slot
    assert not FIELDS & migrated.keys()
    assert original == before


@pytest.mark.parametrize("value", [None, [], "corrupt", 12, True])
def test_invalid_progress_becomes_empty_in_migration_and_ensure(value):
    migrated = migrate_game_state_payload(legacy_payload(adventure_progress=value))
    assert migrated["modules"][module.MODULE_NAME]["progress"] == {}
    raw = {"schema_version": 1, "progress": value, "play_mode": "free"}
    assert module.ensure(raw) is raw
    assert raw["progress"] == {}


@pytest.mark.parametrize("stored,binding,expected", [
    ("free", BINDING, "free"),
    ("adventure", {}, "adventure"),
    ("Free", {}, "Free"),  # known modes are kept verbatim, as the decoder did
    ("", BINDING, "adventure"),
    ("", {}, "free"),
    (None, BINDING, "adventure"),
    ("story", {"adventure_id": ""}, "free"),
    (7, "not-a-dict", "free"),
])
def test_play_mode_derivation_matches_the_previous_decoder(stored, binding, expected):
    payload = legacy_payload(play_mode=stored, adventure_binding=binding)
    migrated = migrate_game_state_payload(payload)
    assert migrated["modules"][module.MODULE_NAME]["play_mode"] == expected
    assert GameInstance.from_dict(payload).play_mode == expected
    assert module.derive_play_mode(stored, binding) == expected


def test_save_without_play_mode_or_progress_derives_and_defaults():
    payload = legacy_payload()
    del payload["play_mode"], payload["adventure_progress"]
    restored = GameInstance.from_dict(payload)
    assert restored.play_mode == "adventure"
    assert restored.adventure_progress == {}


@pytest.mark.parametrize("bound", [True, False])
def test_empty_slot_mode_is_derived_on_every_load(bound):
    """A new run keeps play_mode empty in memory; loading still derives it."""
    instance = new_instance(adventure_binding=deepcopy(BINDING) if bound else {})
    assert instance.play_mode == ""
    encoded = instance.to_dict()
    assert encoded["modules"][module.MODULE_NAME]["play_mode"] == ""
    restored = GameInstance.from_dict(encoded)
    assert restored.play_mode == ("adventure" if bound else "free")


@pytest.mark.parametrize("raw", [None, [], 12, "bad"])
def test_missing_or_malformed_slots_materialize_defaults(raw):
    instance = new_instance(modules={module.MODULE_NAME: raw})
    assert instance.modules[module.MODULE_NAME] == module.fresh()
    assert module.ensure(raw) == module.fresh()
    assert module.ensure({"schema_version": 1}) == module.fresh()


def test_future_instance_version_is_rejected():
    with pytest.raises(ValueError, match="unsupported game instance schema"):
        GameInstance.from_dict({"instance_schema_version": CURRENT_INSTANCE_SCHEMA_VERSION + 1})


def test_unknown_module_version_is_preserved_and_access_fails_closed():
    raw = {"schema_version": 99, "opaque": [1], "play_mode": ""}
    instance = new_instance(modules={module.MODULE_NAME: raw})
    before = deepcopy(instance.modules)
    for key, value in (("adventure_progress", {"a": 1}), ("play_mode", "free")):
        with pytest.raises(ModuleStateError, match="unsupported adventure_runtime module schema"):
            getattr(instance, key)
        with pytest.raises(ModuleStateError, match="unsupported adventure_runtime module schema"):
            setattr(instance, key, value)
    assert instance.modules == before
    encoded = instance.to_dict()
    assert encoded["modules"][module.MODULE_NAME] == raw
    # Decoding never repairs or derives into an opaque slot.
    assert GameInstance.from_dict(encoded).modules[module.MODULE_NAME] == raw


# ---- proxies ---------------------------------------------------------------------


def test_properties_use_live_slot_and_roundtrip_has_one_storage_owner():
    instance = new_instance(adventure_binding=deepcopy(BINDING))
    other = new_instance()
    slot = instance.modules[module.MODULE_NAME]
    assert not FIELDS & {item.name for item in fields(instance)}
    assert not FIELDS & vars(instance).keys()
    progress = deepcopy(PROGRESS)
    instance.adventure_progress = progress
    instance.play_mode = "adventure"
    assert slot["progress"] is progress
    assert instance.adventure_progress is progress
    assert instance.adventure_progress is not other.adventure_progress
    assert slot["play_mode"] == "adventure"
    instance.adventure_progress["active_nodes"].append("crypt")
    encoded = instance.to_dict()
    assert not FIELDS & encoded.keys()
    restored = GameInstance.from_dict(deepcopy(encoded))
    assert restored.modules[module.MODULE_NAME] == slot
    assert restored.adventure_progress["active_nodes"] == ["vault", "crypt"]
    instance.replace_persisted_state_from(restored)
    assert instance.modules[module.MODULE_NAME] == slot


@pytest.mark.parametrize("value", [None, [], "bad"])
def test_progress_setter_stores_empty_progress_for_non_dicts(value):
    instance = new_instance()
    instance.adventure_progress = deepcopy(PROGRESS)
    instance.adventure_progress = value
    assert instance.adventure_progress == {}


@pytest.mark.parametrize("value", [None, 3, ["free"]])
def test_play_mode_setter_stores_empty_mode_for_non_strings(value):
    instance = new_instance()
    instance.play_mode = value
    assert instance.play_mode == ""


def test_owner_writes_reject_unknown_schema_before_mutation():
    instance = new_instance(modules={module.MODULE_NAME: {"schema_version": 99}})
    before = deepcopy(instance.modules)
    for write, value in ((module.replace_progress, {}), (module.replace_play_mode, "free")):
        with pytest.raises(ModuleStateError):
            write(instance, value)
    assert instance.modules == before


# ---- reset / new run ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_place_reset_keeps_progress_and_play_mode():
    instance = _make_populated_instance()
    instance.adventure_progress = deepcopy(PROGRESS)
    progress = instance.adventure_progress
    await instance.reset()
    assert instance.play_mode == "adventure"
    assert instance.adventure_progress is progress
    assert instance.adventure_progress == PROGRESS


@pytest.mark.asyncio
async def test_new_run_candidate_does_not_carry_progress_or_play_mode(tmp_path):
    """Current behaviour, kept verbatim: a reset/restart run starts empty."""
    from types import SimpleNamespace

    from src.commands.game_lifecycle import GameLifecycle

    source = _make_populated_instance()
    source.adventure_progress = deepcopy(PROGRESS)

    async def create_game(game_key, **kwargs):
        return GameInstance(game_key=game_key)

    lifecycle = object.__new__(GameLifecycle)
    lifecycle.create_game = create_game
    lifecycle.prompt = SimpleNamespace(ruleset_registry=None)
    candidate = await lifecycle._new_run_candidate(source, preserve_players=True)
    assert candidate.adventure_binding == source.adventure_binding
    assert candidate.adventure_progress == {}
    assert candidate.play_mode == ""
    assert source.adventure_progress == PROGRESS


# ---- API contract ------------------------------------------------------------------


@pytest.mark.parametrize("stored,bound,expected", [
    ("adventure", True, "adventure"), ("free", False, "free"), ("", False, "free"),
])
def test_game_detail_play_mode_contract_is_unchanged(tmp_path, stored, bound, expected):
    from src.engine.game_instance import GameRegistry
    from tests.test_game_list_order import _query_dependencies
    from src.webui.services.game_queries import game_detail

    registry = GameRegistry(tmp_path)
    instance = new_instance(adventure_binding=deepcopy(BINDING) if bound else {})
    instance.play_mode = stored
    registry.register(instance)
    detail = game_detail(_query_dependencies(registry), "|".join(KEY), viewer_is_gm=True)
    # An empty in-memory mode is still reported as "free", as before the slot.
    assert detail["play_mode"] == expected
    assert "adventure_progress" not in detail
