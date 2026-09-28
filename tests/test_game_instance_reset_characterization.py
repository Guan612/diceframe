"""reset() 契约 characterization tests（施工单 §11.1.2）。

目的不是定义"理想 reset"，而是**冻结开工基线的真实 reset contract**：

- 明确保留的字段继续保留；
- 明确清空的字段继续清空；
- ``rotate_run_identity`` 的 run_id / memory_namespace / economy 行为不变；
- 未被旧 reset() 触碰的字段（"隐式保留"）保持不变 —— 包括
  ``death_save_outcomes`` / ``last_overreach`` / ``rule_id`` 这类看起来
  "似乎应该清"但基线 reset() 确实不碰的字段。

extraction 重构必须让这组测试在迁移前后都保持绿色；任何字段行为变化都
说明迁移不是机械复制。修复"疑似 bug 的 reset 字段"属于另开的 bugfix PR。
"""

from __future__ import annotations

import pytest

from src.engine.game_instance import GameInstance, GameState
from src.engine.world_state import fresh_world_state


def _make_populated_instance() -> GameInstance:
    """构造一个几乎所有字段都有值的实例，用于观察 reset 前后差异。"""
    instance = GameInstance(game_key=("web", "reset-characterization", "bot"))
    instance.run_id = "run_before"
    instance.memory_namespace = "('web', 'reset-characterization', 'bot')::run:run_before"
    instance.economy = {
        "schema_version": 2,
        "run_id": "run_before",
        "next_sequence": 7,
        "proposals": [{"id": "p1"}],
        "transactions": [{"id": "t1"}],
        "idempotency_records": {"k": "v"},
        "effect_groups": [{"id": "g1"}],
        "external_effects_outbox": [{"id": "o1"}],
        "outcomes": [{"id": "x1"}],
    }
    instance.world_id = "world-1"
    instance.world_name = "Test World"
    instance.rule_id = "coc7"
    instance.ruleset_runtime = {
        "id": "core:dnd2024",
        "version": 1,
        "content_version": "2024-01",
        "state_schema_version": 3,
    }
    instance.ruleset_state = {"state_schema_version": 3, "campaign": {"party": []}}
    instance.adventure_binding = {
        "adventure_id": "adv-1",
        "version": "1",
        "format": "v1",
        "content_digest": "deadbeef",
        "world_id": "world-1",
    }
    instance.play_mode = "adventure"
    instance.event_ledger = [{"event": "e1"}]
    instance.scene_image = {"asset_id": "img-1"}
    instance.map_background = {"asset_id": "map-1"}
    instance.group_name = "Group"
    instance.state = GameState.ACTIVE_JUDGMENT
    instance.players = {
        "u1": {
            "character_name": "Alice",
            "character_sheet": {"hp": 10, "gold": 5, "deceased": False},
            "control": {"mode": "human", "revision": 3},
        },
    }
    instance.npcs = {"goblin": {"hp": 7}}
    instance.round_number = 4
    instance.action_queue = [{"user_id": "u1", "text": "act"}]
    instance.pending_actions = [{"user_id": "u2", "text": "pending"}]
    instance.ready_players = {"u1"}
    instance.away_players = {"u2"}
    instance.combat_active = True
    instance.combat_enemies = [{"hp": 3}]
    instance.combat_state = "active"
    instance.initiative_order = ["u1"]
    instance.initiative_current = 1
    instance.max_players = 9
    instance.gm_uid = "gm1"
    instance.player_access_open = False
    instance.away_control_policy = "ai_takeover"
    instance.bot_bind_token = "bind-token"
    instance.room_password = "secret"
    instance.room_token = "room-token"
    instance.private_log = {"u1": [{"role": "gm", "text": "hi"}]}
    instance.table_talk = [{"speaker": "u1", "text": "tt"}]
    instance.scene = "老桥"
    instance.game_time = "14:00"
    instance.log = [{"round": 4, "gm_response": "叙事"}]
    instance.summary = {"narrative": "sum"}
    instance.key_facts = ["fact"]
    instance.world_state = {
        "schema_version": 1,
        "revision": 5,
        "clock": {"day": 1, "minute": 60},
        "facts": {"actor:u1.location": {"value": "bridge"}},
        "scheduled_events": [],
    }
    instance.last_saved_log_count = 3
    instance.total_llm_calls = 11
    instance.total_tokens = 2222
    instance.started_at = "2026-01-01T00:00:00+00:00"
    instance.last_activity = "2026-01-01T01:00:00+00:00"
    instance.last_check = {"check_id": "c1"}
    instance.last_checks = [{"check_id": "c1"}]
    instance.manual_roll_requests = [{"request_id": "r1"}]
    instance.round_unpriced_purchase_intents = [{"item": "potion"}]
    instance.round_checks_prepared = True
    instance.round_start_snapshot = {"u1": {"hp": 10}}
    instance.round_entity_snapshot = {"npcs": {"goblin": {"hp": 7}}}
    instance.death_save_outcomes = {"3": {"u1": {"roll": 18}}}
    instance.gm_directives = [{"id": "d1"}]
    instance.last_state_update = {"hp": "10"}
    instance.last_overreach = [{"player": "u1"}]
    instance.last_world_legality = [{"player": "u1"}]
    instance.last_world_events = [{"event_id": "e1"}]
    instance.last_token_budget_bump = {"kind": "narrative", "from": 1, "to": 2}
    instance.solo_mode = True
    instance.seed_code = "SEED42"
    instance.difficulty = "硬核"
    instance.narrative_perspective = "immersive"
    instance.gm_style_override = {"tone": "grim"}
    instance.language = "en"
    instance.entry_point = "plugin"
    instance.pending_combat_results = [{"damage": 5}]
    instance.lorebook_timed_state = {"e1": {"remaining": 3}}
    instance.quick_actions = ["attack"]
    instance.health_events = [{"kind": "degraded"}]
    instance.health_status = {"degraded": True}
    instance.luck_timeout_seconds = 90
    instance.economy_reward_policy = {"mode": "auto_small_cash", "auto_reward_cap": 10}
    instance.combat_extension = {"schema_version": 1, "pools": {"p1": {}}}
    instance.combat_extension_round_snapshots = {"4": {"schema_version": 1}}
    instance.pending_luck_after_recovery = True
    instance.confirmed_items = ["sword"]
    return instance


