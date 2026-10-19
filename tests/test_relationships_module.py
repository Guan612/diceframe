"""Relationships module slot 测试（P2：slot + REL 标签 + applier + 投影）。

覆盖：schema 解析的封闭词表与 fail-fast、REL 标签语法（对象 ID 含冒号）、
applier 的钳制/单轮上限/阶段引擎计算（monotonic / derived / 里程碑门控）、
回退与回滚的精确反向恢复、座位与 GM 投影的可见性过滤、GM prompt 块的
发布-读取链路、存档迁移补槽。
"""

from __future__ import annotations

import pytest

from src.commands.madness_tracker import MadnessTracker
from src.commands.player_state_applier import PlayerStateApplier
from src.commands.player_tag_handlers import parse_player_tag
from src.engine import module_hooks
from src.engine.game_instance import GameInstance
from src.engine.modules import relationships_state
from src.rules.rule_system import RuleSystem


SCHEMA = {
    "dimensions": [
        {"key": "affection", "label": "好感", "min": 0, "max": 100, "default": 10,
         "per_round_cap": 0, "visibility": "self"},
        {"key": "trust", "label": "信任", "min": 0, "max": 100, "default": 0,
         "per_round_cap": 0, "visibility": "gm"},
        {"key": "spark", "label": "心动", "min": 0, "max": 100, "default": 0,
         "per_round_cap": 0, "visibility": "hidden"},
    ],
    "stages": [
        {"key": "stranger"},
        {"key": "friend", "enter": {"affection": {"gte": 30}}},
        {"key": "crush", "enter": {"affection": {"gte": 60}, "trust": {"gte": 30}}},
        {"key": "lover", "enter": {"affection": {"gte": 85}}, "requires_milestone": "lin_confess"},
    ],
    "stage_mode": "monotonic",
    "targets": ["npc:lin"],
}

CAPPED_SCHEMA = {
    "dimensions": [
        {"key": "affection", "label": "好感", "min": 0, "max": 100, "default": 10, "per_round_cap": 8},
    ],
    "stages": [],
    "targets": ["npc:lin"],
}


def rule(schema=SCHEMA):
    template = {"rule_id": "relationship_test", "relationship_schema": schema}
    return RuleSystem(template)


def game():
    return GameInstance(game_key=("web", "relationships", "gm"))


def track(instance, uid="alice", target="npc:lin"):
    return relationships_state.state(instance)["tracks"].get(uid, {}).get(target, {})


@pytest.mark.parametrize("bad", [
    {"dimensions": []},
    {"dimensions": "affection"},
    {"dimensions": [{"key": "a", "min": 10, "max": 5, "default": 7}]},
    {"dimensions": [{"key": "a", "min": 0, "max": 10, "default": 20}]},
    {"dimensions": [{"key": "a"}, {"key": "a"}]},
    {"dimensions": [{"key": "a b"}]},
    {"dimensions": [{"key": "a", "visibility": "everyone"}]},
    {"dimensions": [{"key": "a", "per_round_cap": 999}]},
    {"stage_mode": "yolo"},
    {"stages": [{"key": "s", "enter": {"nope": {"gte": 1}}}]},
    {"stages": [{"key": "s", "enter": {"affection": {"gt": 1}}}]},
    {"stages": [{"key": "s", "requires_milestone": True}]},
    {"stages": [{"key": "s"}, {"key": "s"}]},
    {"targets": ["npc:lin", "npc:lin"]},
])
def test_relationship_schema_fails_closed(bad):
    with pytest.raises(ValueError):
        relationships_state.parse_relationship_schema({**SCHEMA, **bad})


def test_parse_returns_none_when_absent():
    assert relationships_state.parse_relationship_schema(None) is None
    assert rule().relationship_schema["stage_mode"] == "monotonic"


