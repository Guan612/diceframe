"""Structured adventure gates (ADV2-02, 母方案 §25/§118).

v2 transition 的条件词表——**有限枚举，不是 DSL**（§25 硬边界：无 eval /
javascript / python / 表达式语言）。每个条件是一个结构化断言：

\`\`\`json
{"type": "world.fact_equals", "key": "location:bridge.passable", "value": false}
\`\`\`


词表（母方案 §25）：

\`\`\`text
world.fact_equals / world.entity_status / world.relation_status / world.process_status
adventure.milestone / adventure.objective_status
rules.outcome / rules.party_level / rules.item_possession   （经 runtime adapter）
\`\`\`

求值模型（条件注册表）：

- 每个类型在注册表里登记一个 **reader**：从权威状态读出"可比较值 + 存在性"；
- 比较由通用 **op** 完成：`eq`（默认，兼容全部存量图）/ `in` / `gt` / `gte` /
  `lt` / `lte`；
- 新类型必须先进入 `_TYPE_OPS` 封闭词表（连同允许的 op 集合），再用
  `register_gate_reader` 登记 reader；注册表不向内容 / 插件开放。


op 语义与边界：

- `eq`：任意值，沿用 `==`；缺省 op = eq，归一化结果**不物化**缺省 op
  （存量已验证图字节不变）；
- `in`：`value` 必须是有界标量数组，实际值等于其中一项；
- `gt` / `gte` / `lt` / `lte`：`value` 在校验期必须是数值；求值期双侧必须
  同为数值（bool 不算数值），否则**不满足**（fail closed，不猜）；
- 每个类型允许的 op 集合封闭于 `_TYPE_OPS`：status 类只开 `eq` / `in`，
  `adventure.milestone` 与 `rules.*` 只开 `eq`；rules evaluator 契约的 op
  扩展留给后续 PR，不在本词表内猜测。


求值语义：

- 一个 transition 的 conditions 列表是 **AND**：全部满足才开放；
- **证据不足 = 不满足**（rules adapter 缺席 / 读取失败 → False）——gate 永远
  不能凭"不知道"放行（与 §32C 的"未知≠false"分工：legality 阻断的是玩家
  行动矛盾，gate 决定的是剧情分支走向，走向错误比走向保守更危险时选保守）；
- rules.* 条件经调用方注入的 evaluator（可调用）求值，返回值必须为 bool。
"""

from __future__ import annotations

import operator
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from src.engine.world.read import (
    fact_value,
    world_entities,
    world_processes,
    world_relations,
)

GATE_OPS = ("eq", "in", "gt", "gte", "lt", "lte")
MAX_GATES_PER_TRANSITION = 8
MAX_IN_VALUES = 16

_EQ_ONLY = frozenset({"eq"})
_STATUS_OPS = frozenset({"eq", "in"})
_ALL_OPS = frozenset(GATE_OPS)

# 封闭词表：类型 → 允许的 op 集合（GATE_TYPES 由此派生，单一事实来源）。
_TYPE_OPS: dict[str, frozenset[str]] = {
    "world.fact_equals": _ALL_OPS,
    "world.entity_status": _STATUS_OPS,
    "world.relation_status": _STATUS_OPS,
    "world.process_status": _STATUS_OPS,
    "adventure.milestone": _EQ_ONLY,
    "adventure.objective_status": _STATUS_OPS,
    "rules.outcome": _EQ_ONLY,
    "rules.party_level": _EQ_ONLY,
    "rules.item_possession": _EQ_ONLY,
}

GATE_TYPES = tuple(_TYPE_OPS)

_ORDERING_OPS = frozenset({"gt", "gte", "lt", "lte"})
_ORDERING = {
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}


class GateError(ValueError):
    """A gate is malformed or cannot be evaluated: fail closed."""


@dataclass(frozen=True)
class GateValue:
    """reader 的读出结果：exists=False 时无论 value 是什么都不可满足。"""

    exists: bool
    value: Any


GateReader = Callable[..., GateValue]


def validate_gate(raw: Any) -> dict[str, Any]:
    """Validate one structured gate; unknown fields / types fail closed."""

    if not isinstance(raw, dict):
        raise GateError("gate must be an object")
    gate_type = str(raw.get("type") or "")
    if gate_type not in _TYPE_OPS:
        raise GateError(f"gate type is not supported: {gate_type!r}")
    allowed = {"type", "key", "value", "id", "op"}
    extra = sorted(set(raw) - allowed)
    if extra:
        raise GateError(f"gate has unknown field: {extra[0]!r}")
    op = str(raw.get("op") or "eq")
    if op not in GATE_OPS:
        raise GateError(f"gate op is not supported: {op!r}")
    if op not in _TYPE_OPS[gate_type]:
        raise GateError(f"gate type {gate_type!r} does not support op {op!r}")
    if op == "in":
        value = raw.get("value")
        if not isinstance(value, list) or not value:
            raise GateError("gate op 'in' requires a non-empty array value")
        if len(value) > MAX_IN_VALUES:
            raise GateError(f"gate op 'in' exceeds {MAX_IN_VALUES} values")
        if any(not isinstance(item, (str, int, float, bool)) and item is not None for item in value):
            raise GateError("gate op 'in' values must be scalars")
    if op in _ORDERING_OPS and not _is_number(raw.get("value")):
        raise GateError(f"gate op {op!r} requires a numeric value")
    # 词表字段约定：world.fact_equals 用 key；其余用 id；value 一律必填。
    gate = {"type": gate_type, "value": raw.get("value")}
    if gate_type == "world.fact_equals":
        gate["key"] = str(raw.get("key") or "")
        if not gate["key"]:
            raise GateError("world.fact_equals requires key")
    else:
        gate["id"] = str(raw.get("id") or "")
        if not gate["id"]:
            raise GateError(f"{gate_type} requires id")
    # 缺省 / 显式 eq 都不物化，已验证的存量图保持字节不变。
    if op != "eq":
        gate["op"] = op
    return gate