EXPECTED_PRESERVED = {
    "world_id": "world-1",
    "world_name": "Test World",
    "group_name": "Group",
    "solo_mode": True,
    "narrative_perspective": "immersive",
    "gm_style_override": {"tone": "grim"},
    "language": "en",
    "adventure_binding": {
        "adventure_id": "adv-1",
        "version": "1",
        "format": "v1",
        "content_digest": "deadbeef",
        "world_id": "world-1",
    },
    "ruleset_runtime": {
        "id": "core:dnd2024",
        "version": 1,
        "content_version": "2024-01",
        "state_schema_version": 3,
    },
}

# 基线 reset() 明确清空/归零的字段（值 = 字段自己的空形态）。
EXPECTED_CLEARED = {
    "npcs": {},
    "log": [],
    "summary": {},
    "key_facts": [],
    "pending_combat_results": [],
    "combat_extension_round_snapshots": {},
    "lorebook_timed_state": {},
    "health_events": [],
    "health_status": {},
    "quick_actions": [],
    "confirmed_items": [],
    "private_log": {},
    "table_talk": [],
    "gm_directives": [],
    "event_ledger": [],
}

# 基线 reset() 根本不触碰的字段 —— "隐式保留"。这里冻结的是基线行为本身。
EXPECTED_IMPLICIT_PRESERVED = {
    "rule_id": "coc7",
    "play_mode": "adventure",
    "scene_image": {"asset_id": "img-1"},
    "map_background": {"asset_id": "map-1"},
    "away_players": {"u2"},
    "max_players": 9,
    "gm_uid": "gm1",
    "player_access_open": False,
    "away_control_policy": "ai_takeover",
    "bot_bind_token": "bind-token",
    "room_password": "secret",
    "room_token": "room-token",
    "difficulty": "硬核",
    "entry_point": "plugin",
    "luck_timeout_seconds": 90,
    "economy_reward_policy": {"mode": "auto_small_cash", "auto_reward_cap": 10},
    "last_saved_log_count": 3,
    "pending_luck_after_recovery": True,
    "manual_roll_requests": [{"request_id": "r1"}],
    "round_unpriced_purchase_intents": [{"item": "potion"}],
    "death_save_outcomes": {"3": {"u1": {"roll": 18}}},
    "last_overreach": [{"player": "u1"}],
    "last_world_legality": [{"player": "u1"}],
    "last_world_events": [{"event_id": "e1"}],
}