def test_rel_tag_grammar_accepts_colon_targets():
    result = {"state_update": {"players": {}}}
    parse_player_tag("REL", "alice:npc:lin:affection:+5", result, {})
    changes = result["state_update"]["players"]["alice"]["relationship_changes"]
    assert changes == {"npc:lin": {"affection": 5}}
    parse_player_tag("REL", "alice:npc:lin:affection:-3", result, {})
    assert changes["npc:lin"]["affection"] == 2
    # 同目标多标签累计
    parse_player_tag("REL", "alice:npc:lin:trust:5", result, {})
    assert changes["npc:lin"] == {"affection": 2, "trust": 5}


@pytest.mark.parametrize("value", ["alice:lin:affection", "alice::affection:5", ":npc:lin:affection:5",
                                   "alice:npc:lin:affection:abc", "alice:npc:lin:affection:999"])
def test_rel_tag_rejects_malformed(value):
    result = {"state_update": {"players": {}}}
    parse_player_tag("REL", value, result, {})
    assert "relationship_changes" not in result["state_update"]["players"].setdefault("alice", {})


def test_apply_changes_clamps_and_advances_stage():
    instance = game()
    schema = relationships_state.parse_relationship_schema(SCHEMA)
    notices = relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": 25}}, schema)
    assert track(instance)["values"]["affection"] == 35  # 10 默认 + 25
    assert track(instance)["stage"] == "friend"
    assert notices == [{"subject": "alice", "target": "npc:lin", "from": "stranger", "to": "friend"}]
    # min/max 钳制
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": -999}}, schema)
    assert track(instance)["values"]["affection"] == 0
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": 999}}, schema)
    assert track(instance)["values"]["affection"] == 100


def test_apply_changes_enforces_per_round_cap(monkeypatch):
    instance = game()
    schema = relationships_state.parse_relationship_schema(CAPPED_SCHEMA)
    monkeypatch.setattr(relationships_state.progression, "current_round", lambda _i: 3)
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": 6}}, schema)
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": 6}}, schema)
    assert track(instance)["values"]["affection"] == 10 + 8  # cap=8
    # 负向同样受限；下一轮额度恢复
    monkeypatch.setattr(relationships_state.progression, "current_round", lambda _i: 4)
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": 6}}, schema)
    assert track(instance)["values"]["affection"] == 10 + 8 + 6


def test_monotonic_stage_never_downgrades():
    instance = game()
    schema = relationships_state.parse_relationship_schema(SCHEMA)
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": 25}}, schema)
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": -20}}, schema)
    assert track(instance)["values"]["affection"] == 15
    assert track(instance)["stage"] == "friend"  # monotonic：数值掉了阶段不回


def test_derived_stage_follows_values():
    derived = {**SCHEMA, "stage_mode": "derived"}
    instance = game()
    schema = relationships_state.parse_relationship_schema(derived)
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": 25}}, schema)
    assert track(instance)["stage"] == "friend"
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": -20}}, schema)
    assert track(instance)["stage"] == "stranger"


def test_milestone_gate_blocks_lover_without_evidence():
    instance = game()
    schema = relationships_state.parse_relationship_schema(SCHEMA)
    relationships_state.apply_changes(
        instance, "alice", {"npc:lin": {"affection": 90, "trust": 40}}, schema, milestones=set(),
    )
    assert track(instance)["stage"] == "crush"  # 数值够但里程碑缺席
    # 里程碑达成后，下一次写入重算进入 lover
    relationships_state.apply_changes(
        instance, "alice", {"npc:lin": {"trust": 1}}, schema, milestones={"lin_confess"},
    )
    assert track(instance)["stage"] == "lover"


def test_undeclared_targets_and_dimensions_rejected():
    instance = game()
    schema = relationships_state.parse_relationship_schema(SCHEMA)
    relationships_state.apply_changes(instance, "alice", {"npc:ghost": {"affection": 10}}, schema)
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"nope": 10}}, schema)
    assert track(instance) == {}  # 未声明对象不落槽；声明对象无有效 delta 也不建 track