def validate_gates(raw: Any, *, label: str) -> list[dict[str, Any]]:
    """Validate a transition's conditions list (bounded, all-or-nothing)."""

    if raw is None:
        return []
    if not isinstance(raw, list):
        raise GateError(f"{label} conditions must be an array")
    if len(raw) > MAX_GATES_PER_TRANSITION:
        raise GateError(f"{label} conditions exceed {MAX_GATES_PER_TRANSITION}")
    return [validate_gate(gate) for gate in raw]


def register_gate_reader(gate_type: str, reader: GateReader) -> None:
    """登记一个类型的权威状态 reader（仅引擎能力模块；词表仍封闭）。

    新类型必须先加入 `_TYPE_OPS`（含允许的 op 集合）；`rules.*` 经 evaluator
    求值、不登记 reader；重复登记是编程错误。
    """

    if gate_type not in _TYPE_OPS or gate_type.startswith("rules."):
        raise GateError(f"gate type is not registrable: {gate_type!r}")
    if gate_type in _GATE_READERS:
        raise GateError(f"gate type already has a reader: {gate_type!r}")
    _GATE_READERS[gate_type] = reader


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _read_world_fact(gate: Mapping[str, Any], *, instance: Any, progress: Mapping[str, Any]) -> GateValue:
    del progress
    # fact 缺失读出 None，与历史 eq 行为一致（None == None 可满足）。
    return GateValue(True, fact_value(getattr(instance, "world_state", None), str(gate.get("key") or "")))


def _status_reader(
    container: Callable[[Any], Mapping[str, Any]],
) -> GateReader:
    def reader(gate: Mapping[str, Any], *, instance: Any, progress: Mapping[str, Any]) -> GateValue:
        del progress
        # 非 dict 实体让 .get 抛错 → 外层 fail closed，与历史路径一致。
        obj = container(getattr(instance, "world_state", None)).get(str(gate.get("id") or ""))
        return GateValue(obj is not None, obj.get("status") if obj is not None else None)

    return reader


def _read_milestone(gate: Mapping[str, Any], *, instance: Any, progress: Mapping[str, Any]) -> GateValue:
    del instance
    completed = {str(item) for item in (progress.get("completed_milestones") or [])}
    return GateValue(True, str(gate.get("id") or "") in completed)


def _read_objective_status(gate: Mapping[str, Any], *, instance: Any, progress: Mapping[str, Any]) -> GateValue:
    del instance
    # 历史契约：status 与 str(expected or "") 比较（value 会被字符串化）。
    completed = {str(item) for item in (progress.get("completed_objectives") or [])}
    return GateValue(
        True,
        "completed" if str(gate.get("id") or "") in completed else "active",
    )


def _compare(actual: Any, expected: Any, op: str) -> bool:
    if op == "eq":
        return bool(actual == expected)
    if op == "in":
        if not isinstance(expected, list):
            return False
        return any(actual == item for item in expected)
    order = _ORDERING.get(op)
    if order is None or not (_is_number(actual) and _is_number(expected)):
        return False
    return bool(order(actual, expected))


def _gate_satisfied(
    gate: Mapping[str, Any],
    *,
    instance: Any,
    progress: Mapping[str, Any],
    rules_evaluator: Callable[[str, str, Any], bool] | None,
) -> bool:
    gate_type = str(gate.get("type") or "")
    op = str(gate.get("op") or "eq")
    try:
        if gate_type.startswith("rules."):
            if rules_evaluator is None:
                return False  # 证据不足：不满足（不猜）。
            if op != "eq":
                return False  # evaluator 契约未扩展 op 之前不猜。
            result = rules_evaluator(gate_type, str(gate.get("id") or ""), gate.get("value"))
            return bool(result)
        reader = _GATE_READERS.get(gate_type)
        if reader is None:
            return False
        outcome = reader(gate, instance=instance, progress=progress)
        if gate_type in _PRESENCE_GATES:
            return bool(outcome.value)
        return bool(outcome.exists) and _compare(outcome.value, gate.get("value"), op)
    except Exception:  # noqa: BLE001 - 读取失败 = 证据不足 = 不满足
        return False


def gates_satisfied(
    gates: list[dict[str, Any]],
    *,
    instance: Any,
    progress: Mapping[str, Any],
    rules_evaluator: Callable[[str, str, Any], bool] | None = None,
) -> bool:
    """AND over all gates; empty list = open."""

    return all(
        _gate_satisfied(gate, instance=instance, progress=progress, rules_evaluator=rules_evaluator)
        for gate in gates
    )


# 历史契约：milestone 只看"是否已完成"，value 是装饰性的
# （写 value:false 也不反转结果）；保持原语义，不给它开 op。
_PRESENCE_GATES = frozenset({"adventure.milestone"})

_GATE_READERS: dict[str, GateReader] = {}

register_gate_reader("world.fact_equals", _read_world_fact)
register_gate_reader("world.entity_status", _status_reader(world_entities))
register_gate_reader("world.relation_status", _status_reader(world_relations))
register_gate_reader("world.process_status", _status_reader(world_processes))
register_gate_reader("adventure.milestone", _read_milestone)
register_gate_reader("adventure.objective_status", _read_objective_status)


__all__ = [
    "GATE_OPS",
    "GATE_TYPES",
    "MAX_GATES_PER_TRANSITION",
    "GateError",
    "GateValue",
    "gates_satisfied",
    "register_gate_reader",
    "validate_gate",
    "validate_gates",
]