@pytest.mark.asyncio
async def test_reset_keeps_seed_and_preserves_configuration_fields() -> None:
    instance = _make_populated_instance()
    await instance.reset(keep_seed=True)

    assert instance.state == GameState.CREATED
    assert instance.seed_code == "SEED42"
    for field, expected in EXPECTED_PRESERVED.items():
        actual = getattr(instance, field)
        assert actual == expected, f"reset 必须保留 {field}"
    # 保留字段应是深拷贝，reset 后修改不影响旧对象引用。
    assert instance.gm_style_override is not EXPECTED_PRESERVED["gm_style_override"]


@pytest.mark.asyncio
async def test_reset_without_seed_clears_seed_code() -> None:
    instance = _make_populated_instance()
    await instance.reset(keep_seed=False)
    assert instance.seed_code == ""


@pytest.mark.asyncio
async def test_reset_clears_runtime_and_narrative_state() -> None:
    instance = _make_populated_instance()
    await instance.reset(keep_seed=True)

    assert instance.players == {}
    assert instance.round_number == 0
    assert instance.action_queue == []
    assert instance.pending_actions == []
    assert instance.ready_players == set()
    assert instance.combat_active is False
    assert instance.combat_enemies == []
    assert instance.combat_state == "none"
    assert instance.initiative_order == []
    assert instance.initiative_current == 0
    assert instance.scene == ""
    assert instance.game_time == ""
    assert instance.world_state == fresh_world_state()
    assert instance.total_llm_calls == 0
    assert instance.total_tokens == 0
    assert instance.started_at == ""
    assert instance.last_activity == ""
    assert instance.puzzle_manager is None
    assert instance.plot_tracker is None
    assert instance.combat_extension == {}
    assert instance.last_check is None
    assert instance.last_checks == []
    assert instance.round_checks_prepared is False
    assert instance.round_start_snapshot == {}
    assert instance.round_entity_snapshot == {}
    assert instance.last_state_update is None
    assert instance.last_token_budget_bump is None
    for key, expected_empty in EXPECTED_CLEARED.items():
        assert getattr(instance, key) == expected_empty, f"reset 必须清空 {key}"


@pytest.mark.asyncio
async def test_reset_rotates_run_identity_and_economy() -> None:
    instance = _make_populated_instance()
    old_run_id = instance.run_id
    old_namespace = instance.memory_namespace
    await instance.reset(keep_seed=True)

    assert instance.run_id != old_run_id
    assert instance.run_id.startswith("run_")
    assert instance.memory_namespace != old_namespace
    assert instance.memory_namespace.endswith(f"::run:{instance.run_id}")
    assert instance.memory_namespace.startswith(str(instance.game_key))
    # economy 整体重建为全新 run 的初始形态，不残留旧 proposals/transactions。
    assert instance.economy["schema_version"] == 2
    assert instance.economy["run_id"] == instance.run_id
    assert instance.economy["next_sequence"] == 1
    assert instance.economy["proposals"] == []
    assert instance.economy["transactions"] == []
    assert instance.economy["external_effects_outbox"] == []


@pytest.mark.asyncio
async def test_reset_does_not_touch_implicit_preserve_fields() -> None:
    instance = _make_populated_instance()
    await instance.reset(keep_seed=True)

    for field, expected in EXPECTED_IMPLICIT_PRESERVED.items():
        actual = getattr(instance, field)
        assert actual == expected, (
            f"基线 reset() 不触碰 {field}；extraction 不得改变这一行为"
        )


@pytest.mark.asyncio
async def test_reset_rebuilds_ruleset_state_from_preserved_runtime() -> None:
    instance = _make_populated_instance()
    await instance.reset(keep_seed=True)

    assert instance.ruleset_state == {"state_schema_version": 3}
