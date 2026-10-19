"""Structured gates 测试（ADV2-02，母方案 §25/§118）。

覆盖：§25 词表逐类求值（world 四类 / adventure 两类 / rules 经 adapter）、
AND 语义、证据不足=不满足（rules adapter 缺席 / 读取异常）、未知 gate 类型
与未知字段 fail closed、adv2 图契约接受合法 gate。
"""

from __future__ import annotations

import pytest

from src.adventures.gates import (
    GATE_TYPES,
    GateError,
    gates_satisfied,
    validate_gates,
)
from src.engine.game_instance import GameInstance
from src.engine.world_state import apply_world_ops


def make_instance() -> GameInstance:
    return GameInstance(game_key=("web", "adv2-gates", "bot"))


def _populated_instance() -> GameInstance:
    instance = make_instance()
    apply_world_ops(instance, [
        {"op": "set_fact", "key": "location:bridge.passable", "value": False},
        {"op": "register_entity", "entity_id": "npc:count", "kind": "npc"},
        {"op": "add_relation", "relation_id": "rel:bridge-road", "kind": "connects",
         "from_ref": "location:east", "to_ref": "location:harbor"},
        {"op": "start_process", "process_id": "process:ritual", "kind": "ritual"},
        {"op": "complete_process", "process_id": "process:ritual"},
    ])
    return instance


@pytest.mark.parametrize("gate,expected", [
    ({"type": "world.fact_equals", "key": "location:bridge.passable", "value": False}, True),
    ({"type": "world.fact_equals", "key": "location:bridge.passable", "value": True}, False),
    ({"type": "world.entity_status", "id": "npc:count", "value": "active"}, True),
    ({"type": "world.entity_status", "id": "npc:count", "value": "retired"}, False),
    ({"type": "world.relation_status", "id": "rel:bridge-road", "value": "active"}, True),
    ({"type": "world.relation_status", "id": "rel:bridge-road", "value": "severed"}, False),
    ({"type": "world.process_status", "id": "process:ritual", "value": "completed"}, True),
    ({"type": "world.process_status", "id": "process:ritual", "value": "running"}, False),
])
def test_world_gates_evaluate_against_authoritative_state(gate: dict, expected: bool) -> None:
    assert gates_satisfied([gate], instance=_populated_instance(), progress={}) is expected


def test_adventure_gates_use_progress() -> None:
    progress = {"completed_milestones": ["mile_castle"], "completed_objectives": ["obj_crown"]}
    assert gates_satisfied(
        [{"type": "adventure.milestone", "id": "mile_castle", "value": True}],
        instance=make_instance(), progress=progress,
    )
    assert gates_satisfied(
        [{"type": "adventure.objective_status", "id": "obj_crown", "value": "completed"}],
        instance=make_instance(), progress=progress,
    )
    assert not gates_satisfied(
        [{"type": "adventure.objective_status", "id": "obj_crown", "value": "active"}],
        instance=make_instance(), progress=progress,
    )


def test_rules_gates_need_evaluator_and_default_to_unsatisfied() -> None:
    gate = {"type": "rules.party_level", "id": "party", "value": 5}
    # adapter 缺席：证据不足 → 不满足（不猜）。
    assert gates_satisfied([gate], instance=make_instance(), progress={}) is False
    assert gates_satisfied(
        [gate], instance=make_instance(), progress={},
        rules_evaluator=lambda gate_type, gate_id, value: value == 5,
    )


def test_gates_are_and_semantics() -> None:
    instance = _populated_instance()
    assert gates_satisfied([
        {"type": "world.entity_status", "id": "npc:count", "value": "active"},
        {"type": "world.relation_status", "id": "rel:bridge-road", "value": "active"},
    ], instance=instance, progress={})
    assert not gates_satisfied([
        {"type": "world.entity_status", "id": "npc:count", "value": "active"},
        {"type": "world.relation_status", "id": "rel:bridge-road", "value": "severed"},
    ], instance=instance, progress={})


def test_gate_vocabulary_is_closed_and_fail_closed() -> None:
    with pytest.raises(GateError, match="not supported"):
        validate_gates([{"type": "world.weather", "id": "x", "value": "rain"}], label="t")
    with pytest.raises(GateError, match="unknown field"):
        validate_gates([{"type": "world.fact_equals", "key": "a.b", "value": 1, "expr": "1+1"}], label="t")
    with pytest.raises(GateError, match="exceed"):
        validate_gates(
            [{"type": "world.fact_equals", "key": "a.b", "value": 1}] * 9, label="t",
        )
    assert len(GATE_TYPES) == 9


def test_corrupt_world_degrades_to_unsatisfied() -> None:
    instance = make_instance()
    instance.world_state = {"schema_version": 99, "facts": {}}
    assert gates_satisfied(
        [{"type": "world.fact_equals", "key": "a.b", "value": 1}],
        instance=instance, progress={},
    ) is False