def test_rewind_restores_values_and_stage(monkeypatch):
    instance = game()
    schema = relationships_state.parse_relationship_schema(SCHEMA)
    monkeypatch.setattr(relationships_state.progression, "current_round", lambda _i: 1)
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": 25}}, schema)
    monkeypatch.setattr(relationships_state.progression, "current_round", lambda _i: 2)
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"trust": 5}}, schema)
    assert track(instance)["stage"] == "friend"
    relationships_state.rewind(instance, 1)
    assert track(instance)["values"] == {"affection": 35, "trust": 0, "spark": 0}
    assert track(instance)["stage"] == "friend"
    # 回退越过全部 delta：track 由非零 delta 物化，反毕即整体撤销
    relationships_state.rewind(instance, 0)
    assert track(instance) == {}


def test_round_abort_reverts_current_round(monkeypatch):
    instance = game()
    schema = relationships_state.parse_relationship_schema(SCHEMA)
    monkeypatch.setattr(relationships_state.progression, "current_round", lambda _i: 5)
    assert relationships_state._on_round_abort(instance) is False  # 本轮无 delta
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": 5}}, schema)
    assert relationships_state._on_round_abort(instance) is True
    assert track(instance) == {}


def test_views_filter_visibility():
    instance = game()
    schema = relationships_state.parse_relationship_schema(SCHEMA)
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": 7, "trust": 3}}, schema)
    seat = relationships_state.seat_view(instance, schema, "alice")
    assert seat["npc:lin"]["values"] == {"affection": 17}  # self 可见；gm/hidden 不可见
    gm = relationships_state.gm_view(instance, schema)
    assert gm["alice"]["npc:lin"]["values"] == {"affection": 17, "trust": 3}  # hidden 仍隐藏
    assert relationships_state.seat_view(instance, schema, "bob") == {}


def test_gm_context_block_needs_published_schema():
    instance = game()
    assert relationships_state.gm_context_block(instance) == ""  # 未发布即未配置
    relationships_state.publish_schema(instance, rule())
    block = relationships_state.gm_context_block(instance)
    assert "Relationship State" in block and "REL:玩家ID:对象ID:维度:变化量" in block
    relationships_state.publish_schema(instance, RuleSystem({"rule_id": "x"}))
    assert relationships_state.gm_context_block(instance) == ""  # 无 schema 的规则会撤下块
    assert module_hooks.read(instance, module_hooks.GM_PROMPT_SECTIONS) == []


def test_applier_settles_rel_tags_end_to_end():
    instance = game()
    instance.players["alice"] = {"character_name": "Alice", "character_sheet": {"hp": 10, "max_hp": 10}}
    update = {"relationship_changes": {"npc:lin": {"affection": 25}}}
    PlayerStateApplier(MadnessTracker()).apply_players(instance, {"alice": update}, rule=rule())
    assert track(instance)["stage"] == "friend"
    assert track(instance)["values"]["affection"] == 35
    # schema 快照已发布，GM prompt 块可读
    block = relationships_state.gm_context_block(instance)
    assert "npc:lin" in block


def test_applier_ignores_rel_without_schema():
    instance = game()
    instance.players["alice"] = {"character_name": "Alice", "character_sheet": {"hp": 10, "max_hp": 10}}
    update = {"relationship_changes": {"npc:lin": {"affection": 25}}}
    PlayerStateApplier(MadnessTracker()).apply_players(
        instance, {"alice": update}, rule=RuleSystem({"rule_id": "plain"}),
    )
    assert track(instance) == {}
    assert relationships_state.gm_context_block(instance) == ""


def test_instance_reset_clears_tracks():
    instance = game()
    schema = relationships_state.parse_relationship_schema(SCHEMA)
    relationships_state.apply_changes(instance, "alice", {"npc:lin": {"affection": 5}}, schema)
    relationships_state.reset(instance)
    assert relationships_state.state(instance)["tracks"] == {}
