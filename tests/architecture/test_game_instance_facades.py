"""Shrink-only baseline for callers that still reach module state via GameInstance.

R7-R9 moved runtime state into ``src/engine/modules`` slots, but GameInstance
kept a compatibility property for each moved field.  Callers that read or write
``instance.<field>`` still couple to the aggregate, so a change to a module is
not yet isolated from them.  This guard records the remaining facade usage per
file and property; it must only shrink.  When a PR moves callers onto the
module API, lower or delete the matching entries in the same PR, and delete a
property once nothing outside the aggregate uses it.

A facade is any GameInstance property whose body references a module imported
from ``src.engine.modules``, so new facades are covered automatically.
Attribute access on a name bound by an import (``table_settings.solo_mode``)
is a module call, not facade usage, and is ignored.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GAME_INSTANCE = "src/engine/game_instance.py"
MODULES_PACKAGE = "src.engine.modules"
MODULES_DIR = "src/engine/modules/"

# Module-backed properties currently on GameInstance. Do not raise.
MAX_MODULE_FACADES = 59

# Keys are source file + property name, so edits inside a caller do not make
# the baseline brittle. Do not add entries or raise counts.
FACADE_USAGE: dict[tuple[str, str], int] = {
    ("src/bots/bridge_core/service.py", "private_log"): 1,
    ("src/commands/ai_player.py", "round_number"): 1,
    ("src/commands/check_planner.py", "combat_enemies"): 2,
    ("src/commands/check_planner.py", "difficulty"): 2,
    ("src/commands/check_planner.py", "round_number"): 5,
    ("src/commands/check_planner.py", "scene"): 1,
    ("src/commands/check_planner.py", "total_tokens"): 1,
    ("src/commands/combat_resolver.py", "combat_enemies"): 2,
    ("src/commands/combat_resolver.py", "difficulty"): 1,
    ("src/commands/combat_resolver.py", "pending_combat_results"): 1,
    ("src/commands/combat_resolver.py", "round_number"): 3,
    ("src/commands/death_save_tracker.py", "round_number"): 3,
    ("src/commands/game_lifecycle.py", "bot_bind_token"): 1,
    ("src/commands/game_lifecycle.py", "difficulty"): 1,
    ("src/commands/game_lifecycle.py", "economy_reward_policy"): 1,
    ("src/commands/game_lifecycle.py", "entry_point"): 1,
    ("src/commands/game_lifecycle.py", "gm_style_override"): 1,
    ("src/commands/game_lifecycle.py", "luck_timeout_seconds"): 1,
    ("src/commands/game_lifecycle.py", "max_players"): 1,
    ("src/commands/game_lifecycle.py", "narrative_perspective"): 1,
    ("src/commands/game_lifecycle.py", "player_access_open"): 1,
    ("src/commands/game_lifecycle.py", "ruleset_runtime"): 2,
    ("src/commands/game_lifecycle.py", "scene"): 8,
    ("src/commands/game_lifecycle.py", "seed_code"): 1,
    ("src/commands/game_lifecycle.py", "solo_mode"): 1,
    ("src/commands/game_lifecycle.py", "total_tokens"): 1,
    ("src/commands/madness_tracker.py", "round_number"): 4,
    ("src/commands/npc_state_applier.py", "difficulty"): 1,
    ("src/commands/npc_state_applier.py", "round_number"): 1,
    ("src/commands/player_state_applier.py", "round_number"): 7,
    ("src/commands/prompt_composer.py", "difficulty"): 1,
    ("src/commands/protocol_repair.py", "total_tokens"): 1,
    ("src/commands/resource_triggers.py", "round_number"): 1,
    ("src/commands/round_actions.py", "gm_directives"): 1,
    ("src/commands/round_actions.py", "round_number"): 1,
    ("src/commands/round_effects.py", "combat_state"): 1,
    ("src/commands/round_effects.py", "round_number"): 7,
    ("src/commands/round_helpers.py", "entry_point"): 1,
    ("src/commands/round_llm.py", "round_number"): 16,
    ("src/commands/round_processor.py", "combat_enemies"): 1,
    ("src/commands/round_processor.py", "combat_state"): 2,
    ("src/commands/round_processor.py", "round_number"): 12,
    ("src/commands/round_processor.py", "ruleset_state"): 1,
    ("src/commands/round_processor.py", "scene_image"): 1,
    ("src/commands/round_processor.py", "total_tokens"): 1,
    ("src/commands/state_update_applier.py", "round_number"): 4,
    ("src/commands/swipe_generator.py", "round_number"): 2,
    ("src/engine/action_gate.py", "round_number"): 1,
    ("src/engine/checks.py", "combat_enemies"): 3,
    ("src/engine/checks.py", "combat_state"): 1,
    ("src/engine/checks.py", "difficulty"): 3,
    ("src/engine/checks.py", "ruleset_state"): 1,
    ("src/engine/game_context_projector.py", "combat_enemies"): 1,
    ("src/engine/game_context_projector.py", "combat_state"): 2,
    ("src/engine/game_context_projector.py", "difficulty"): 1,
    ("src/engine/game_context_projector.py", "game_time"): 1,
    ("src/engine/game_context_projector.py", "initiative_current"): 1,
    ("src/engine/game_context_projector.py", "initiative_order"): 1,
    ("src/engine/game_context_projector.py", "quick_actions"): 1,
    ("src/engine/game_context_projector.py", "round_number"): 1,
    ("src/engine/game_context_projector.py", "scene"): 1,
    ("src/engine/game_context_projector.py", "solo_mode"): 1,
    ("src/engine/instance_lifecycle.py", "confirmed_items"): 1,
    ("src/engine/instance_lifecycle.py", "game_time"): 1,
    ("src/engine/instance_lifecycle.py", "gm_directives"): 1,
    ("src/engine/instance_lifecycle.py", "gm_style_override"): 2,
    ("src/engine/instance_lifecycle.py", "health_events"): 1,
    ("src/engine/instance_lifecycle.py", "health_status"): 1,
    ("src/engine/instance_lifecycle.py", "key_facts"): 1,
    ("src/engine/instance_lifecycle.py", "last_state_update"): 1,
    ("src/engine/instance_lifecycle.py", "last_token_budget_bump"): 1,
    ("src/engine/instance_lifecycle.py", "lorebook_timed_state"): 1,
    ("src/engine/instance_lifecycle.py", "narrative_perspective"): 2,
    ("src/engine/instance_lifecycle.py", "pending_combat_results"): 1,
    ("src/engine/instance_lifecycle.py", "private_log"): 1,
    ("src/engine/instance_lifecycle.py", "quick_actions"): 1,
    ("src/engine/instance_lifecycle.py", "ruleset_runtime"): 1,
    ("src/engine/instance_lifecycle.py", "seed_code"): 3,
    ("src/engine/instance_lifecycle.py", "solo_mode"): 2,
    ("src/engine/instance_lifecycle.py", "summary"): 1,
    ("src/engine/instance_lifecycle.py", "table_talk"): 1,
    ("src/engine/plot_tracker.py", "round_number"): 2,
    ("src/engine/progression.py", "round_number"): 10,
    ("src/engine/round_recovery.py", "adventure_progress"): 1,
    ("src/engine/round_recovery.py", "round_entity_snapshot"): 2,
    ("src/engine/round_recovery.py", "round_number"): 9,
    ("src/engine/round_recovery.py", "round_start_snapshot"): 4,
    ("src/engine/round_snapshots.py", "adventure_progress"): 1,
    ("src/engine/round_snapshots.py", "combat_active"): 1,
    ("src/engine/round_snapshots.py", "combat_enemies"): 2,
    ("src/engine/round_snapshots.py", "combat_state"): 1,
    ("src/engine/round_snapshots.py", "initiative_current"): 1,
    ("src/engine/round_snapshots.py", "initiative_order"): 1,
    ("src/engine/round_snapshots.py", "round_entity_snapshot"): 1,
    ("src/engine/round_snapshots.py", "round_number"): 2,
    ("src/engine/turn_state.py", "max_players"): 1,
    ("src/engine/turn_state.py", "player_access_open"): 1,
    ("src/engine/turn_state.py", "round_number"): 3,
    ("src/engine/turn_state.py", "solo_mode"): 2,
    ("src/llm/client.py", "total_tokens"): 1,
    ("src/llm/context_builder.py", "combat_state"): 1,
    ("src/llm/context_builder.py", "confirmed_items"): 7,
    ("src/llm/context_builder.py", "difficulty"): 1,
    ("src/llm/context_builder.py", "game_time"): 1,
    ("src/llm/context_builder.py", "key_facts"): 3,
    ("src/llm/context_builder.py", "private_log"): 1,
    ("src/llm/context_builder.py", "round_number"): 1,
    ("src/llm/context_builder.py", "scene"): 1,
    ("src/llm/context_builder.py", "summary"): 2,
    ("src/memory/summarizer.py", "round_number"): 3,
    ("src/memory/summarizer.py", "summary"): 4,
    ("src/plugin_host/host.py", "started_at"): 3,
    ("src/rulesets/automation.py", "combat_active"): 1,
    ("src/rulesets/automation.py", "combat_state"): 1,
    ("src/rulesets/automation.py", "event_ledger"): 1,
    ("src/rulesets/automation.py", "initiative_current"): 1,
    ("src/rulesets/automation.py", "initiative_order"): 1,
    ("src/rulesets/automation.py", "ruleset_state"): 1,
    ("src/rulesets/dnd2024/advancement_access.py", "ruleset_state"): 4,
    ("src/rulesets/dnd2024/campaign/engine.py", "event_ledger"): 3,
    ("src/rulesets/dnd2024/campaign/engine.py", "ruleset_state"): 4,
    ("src/rulesets/dnd2024/combat/engine.py", "event_ledger"): 3,
    ("src/rulesets/dnd2024/combat/engine.py", "ruleset_state"): 4,
    ("src/rulesets/dnd2024/exploration/engine.py", "event_ledger"): 2,
    ("src/rulesets/dnd2024/exploration/engine.py", "ruleset_state"): 7,
    ("src/rulesets/dnd2024/features/models.py", "summary"): 1,
    ("src/rulesets/dnd2024/features/resolver.py", "summary"): 1,
    ("src/rulesets/dnd2024/runtime.py", "event_ledger"): 2,
    ("src/rulesets/dnd2024/runtime.py", "ruleset_state"): 5,
    ("src/webui/api.py", "economy_reward_policy"): 1,
    ("src/webui/routes/game_character_routes.py", "solo_mode"): 1,
    ("src/webui/routes/game_control_routes.py", "dice_reveal_mode"): 1,
    ("src/webui/routes/game_control_routes.py", "luck_timeout_seconds"): 1,
    ("src/webui/routes/game_control_routes.py", "private_log"): 1,
    ("src/webui/routes/game_control_routes.py", "table_talk"): 1,
    ("src/webui/routes/game_query_routes.py", "scene_image"): 1,
    ("src/webui/routes/manual_roll_routes.py", "manual_roll_requests"): 1,
    ("src/webui/routes/sse.py", "last_activity"): 1,
    ("src/webui/routes/sse.py", "private_log"): 2,
    ("src/webui/routes/sse.py", "round_number"): 9,
    ("src/webui/routes/sse.py", "scene"): 1,
    ("src/webui/routes/sse.py", "scene_image"): 1,
    ("src/webui/services/bot_access.py", "bot_bind_token"): 1,
    ("src/webui/services/characters.py", "round_number"): 2,
    ("src/webui/services/characters.py", "ruleset_runtime"): 1,
    ("src/webui/services/combat_extension.py", "round_number"): 1,
    ("src/webui/services/game_controls.py", "gm_style_override"): 1,
    ("src/webui/services/game_controls.py", "narrative_perspective"): 1,
    ("src/webui/services/game_controls.py", "player_access_open"): 1,
    ("src/webui/services/game_controls.py", "solo_mode"): 1,
    ("src/webui/services/game_lifecycle.py", "round_number"): 1,
    ("src/webui/services/game_lifecycle.py", "seed_code"): 3,
    ("src/webui/services/game_master.py", "round_number"): 2,
    ("src/webui/services/game_queries.py", "combat_active"): 1,
    ("src/webui/services/game_queries.py", "difficulty"): 1,
    ("src/webui/services/game_queries.py", "last_activity"): 2,
    ("src/webui/services/game_queries.py", "max_players"): 1,
    ("src/webui/services/game_queries.py", "private_log"): 1,
    ("src/webui/services/game_queries.py", "round_number"): 3,
    ("src/webui/services/game_queries.py", "ruleset_runtime"): 1,
    ("src/webui/services/game_queries.py", "scene"): 3,
    ("src/webui/services/game_queries.py", "seed_code"): 2,
    ("src/webui/services/game_queries.py", "solo_mode"): 2,
    ("src/webui/services/game_queries.py", "started_at"): 2,
    ("src/webui/services/game_queries.py", "table_talk"): 1,
    ("src/webui/services/game_queries.py", "total_llm_calls"): 2,
    ("src/webui/services/game_queries.py", "total_tokens"): 2,
    ("src/webui/services/game_seed_lifecycle.py", "difficulty"): 1,
    ("src/webui/services/game_seed_lifecycle.py", "round_number"): 1,
    ("src/webui/services/game_seed_lifecycle.py", "seed_code"): 1,
    ("src/webui/services/generated_images.py", "scene_image"): 1,
    ("src/webui/services/kp_questions.py", "round_number"): 2,
    ("src/webui/services/logs.py", "round_number"): 1,
    ("src/webui/services/logs.py", "total_llm_calls"): 1,
    ("src/webui/services/logs.py", "total_tokens"): 1,
    ("src/webui/services/manual_rolls.py", "manual_roll_requests"): 4,
    ("src/webui/services/manual_rolls.py", "round_number"): 1,
    ("src/webui/services/maps.py", "scene"): 1,
    ("src/webui/services/ruleset_characters.py", "ruleset_runtime"): 1,
    ("src/webui/services/ruleset_gameplay.py", "combat_active"): 2,
    ("src/webui/services/ruleset_gameplay.py", "combat_state"): 2,
    ("src/webui/services/ruleset_gameplay.py", "event_ledger"): 2,
    ("src/webui/services/ruleset_gameplay.py", "initiative_current"): 2,
    ("src/webui/services/ruleset_gameplay.py", "initiative_order"): 2,
    ("src/webui/services/ruleset_gameplay.py", "last_activity"): 2,
    ("src/webui/services/ruleset_gameplay.py", "round_number"): 2,
    ("src/webui/services/ruleset_gameplay.py", "ruleset_state"): 2,
    ("src/webui/services/ruleset_rest.py", "combat_active"): 1,
    ("src/webui/services/ruleset_rest.py", "combat_state"): 1,
    ("src/webui/services/ruleset_rest.py", "ruleset_state"): 1,
    ("src/webui/services/turns.py", "last_state_update"): 1,
    ("src/webui/services/turns.py", "quick_actions"): 1,
    ("src/webui/services/turns.py", "round_number"): 1,
    ("src/webui/services/turns.py", "ruleset_runtime"): 1,
    ("src/webui/services/turns.py", "ruleset_state"): 1,
    ("src/webui/services/turns.py", "solo_mode"): 1,
}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8-sig"))


def module_facades(root: Path) -> frozenset[str]:
    tree = _parse(root / GAME_INSTANCE)
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == MODULES_PACKAGE:
            modules.update(alias.asname or alias.name for alias in node.names)
    instance = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GameInstance"
    )
    return frozenset(
        node.name
        for node in instance.body
        if isinstance(node, ast.FunctionDef)
        and any(isinstance(item, ast.Name) and item.id == "property" for item in node.decorator_list)
        and any(isinstance(item, ast.Name) and item.id in modules for item in ast.walk(node))
    )


def _import_bound_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def scan_facade_usage(root: Path, facades: frozenset[str]) -> Counter[tuple[str, str]]:
    observed: Counter[tuple[str, str]] = Counter()
    source_root = root / "src"
    if not source_root.is_dir():
        return observed
    for path in sorted(source_root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative == GAME_INSTANCE or relative.startswith(MODULES_DIR):
            continue
        tree = _parse(path)
        imported = _import_bound_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or node.attr not in facades:
                continue
            if isinstance(node.value, ast.Name) and node.value.id in imported:
                continue
            observed[(relative, node.attr)] += 1
    return observed


def assert_facade_usage_matches(
    observed: Counter[tuple[str, str]],
    baseline: dict[tuple[str, str], int],
) -> None:
    unknown = sorted(set(observed) - set(baseline))
    assert not unknown, (
        f"new GameInstance facade usage, call the owning module instead: {unknown}"
    )
    increased = {
        key: (count, baseline[key])
        for key, count in observed.items()
        if count > baseline[key]
    }
    assert not increased, f"GameInstance facade usage increased: {increased}"
    shrunk = {
        key: (observed.get(key, 0), count)
        for key, count in baseline.items()
        if observed.get(key, 0) < count
    }
    assert not shrunk, f"facade usage shrank, lower FACADE_USAGE to match: {shrunk}"


def test_game_instance_facade_usage_matches_shrink_only_baseline() -> None:
    assert_facade_usage_matches(scan_facade_usage(ROOT, module_facades(ROOT)), FACADE_USAGE)


def test_module_facade_count_does_not_grow() -> None:
    count = len(module_facades(ROOT))
    assert count <= MAX_MODULE_FACADES, (
        f"GameInstance has {count} module-backed properties (maximum {MAX_MODULE_FACADES})"
    )


def test_new_facade_caller_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "src" / "webui" / "services" / "new_service.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "def read(instance):\n"
        "    return instance.economy\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="new GameInstance facade usage"):
        assert_facade_usage_matches(
            scan_facade_usage(tmp_path, frozenset({"economy"})), FACADE_USAGE,
        )


def test_module_attribute_access_is_not_facade_usage(tmp_path: Path) -> None:
    source = tmp_path / "src" / "webui" / "services" / "new_service.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from src.engine.modules import table_settings\n"
        "def read(instance):\n"
        "    return table_settings.solo_mode(instance)\n",
        encoding="utf-8",
    )
    assert not scan_facade_usage(tmp_path, frozenset({"solo_mode"}))


def test_removed_facade_caller_requires_baseline_update() -> None:
    observed = Counter(FACADE_USAGE)
    key = next(iter(FACADE_USAGE))
    observed.pop(key)
    with pytest.raises(AssertionError, match="lower FACADE_USAGE"):
        assert_facade_usage_matches(observed, FACADE_USAGE)