def test_default_op_is_eq_and_is_not_materialized() -> None:
    (no_op,) = validate_gates([{"type": "world.fact_equals", "key": "a.b", "value": 1}], label="t")
    assert "op" not in no_op
    (explicit_eq,) = validate_gates(
        [{"type": "world.fact_equals", "key": "a.b", "value": 1, "op": "eq"}], label="t",
    )
    assert "op" not in explicit_eq
    (with_op,) = validate_gates(
        [{"type": "world.fact_equals", "key": "a.b", "value": 1, "op": "gte"}], label="t",
    )
    assert with_op["op"] == "gte"


def test_fact_ordering_ops_compare_numbers() -> None:
    instance = make_instance()
    apply_world_ops(instance, [{"op": "set_fact", "key": "stat:party.morale", "value": 7}])
    gate = {"type": "world.fact_equals", "key": "stat:party.morale"}
    cases = [
        ({"op": "gte", "value": 5}, True),
        ({"op": "gte", "value": 7}, True),
        ({"op": "gt", "value": 7}, False),
        ({"op": "lt", "value": 5}, False),
        ({"op": "lte", "value": 7}, True),
        ({"op": "eq", "value": 7}, True),
    ]
    for extra, expected in cases:
        assert gates_satisfied([{**gate, **extra}], instance=instance, progress={}) is expected, extra


def test_ordering_fails_closed_on_non_numeric_actual() -> None:
    instance = make_instance()
    apply_world_ops(instance, [
        {"op": "set_fact", "key": "mood:party", "value": "high"},
        {"op": "set_fact", "key": "flag:done", "value": True},
    ])
    # 字符串 / bool 实际值与数值期望不可比 → 不满足（fail closed，不猜）。
    assert gates_satisfied(
        [{"type": "world.fact_equals", "key": "mood:party", "op": "gte", "value": 3}],
        instance=instance, progress={},
    ) is False
    assert gates_satisfied(
        [{"type": "world.fact_equals", "key": "flag:done", "op": "gte", "value": 0}],
        instance=instance, progress={},
    ) is False


def test_in_op_membership() -> None:
    instance = _populated_instance()
    assert gates_satisfied(
        [{"type": "world.entity_status", "id": "npc:count", "op": "in", "value": ["active", "busy"]}],
        instance=instance, progress={},
    )
    assert not gates_satisfied(
        [{"type": "world.entity_status", "id": "npc:count", "op": "in", "value": ["retired"]}],
        instance=instance, progress={},
    )
    progress = {"completed_objectives": ["obj_crown"]}
    assert gates_satisfied(
        [{"type": "adventure.objective_status", "id": "obj_crown", "op": "in", "value": ["completed"]}],
        instance=make_instance(), progress=progress,
    )


def test_op_vocabulary_is_closed_at_validation() -> None:
    fact = {"type": "world.fact_equals", "key": "a.b"}
    with pytest.raises(GateError, match="op is not supported"):
        validate_gates([{**fact, "value": 1, "op": "between"}], label="t")
    with pytest.raises(GateError, match="does not support op"):
        validate_gates(
            [{"type": "world.entity_status", "id": "npc:count", "value": "active", "op": "gte"}], label="t",
        )
    with pytest.raises(GateError, match="requires a numeric value"):
        validate_gates([{**fact, "value": "5", "op": "gte"}], label="t")
    with pytest.raises(GateError, match="requires a non-empty array"):
        validate_gates([{**fact, "op": "in", "value": []}], label="t")
    with pytest.raises(GateError, match="requires a non-empty array"):
        validate_gates([{**fact, "op": "in", "value": "active"}], label="t")
    with pytest.raises(GateError, match="exceeds"):
        validate_gates([{**fact, "op": "in", "value": [1] * 17}], label="t")
    with pytest.raises(GateError, match="must be scalars"):
        validate_gates([{**fact, "op": "in", "value": [{"x": 1}]}], label="t")
    with pytest.raises(GateError, match="does not support op"):
        validate_gates(
            [{"type": "rules.party_level", "id": "party", "value": 5, "op": "gte"}], label="t",
        )


def test_milestone_value_is_decorative() -> None:
    # 历史契约：milestone 只看是否完成，value:false 不反转结果。
    progress = {"completed_milestones": ["mile_castle"]}
    assert gates_satisfied(
        [{"type": "adventure.milestone", "id": "mile_castle", "value": False}],
        instance=make_instance(), progress=progress,
    )


def test_gate_reader_registry_is_a_closed_extension_point(monkeypatch) -> None:
    from src.adventures import gates as gates_module

    monkeypatch.setitem(gates_module._TYPE_OPS, "world.mood", gates_module._EQ_ONLY)

    def reader(gate, *, instance, progress):
        return gates_module.GateValue(True, "sunny")

    gates_module.register_gate_reader("world.mood", reader)
    try:
        assert gates_satisfied(
            [{"type": "world.mood", "id": "sky", "value": "sunny"}],
            instance=make_instance(), progress={},
        )
        with pytest.raises(GateError, match="already has a reader"):
            gates_module.register_gate_reader("world.mood", reader)
    finally:
        gates_module._GATE_READERS.pop("world.mood", None)

    with pytest.raises(GateError, match="not registrable"):
        gates_module.register_gate_reader("world.newthing", reader)
    with pytest.raises(GateError, match="not registrable"):
        gates_module.register_gate_reader("rules.outcome", reader)
