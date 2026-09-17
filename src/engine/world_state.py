"""Authoritative world truth: facts, logical clock, and scheduled events.

`#284` needs one authoritative owner for "what is currently true in the world"
so a player action cannot silently teleport, walk over a destroyed bridge, or
rewrite a fact the table already established.  That owner is the single-game
aggregate: ``GameInstance.world_state``.

This module is the only writer (``apply_world_ops``) and the only place that
validates the shape.  Callers must not poke ``instance.world_state["facts"]``
directly; they must go through world ops so that validation, bounds, revision
bookkeeping and provenance stay in one place.

Persisted schema (``schema_version = 1``)::

    {
      "schema_version": 1,
      "revision": 3,
      "clock": {"day": 1, "minute": 720},
      "facts": {
        "actor:p1.location": {
          "value": "village_east",
          "visibility": "public",
          "source_round": 4,
          "updated_revision": 3
        }
      },
      "scheduled_events": {
        "ritual:clearing": {
          "event_id": "ritual:clearing",
          "due_at": {"day": 1, "minute": 840},
          "status": "pending",
          "label": "清林仪式完成",
          "ops": [
            {"op": "set_fact", "key": "ritual:clearing.status", "value": "completed"}
          ]
        }
      }
    }

Design boundaries (deliberately small for the first version):

- No entity graph, no relations, no map topology, no pathfinding.  A fact is a
  canonical key plus a scalar value and its visibility.
- No background work: world ops are pure, synchronous mutations applied by the
  existing authoritative flow while it already holds the aggregate locks.  This
  module never starts threads, writes files, or performs network calls.
- Facts are canonical world coordinates, never localized display names: keys
  match ``[A-Za-z0-9_.:-]`` so a translated label cannot become an identity.
- ``advance_time`` only moves the logical clock.  Settling due scheduled events
  is a separate concern (see the follow-up work package) so this container
  cannot start executing events by accident.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

WORLD_STATE_SCHEMA_VERSION = 1

# 事实可见性：第一版只有公开与 GM 私有。更细的 ACL / group graph 不在本层。
FACT_VISIBILITIES = ("public", "gm")
# 事件状态：pending 待结算（后续 work package 结算后为 applied），cancelled 由
# cancel_event 写入。三者都是持久化值，不能靠内存标记推断。
EVENT_STATUSES = ("pending", "applied", "cancelled")
OP_KINDS = ("set_fact", "remove_fact", "advance_time", "schedule_event", "cancel_event")
# 定时事件内部只允许改事实；不允许事件嵌套调度或自己推进时间（否则结算顺序
# 会依赖递归，不再确定性）。
EVENT_OP_KINDS = ("set_fact", "remove_fact")

MINUTES_PER_DAY = 1440
MAX_FACTS = 512
MAX_SCHEDULED_EVENTS = 256
MAX_OPS_PER_BATCH = 64
MAX_STRING_CHARS = 400
MAX_LABEL_CHARS = 160
MAX_ABSOLUTE_INT = 1_000_000_000
MAX_CLOCK_DAY = 365_000
MAX_ADVANCE_MINUTES = MINUTES_PER_DAY * 30
# canonical key：允许平台 uid / canonical ref 常见字符，但拒绝空白、Unicode 展示名
# 与路径分隔符——世界坐标不能是翻译后的 display name。
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")


class WorldStateError(ValueError):
    """A world op or a persisted world state is invalid: fail closed."""


def fresh_world_state() -> dict[str, Any]:
    """The empty world truth of a new game (day 1, 00:00, no facts)."""

    return {
        "schema_version": WORLD_STATE_SCHEMA_VERSION,
        "revision": 0,
        "clock": {"day": 1, "minute": 0},
        "facts": {},
        "scheduled_events": {},
    }


def ensure_world_state(raw: Any) -> dict[str, Any]:
    """Return a usable container for ``GameInstance.world_state``.

    Unset / malformed input becomes a fresh empty state.  Anything else is
    passed through unchanged: persisted data is untrusted, and an unsupported
    or corrupted payload must be rejected by the write path instead of being
    silently overwritten with a default that would destroy user data.
    """

    if isinstance(raw, Mapping) and raw:
        return deepcopy(dict(raw))
    return fresh_world_state()


# ---- 读取入口：投影与合法性判断都必须经这里，且对损坏存档保持沉默降级 ----


def _current_payload(state: Any) -> Mapping[str, Any] | None:
    if not isinstance(state, Mapping):
        return None
    if state.get("schema_version") != WORLD_STATE_SCHEMA_VERSION:
        return None
    return state


def world_revision(state: Any) -> int:
    payload = _current_payload(state)
    if payload is None:
        return 0
    revision = payload.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        return 0
    return revision


def world_clock(state: Any) -> dict[str, int]:
    """The logical world time; a corrupt clock reads as day 1, 00:00."""

    payload = _current_payload(state)
    raw = payload.get("clock") if payload is not None else None
    if not isinstance(raw, Mapping):
        return {"day": 1, "minute": 0}
    day, minute = raw.get("day"), raw.get("minute")
    if (
        isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= MAX_CLOCK_DAY
        or isinstance(minute, bool) or not isinstance(minute, int)
        or not 0 <= minute < MINUTES_PER_DAY
    ):
        return {"day": 1, "minute": 0}
    return {"day": day, "minute": minute}


def world_facts(state: Any) -> dict[str, dict[str, Any]]:
    """All established facts (copies).  Malformed entries are not guessed."""

    payload = _current_payload(state)
    raw = payload.get("facts") if payload is not None else None
    if not isinstance(raw, Mapping):
        return {}
    facts: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, Mapping) and "value" in value:
            facts[key] = deepcopy(dict(value))
    return facts


def fact_value(state: Any, key: str, default: Any = None) -> Any:
    """Read one fact value without exposing the mutable container."""

    fact = world_facts(state).get(str(key or ""))
    return default if fact is None else fact.get("value", default)


def world_scheduled_events(state: Any) -> dict[str, dict[str, Any]]:
    payload = _current_payload(state)
    raw = payload.get("scheduled_events") if payload is not None else None
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(key): deepcopy(dict(value))
        for key, value in raw.items()
        if isinstance(value, Mapping)
    }


# ---- 写入口 ---------------------------------------------------------------


def apply_world_ops(
    instance: Any,
    ops: Sequence[Mapping[str, Any]],
    *,
    source_round: int | None = None,
) -> dict[str, Any]:
    """Apply one batch of world ops atomically and return what changed.

    The whole batch either applies or nothing is written: ops are first applied
    to a detached draft, and only a fully valid result is committed back to
    ``instance.world_state``.  Callers run this inside the existing
    authoritative write path; this function does no locking, IO, or scheduling.
    """

    if not isinstance(ops, Sequence) or isinstance(ops, (str, bytes)):
        raise WorldStateError("world ops must be a list")
    if not ops:
        raise WorldStateError("world ops must not be empty")
    if len(ops) > MAX_OPS_PER_BATCH:
        raise WorldStateError(f"world ops exceed {MAX_OPS_PER_BATCH} entries")
    draft = _validated_copy(getattr(instance, "world_state", None))
    revision = int(draft["revision"]) + 1
    round_number = _source_round(instance, source_round)
    applied: list[dict[str, Any]] = []
    for position, raw in enumerate(ops):
        applied.append(_apply_op(
            draft, raw, revision=revision, source_round=round_number,
            position=position, inside_event=False,
        ))
    if len(draft["facts"]) > MAX_FACTS:
        raise WorldStateError(f"world state exceeds {MAX_FACTS} facts")
    if len(draft["scheduled_events"]) > MAX_SCHEDULED_EVENTS:
        raise WorldStateError(
            f"world state exceeds {MAX_SCHEDULED_EVENTS} scheduled events"
        )
    draft["revision"] = revision
    # 持久化形状按 canonical key 排序：存档 diff 与测试断言都不依赖插入顺序。
    draft["facts"] = {key: draft["facts"][key] for key in sorted(draft["facts"])}
    draft["scheduled_events"] = {
        key: draft["scheduled_events"][key] for key in sorted(draft["scheduled_events"])
    }
    instance.world_state = draft
    return {
        "revision": revision,
        "clock": dict(draft["clock"]),
        "applied": applied,
    }


def _source_round(instance: Any, source_round: int | None) -> int:
    value = source_round if source_round is not None else getattr(instance, "round_number", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _validated_copy(state: Any) -> dict[str, Any]:
    """Validate the stored container and return a detached mutable draft."""

    payload = _current_payload(state)
    if payload is None:
        raw_version = state.get("schema_version") if isinstance(state, Mapping) else None
        if raw_version is not None and raw_version != WORLD_STATE_SCHEMA_VERSION:
            raise WorldStateError(
                f"unsupported world state schema: {raw_version!r}"
            )
        raise WorldStateError("world state is missing or malformed")
    draft = deepcopy(dict(payload))
    revision = draft.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise WorldStateError("world state revision is invalid")
    clock = draft.get("clock")
    if (
        not isinstance(clock, Mapping)
        or _instant_minutes(clock, "clock") is None
    ):
        raise WorldStateError("world state clock is invalid")
    facts = draft.get("facts")
    if not isinstance(facts, Mapping):
        raise WorldStateError("world state facts must be an object")
    for key, fact in facts.items():
        if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
            raise WorldStateError(f"world state fact key is invalid: {key!r}")
        if not isinstance(fact, Mapping) or "value" not in fact:
            raise WorldStateError(f"world state fact is invalid: {key!r}")
        if fact.get("visibility") not in FACT_VISIBILITIES:
            raise WorldStateError(f"world state fact visibility is invalid: {key!r}")
    events = draft.get("scheduled_events")
    if not isinstance(events, Mapping):
        raise WorldStateError("world state scheduled_events must be an object")
    for key, event in events.items():
        if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
            raise WorldStateError(f"scheduled event key is invalid: {key!r}")
        if not isinstance(event, Mapping) or event.get("event_id") != key:
            raise WorldStateError(f"scheduled event is invalid: {key!r}")
        if event.get("status") not in EVENT_STATUSES:
            raise WorldStateError(f"scheduled event status is invalid: {key!r}")
        if _instant_minutes(event.get("due_at"), "due_at") is None:
            raise WorldStateError(f"scheduled event due_at is invalid: {key!r}")
        event_ops = event.get("ops")
        if not isinstance(event_ops, list) or not event_ops:
            raise WorldStateError(f"scheduled event ops are invalid: {key!r}")
    draft["facts"] = dict(facts)
    draft["scheduled_events"] = dict(events)
    draft["clock"] = dict(clock)
    return draft


def _apply_op(
    draft: dict[str, Any],
    raw: Any,
    *,
    revision: int,
    source_round: int,
    position: int,
    inside_event: bool,
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise WorldStateError(f"world op #{position} must be an object")
    kind = raw.get("op")
    if kind not in OP_KINDS:
        raise WorldStateError(f"unknown world op: {kind!r}")
    if inside_event and kind not in EVENT_OP_KINDS:
        raise WorldStateError(f"scheduled event ops cannot use {kind!r}")
    if kind == "set_fact":
        return _op_set_fact(draft, raw, revision=revision, source_round=source_round, position=position)
    if kind == "remove_fact":
        return _op_remove_fact(draft, raw, position=position)
    if kind == "advance_time":
        return _op_advance_time(draft, raw, position=position)
    if kind == "schedule_event":
        return _op_schedule_event(draft, raw, revision=revision, position=position)
    return _op_cancel_event(draft, raw, position=position)


def _op_set_fact(
    draft: dict[str, Any], raw: Mapping[str, Any], *,
    revision: int, source_round: int, position: int,
) -> dict[str, Any]:
    _reject_unknown_fields(raw, {"op", "key", "value", "visibility"}, position)
    key = _fact_key(raw.get("key"), position)
    value = _fact_value(raw.get("value"), key)
    facts = draft["facts"]
    previous = facts.get(key)
    declared = raw.get("visibility")
    if declared is None:
        # 更新已有事实时不写 visibility 就沿用原值：缺失字段不能让一条 GM 私有
        # 事实因为一次数值更新而意外变成公开事实。
        visibility = str(previous["visibility"]) if isinstance(previous, Mapping) else "public"
    else:
        visibility = _visibility(declared, position)
    facts[key] = {
        "value": value,
        "visibility": visibility,
        "source_round": source_round,
        "updated_revision": revision,
    }
    return {
        "op": "set_fact",
        "key": key,
        "created": not isinstance(previous, Mapping),
        "visibility": visibility,
    }


def _op_remove_fact(
    draft: dict[str, Any], raw: Mapping[str, Any], *, position: int,
) -> dict[str, Any]:
    _reject_unknown_fields(raw, {"op", "key"}, position)
    key = _fact_key(raw.get("key"), position)
    if key not in draft["facts"]:
        raise WorldStateError(f"world op #{position} removes an unknown fact: {key!r}")
    draft["facts"].pop(key)
    return {"op": "remove_fact", "key": key}


def _op_advance_time(
    draft: dict[str, Any], raw: Mapping[str, Any], *, position: int,
) -> dict[str, Any]:
    _reject_unknown_fields(raw, {"op", "minutes"}, position)
    minutes = raw.get("minutes")
    if (
        isinstance(minutes, bool) or not isinstance(minutes, int)
        or not 0 < minutes <= MAX_ADVANCE_MINUTES
    ):
        raise WorldStateError(
            f"world op #{position} needs 1..{MAX_ADVANCE_MINUTES} minutes"
        )
    total = _instant_minutes(draft["clock"], "clock")
    if total is None:  # pragma: no cover - _validated_copy already checked
        raise WorldStateError("world state clock is invalid")
    clock = _clock_from_minutes(total + minutes, position)
    draft["clock"] = clock
    # 到期的 scheduled_events 不在这里结算：本 work package 只维护数据容器，
    # 定时结算由后续 work package 在同一写入口上实现。
    return {"op": "advance_time", "minutes": minutes, "clock": dict(clock)}


def _op_schedule_event(
    draft: dict[str, Any], raw: Mapping[str, Any], *, revision: int, position: int,
) -> dict[str, Any]:
    _reject_unknown_fields(
        raw, {"op", "event_id", "due_at", "ops", "label", "status"}, position,
    )
    event_id = _event_id(raw.get("event_id"), position)
    events = draft["scheduled_events"]
    if event_id in events:
        raise WorldStateError(f"world op #{position} reuses event id: {event_id!r}")
    due_at = _instant(raw.get("due_at"), position)
    now = _instant_minutes(draft["clock"], "clock")
    if now is None:  # pragma: no cover - _validated_copy already checked
        raise WorldStateError("world state clock is invalid")
    if _instant_minutes(due_at, "due_at") <= now:
        raise WorldStateError(
            f"world op #{position} schedules an event in the past: {event_id!r}"
        )
    raw_ops = raw.get("ops")
    if not isinstance(raw_ops, list) or not raw_ops:
        raise WorldStateError(f"world op #{position} event needs non-empty ops")
    if len(raw_ops) > MAX_OPS_PER_BATCH:
        raise WorldStateError(
            f"world op #{position} event exceeds {MAX_OPS_PER_BATCH} ops"
        )
    # 事件 ops 在调度时就按当前状态校验一次（fail closed），但只写入 scratch
    # 副本：引用合法性以结算时刻的状态为准。
    scratch = deepcopy(draft)
    for nested_position, nested in enumerate(raw_ops):
        _apply_op(
            scratch, nested, revision=revision, source_round=0,
            position=nested_position, inside_event=True,
        )
    label = raw.get("label", "")
    if label is None:
        label = ""
    if not isinstance(label, str) or len(label) > MAX_LABEL_CHARS:
        raise WorldStateError(f"world op #{position} event label is invalid")
    status = raw.get("status", "pending")
    if status != "pending":
        raise WorldStateError(
            f"world op #{position} can only schedule a pending event"
        )
    events[event_id] = {
        "event_id": event_id,
        "due_at": due_at,
        "status": "pending",
        "label": label,
        "ops": [deepcopy(dict(item)) for item in raw_ops],
    }
    return {"op": "schedule_event", "event_id": event_id, "due_at": dict(due_at)}


def _op_cancel_event(
    draft: dict[str, Any], raw: Mapping[str, Any], *, position: int,
) -> dict[str, Any]:
    _reject_unknown_fields(raw, {"op", "event_id"}, position)
    event_id = _event_id(raw.get("event_id"), position)
    event = draft["scheduled_events"].get(event_id)
    if not isinstance(event, Mapping):
        raise WorldStateError(f"world op #{position} cancels an unknown event: {event_id!r}")
    if event.get("status") != "pending":
        raise WorldStateError(
            f"world op #{position} cancels a non-pending event: {event_id!r}"
        )
    event["status"] = "cancelled"
    return {"op": "cancel_event", "event_id": event_id}


# ---- 字段校验 -------------------------------------------------------------


def _reject_unknown_fields(raw: Mapping[str, Any], allowed: set[str], position: int) -> None:
    extra = sorted(str(key) for key in raw if key not in allowed)
    if extra:
        raise WorldStateError(f"world op #{position} has unknown field: {extra[0]!r}")


def _fact_key(value: Any, position: int) -> str:
    if not isinstance(value, str) or not _KEY_RE.fullmatch(value):
        raise WorldStateError(f"world op #{position} fact key is invalid: {value!r}")
    return value


def _event_id(value: Any, position: int) -> str:
    if not isinstance(value, str) or not _KEY_RE.fullmatch(value):
        raise WorldStateError(f"world op #{position} event id is invalid: {value!r}")
    return value


def _visibility(value: Any, position: int) -> str:
    if value not in FACT_VISIBILITIES:
        raise WorldStateError(f"world op #{position} visibility is invalid: {value!r}")
    return str(value)


def _fact_value(value: Any, key: str) -> Any:
    """Fact values are scalars only: no entity graph, no nested structures."""

    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if not -MAX_ABSOLUTE_INT <= value <= MAX_ABSOLUTE_INT:
            raise WorldStateError(f"fact value is out of range: {key!r}")
        return value
    if isinstance(value, str):
        if len(value) > MAX_STRING_CHARS:
            raise WorldStateError(f"fact value is too long: {key!r}")
        if any(character < " " and character not in "\t" for character in value):
            raise WorldStateError(f"fact value has control characters: {key!r}")
        return value
    raise WorldStateError(f"fact value must be a string, integer, or boolean: {key!r}")


def _instant(value: Any, position: int) -> dict[str, int]:
    minutes = _instant_minutes(value, f"world op #{position} due_at")
    if minutes is None:
        raise WorldStateError(f"world op #{position} due_at is invalid: {value!r}")
    return _clock_from_minutes(minutes, position)


def _instant_minutes(value: Any, field: str) -> int | None:
    """Convert ``{"day": n, "minute": m}`` into absolute logical minutes."""

    if not isinstance(value, Mapping):
        return None
    day, minute = value.get("day"), value.get("minute")
    if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= MAX_CLOCK_DAY:
        return None
    if isinstance(minute, bool) or not isinstance(minute, int):
        return None
    if not 0 <= minute < MINUTES_PER_DAY:
        return None
    return (day - 1) * MINUTES_PER_DAY + minute


def _clock_from_minutes(total: int, position: int) -> dict[str, int]:
    if total < 0:
        raise WorldStateError(f"world op #{position} moves the clock before day 1")
    day, minute = divmod(total, MINUTES_PER_DAY)
    day += 1
    if day > MAX_CLOCK_DAY:
        raise WorldStateError(f"world op #{position} moves the clock too far")
    return {"day": day, "minute": minute}


__all__ = [
    "EVENT_STATUSES",
    "FACT_VISIBILITIES",
    "OP_KINDS",
    "WORLD_STATE_SCHEMA_VERSION",
    "WorldStateError",
    "apply_world_ops",
    "ensure_world_state",
    "fact_value",
    "fresh_world_state",
    "world_clock",
    "world_facts",
    "world_revision",
    "world_scheduled_events",
]
