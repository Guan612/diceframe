"""Relationship tracks: subject × target → dimension values + stage (schema v1).

通用的"主体 × 对象 → 多维数值 + 阶段"权威状态，不绑定恋爱玩法；可复用于
阵营声望、剧本杀嫌疑度等。维度、阶段与门槛由规则模板的 ``relationship_schema``
声明（数据），本模块只实现通用语义：

- 写入只经 :meth:`apply_changes`（REL 标签 applier 调用）：钳制 min/max 与
  ``per_round_cap``，维度/对象必须已声明；
- 阶段由引擎按声明顺序重新计算，模型不能直接设置；``stage_mode: monotonic``
  只升不降，``derived`` 跟随数值；``requires_milestone`` 的阶段还需要冒险图
  对应里程碑已完成（证据不足 = 不可进入，fail closed）；
- 每条 delta 记入 track 内有界 history，回退/回滚按轮次精确反向恢复；
- 可见性：``party`` / ``self`` / ``gm`` / ``hidden``（数值连 GM 也不看，只留
  给引擎与门控）；座位投影按维度过滤，GM 投影全量（hidden 维度除外）。

不支持的 slot schema 原样保留、读取失败：不猜测解释未来数据。
"""

from __future__ import annotations

import logging
import time
import uuid

from typing import Any

from src.engine import module_hooks, progression
from src.engine.module_state import ModuleStateSpec, get_module_state, register_module_state

logger = logging.getLogger("trpg")

MODULE_NAME = "relationships"
SCHEMA_VERSION = 1

MAX_DIMENSIONS = 6
MAX_STAGES = 8
MAX_TARGETS = 24
MAX_HISTORY_PER_TRACK = 200
VISIBILITIES = ("party", "self", "gm", "hidden")
STAGE_MODES = ("monotonic", "derived")


def fresh() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "tracks": {}}


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    if not isinstance(raw.get("tracks"), dict):
        raw["tracks"] = {}
    return raw


def state(instance: Any) -> dict[str, Any]:
    slot = get_module_state(instance, MODULE_NAME)
    if not isinstance(slot.get("tracks"), dict):
        raise ValueError("invalid relationship tracks")
    return slot


# ---------------------------------------------------------------------------
# schema 声明解析（规则模板 relationship_schema → 规范化结构）
# ---------------------------------------------------------------------------


def parse_relationship_schema(raw: Any) -> dict[str, Any] | None:
    """规范化规则模板里的 ``relationship_schema``；未声明返回 None。

    结构非法时抛 ValueError：供内容校验与测试直接使用；运行时经
    :meth:`schema_for` 走降级路径（告警 + 视为未配置），不让一条坏 schema
    拖垮整局游戏。
    """

    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("relationship_schema must be an object")
    dims_raw = raw.get("dimensions")
    stages_raw = raw.get("stages")
    if not isinstance(dims_raw, list) or not dims_raw:
        raise ValueError("relationship_schema requires dimensions")
    if len(dims_raw) > MAX_DIMENSIONS:
        raise ValueError(f"relationship_schema exceeds {MAX_DIMENSIONS} dimensions")
    dimensions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for dim in dims_raw:
        if not isinstance(dim, dict):
            raise ValueError("relationship dimension must be an object")
        key = str(dim.get("key") or "").strip()
        if not key or not key.isidentifier() or key in seen:
            raise ValueError(f"invalid or duplicate relationship dimension key: {key!r}")
        seen.add(key)
        try:
            lo = int(dim.get("min", 0))
            hi = int(dim.get("max", 100))
            default = int(dim.get("default", lo))
            cap = int(dim.get("per_round_cap", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"relationship dimension {key!r} bounds must be integers") from exc
        if not lo <= default <= hi:
            raise ValueError(f"relationship dimension {key!r} default outside min/max")
        if cap < 0 or cap > 100:
            raise ValueError(f"relationship dimension {key!r} per_round_cap out of range")
        visibility = str(dim.get("visibility") or "gm")
        if visibility not in VISIBILITIES:
            raise ValueError(f"relationship dimension {key!r} visibility unsupported: {visibility!r}")
        dimensions.append({
            "key": key,
            "label": str(dim.get("label") or key),
            "min": lo,
            "max": hi,
            "default": default,
            "per_round_cap": cap,
            "visibility": visibility,
        })
    stage_mode = str(raw.get("stage_mode") or "monotonic")
    if stage_mode not in STAGE_MODES:
        raise ValueError(f"relationship stage_mode unsupported: {stage_mode!r}")
    stages: list[dict[str, Any]] = []
    if stages_raw is not None:
        if not isinstance(stages_raw, list):
            raise ValueError("relationship stages must be an array")
        if len(stages_raw) > MAX_STAGES:
            raise ValueError(f"relationship_schema exceeds {MAX_STAGES} stages")
        order: dict[str, int] = {}
        for stage in stages_raw:
            if not isinstance(stage, dict):
                raise ValueError("relationship stage must be an object")
            key = str(stage.get("key") or "").strip()
            if not key or not key.isidentifier() or key in order:
                raise ValueError(f"invalid or duplicate relationship stage key: {key!r}")
            enter_raw = stage.get("enter") or {}
            if not isinstance(enter_raw, dict):
                raise ValueError(f"relationship stage {key!r} enter must be an object")
            enter: dict[str, dict[str, int]] = {}
            for dim_key, threshold in enter_raw.items():
                if dim_key not in seen:
                    raise ValueError(f"relationship stage {key!r} gates unknown dimension: {dim_key!r}")
                if not isinstance(threshold, dict):
                    raise ValueError(f"relationship stage {key!r} threshold must be an object")
                try:
                    enter[str(dim_key)] = {"gte": int(threshold["gte"])}
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"relationship stage {key!r} threshold for {dim_key!r} requires integer gte"
                    ) from exc
            milestone = stage.get("requires_milestone")
            if milestone is not None and not (isinstance(milestone, str) and milestone.strip()):
                raise ValueError(f"relationship stage {key!r} requires_milestone must be a milestone id")
            order[key] = len(stages)
            stages.append({
                "key": key,
                "label": str(stage.get("label") or key),
                "enter": enter,
                "requires_milestone": str(milestone).strip() if milestone else "",
            })
    targets_raw = raw.get("targets")
    targets: list[str] = []
    if targets_raw is not None:
        if not isinstance(targets_raw, list) or len(targets_raw) > MAX_TARGETS:
            raise ValueError("relationship targets must be a bounded array")
        for target in targets_raw:
            text = str(target or "").strip()
            if not text or len(text) > 128 or text in targets:
                raise ValueError(f"invalid or duplicate relationship target: {target!r}")
            targets.append(text)
    return {"dimensions": dimensions, "stages": stages, "stage_mode": stage_mode, "targets": targets}


def schema_for(instance: Any, rule: Any) -> dict[str, Any] | None:
    """从当前规则读取并解析 relationship_schema；规则缺席即能力未配置。"""

    if rule is None:
        return None
    try:
        raw = rule.relationship_schema
    except AttributeError:
        return None
    try:
        return parse_relationship_schema(raw)
    except ValueError:
        logger.warning("relationship_schema 非法，能力视为未配置: %s", getattr(rule, "rule_id", "?"), exc_info=True)
        return None


def publish_schema(instance: Any, rule: Any) -> None:
    """把当前规则的关系 schema 快照进槽（GM prompt 注入的数据源）。

    由非核心流程的 applier 每轮调用；核心流程只经 module_hooks 读，
    不点名本模块。首轮模型调用早于第一次 applier 时块缺席，属预期冷启动。
    """

    schema = schema_for(instance, rule)
    try:
        slot = state(instance)
    except ValueError:
        return
    if schema is None:
        slot.pop("schema", None)
    else:
        slot["schema"] = schema


def _published_schema(instance: Any) -> dict[str, Any] | None:
    try:
        schema = state(instance).get("schema")
    except ValueError:
        return None
    return schema if isinstance(schema, dict) and schema.get("dimensions") else None


def _dimension(schema: dict[str, Any], key: str) -> dict[str, Any] | None:
    for dim in schema["dimensions"]:
        if dim["key"] == key:
            return dim
    return None


def _stage_order(schema: dict[str, Any]) -> dict[str, int]:
    return {stage["key"]: index for index, stage in enumerate(schema["stages"])}


def _default_stage(schema: dict[str, Any]) -> str:
    return schema["stages"][0]["key"] if schema["stages"] else ""


def _stage_satisfied(stage: dict[str, Any], values: dict[str, int], milestones: set[str]) -> bool:
    for dim_key, bound in stage["enter"].items():
        if values.get(dim_key, 0) < bound["gte"]:
            return False
    milestone = stage["requires_milestone"]
    if milestone and milestone not in milestones:
        return False
    return True


def _computed_stage(schema: dict[str, Any], values: dict[str, int], milestones: set[str]) -> str:
    current = _default_stage(schema)
    for stage in schema["stages"]:
        if _stage_satisfied(stage, values, milestones):
            current = stage["key"]
    return current


# ---------------------------------------------------------------------------
# 写入（唯一权威路径：REL 标签 applier）
# ---------------------------------------------------------------------------


def apply_changes(
    instance: Any,
    subject_uid: str,
    changes: dict[str, dict[str, int]],
    schema: dict[str, Any],
    milestones: set[str] | None = None,
) -> list[dict[str, str]]:
    """对一个主体应用一批 {target: {dimension: delta}} 变化。

    只接受已声明的对象与维度；delta 钳制到 min/max，单轮累计钳制到
    ``per_round_cap``（0 = 不限）。阶段由引擎按声明顺序重算。返回发生阶段
    变化的通知列表（同时已作为下一轮 GM 指令下发）。
    """

    if not isinstance(changes, dict) or not changes:
        return []
    milestones = milestones or set()
    slot = state(instance)
    round_no = progression.current_round(instance)
    tracks = slot["tracks"].setdefault(str(subject_uid), {})
    notices: list[dict[str, str]] = []
    for target, deltas in changes.items():
        target = str(target or "")
        if schema["targets"] and target not in schema["targets"]:
            logger.warning("REL 对象未声明，已忽略: %s %s", subject_uid, target)
            continue
        if not isinstance(deltas, dict):
            continue
        existing = tracks.get(target)
        values: dict[str, int] = (
            {str(k): int(v) for k, v in (existing.get("values") or {}).items()}
            if isinstance(existing, dict) else
            {dim["key"]: dim["default"] for dim in schema["dimensions"]}
        )
        history: list[dict[str, Any]] = (
            list(existing.get("history") or []) if isinstance(existing, dict) else []
        )
        stage_before = str((existing or {}).get("stage") or _default_stage(schema))
        applied_any = False
        for dim_key, delta in deltas.items():
            dim = _dimension(schema, str(dim_key))
            if dim is None:
                logger.warning("REL 维度未声明，已忽略: %s %s", subject_uid, dim_key)
                continue
            if not isinstance(delta, int):
                continue
            current = int(values.get(dim["key"], dim["default"]))
            applied = delta
            cap = int(dim["per_round_cap"])
            if cap:
                # 单轮上限按带符号累计：本轮已用 |Σd|，剩余额度内钳制。
                used = sum(
                    int(entry["d"]) for entry in history
                    if entry["r"] == round_no and entry["dim"] == dim["key"]
                )
                headroom = max(0, cap - abs(used))
                applied = max(-headroom, min(headroom, applied))
            applied = max(dim["min"] - current, min(dim["max"] - current, applied))
            if applied == 0:
                continue
            values[dim["key"]] = current + applied
            history.append({"r": round_no, "dim": dim["key"], "d": applied, "sb": stage_before})
            applied_any = True
        if not applied_any:
            # 无有效 delta 不物化 track：拒绝批次不留默认值残影。
            if existing is None:
                continue
            tracks[target] = existing
            continue
        if len(history) > MAX_HISTORY_PER_TRACK:
            del history[: len(history) - MAX_HISTORY_PER_TRACK]
        computed = _computed_stage(schema, values, milestones)
        if schema["stage_mode"] == "monotonic":
            order = _stage_order(schema)
            new_stage = computed if order.get(computed, -1) > order.get(stage_before, -1) else stage_before
        else:
            new_stage = computed
        tracks[target] = {
            "values": values,
            "stage": new_stage,
            "updated_round": round_no,
            "history": history,
        }
        if new_stage != stage_before:
            notices.append(_notify_stage_change(instance, subject_uid, target, schema, stage_before, new_stage))
    if not tracks:
        slot["tracks"].pop(str(subject_uid), None)
    return notices


def _notify_stage_change(
    instance: Any, subject_uid: str, target: str,
    schema: dict[str, Any], before: str, after: str,
) -> dict[str, str]:
    labels = {stage["key"]: stage["label"] for stage in schema["stages"]}
    text = (
        f"【关系阶段】{subject_uid} 对 {target} 的关系阶段变化："
        f"{labels.get(before, before)} → {labels.get(after, after)}。"
        "请在下一轮叙事中体现新阶段的语气与边界，不要直接复述数值。"
    )
    instance.add_gm_directive({
        "id": uuid.uuid4().hex,
        "text": text,
        "created_at": time.time(),
        "target_round": progression.current_round(instance) + 1,
    })
    return {"subject": str(subject_uid), "target": target, "from": before, "to": after}


def rewind(instance: Any, target_round: int) -> None:
    """回退到 target_round：按 history 反向恢复被丢弃轮次的 delta 与阶段。"""

    try:
        slot = state(instance)
    except ValueError:
        return  # 未来/损坏 slot 原样保留，不猜测。
    for tracks in slot["tracks"].values():
        if not isinstance(tracks, dict):
            continue
        for target in list(tracks):
            track = tracks.get(target)
            history = track.get("history") if isinstance(track, dict) else None
            if not isinstance(history, list):
                continue
            restore_stage = None
            while history and int(history[-1].get("r", 0)) > target_round:
                entry = history.pop()
                dim = str(entry.get("dim") or "")
                delta = entry.get("d")
                if dim and isinstance(delta, int):
                    values = track.setdefault("values", {})
                    values[dim] = int(values.get(dim, 0)) - delta
                # 目标轮次的阶段 = 最早被丢弃那条 delta 之前的阶段；
                # 持续覆盖，循环结束后留下的即最早条目的 sb。
                if isinstance(entry.get("sb"), str):
                    restore_stage = entry["sb"]
            if not history:
                # track 只由非零 delta 物化：history 清空 = 全部反毕，删除 track。
                tracks.pop(target, None)
                continue
            if restore_stage is not None:
                track["stage"] = restore_stage


def reset(instance: Any) -> None:
    try:
        slot = state(instance)
    except ValueError:
        return  # 未来 slot 保留，不重置成猜测的形状。
    slot["tracks"] = {}


# ---------------------------------------------------------------------------
# 读取投影
# ---------------------------------------------------------------------------


def seat_view(instance: Any, schema: dict[str, Any], uid: str) -> dict[str, Any]:
    """主体自己的视图：阶段全可见，数值按维度 visibility 过滤。"""

    tracks = state(instance)["tracks"].get(str(uid), {})
    view: dict[str, Any] = {}
    for target, track in tracks.items():
        if not isinstance(track, dict):
            continue
        row: dict[str, Any] = {"stage": str(track.get("stage") or "")}
        values = track.get("values") or {}
        shown: dict[str, int] = {}
        for dim in schema["dimensions"]:
            if dim["visibility"] in ("party", "self") and dim["key"] in values:
                shown[dim["key"]] = int(values[dim["key"]])
        if shown:
            row["values"] = shown
        view[str(target)] = row
    return view


def gm_view(instance: Any, schema: dict[str, Any]) -> dict[str, Any]:
    """GM 视图：全部主体与阶段；数值除 hidden 维度外全可见。"""

    result: dict[str, Any] = {}
    for uid, tracks in state(instance)["tracks"].items():
        view: dict[str, Any] = {}
        for target, track in tracks.items():
            if not isinstance(track, dict):
                continue
            row: dict[str, Any] = {"stage": str(track.get("stage") or "")}
            values = track.get("values") or {}
            shown = {
                dim["key"]: int(values[dim["key"]])
                for dim in schema["dimensions"]
                if dim["visibility"] != "hidden" and dim["key"] in values
            }
            if shown:
                row["values"] = shown
            view[str(target)] = row
        if view:
            result[str(uid)] = view
    return result


def gm_context_block(instance: Any, rule: Any = None) -> str:
    """给叙事模型的关系状态块（GM 权威视角，hidden 维度只给阶段）。

    rule 提供时即时解析；否则读 applier 发布的槽内快照。
    """

    schema = schema_for(instance, rule) if rule is not None else _published_schema(instance)
    if schema is None:
        return ""
    view = gm_view(instance, schema)
    dim_labels = {dim["key"]: dim["label"] for dim in schema["dimensions"]}
    stage_labels = {stage["key"]: stage["label"] for stage in schema["stages"]}
    lines: list[str] = []
    for uid, tracks in view.items():
        for target, row in tracks.items():
            parts = [f"{dim_labels.get(key, key)} {value}" for key, value in (row.get("values") or {}).items()]
            stage = stage_labels.get(row.get("stage", ""), row.get("stage", ""))
            detail = f"（{'，'.join(parts)}）" if parts else ""
            lines.append(f"- {uid} → {target}：阶段〔{stage}〕{detail}")
    header = "## Relationship State（引擎权威数值，仅供叙事参考，禁止在正文直接复述数字）"
    body = "\n".join(lines) if lines else "（暂无记录：关系尚未建立）"
    usage = (
        "关系变化必须通过状态标签输出：REL:玩家ID:对象ID:维度:变化量"
        "（只写数值变化，阶段由引擎判定；对象与维度须使用上方出现过的名称）"
    )
    return header + "\n" + body + "\n" + usage


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)


def _on_rewind_restore(instance: Any, entry: Any, target_round: Any, source: Any) -> None:
    rewind(instance, int(target_round))


def _on_round_abort(instance: Any) -> bool:
    """判定失败：反向结算本轮已应用的关系 delta，回答是否恢复了东西。"""

    round_no = progression.current_round(instance)
    touched = False
    try:
        slot = state(instance)
    except ValueError:
        return False
    for tracks in slot["tracks"].values():
        if not isinstance(tracks, dict):
            continue
        for track in tracks.values():
            history = track.get("history")
            if isinstance(history, list) and any(
                isinstance(entry, dict) and int(entry.get("r", 0)) == round_no for entry in history
            ):
                touched = True
    rewind(instance, round_no - 1)
    return touched


def _read_state(instance: Any, kind: str) -> Any:
    if kind == module_hooks.GM_PROMPT_SECTIONS:
        block = gm_context_block(instance)
        return [block] if block else []
    return None


module_hooks.register(module_hooks.INSTANCE_RESET, MODULE_NAME, reset)
module_hooks.register(module_hooks.ROUND_REWIND_RESTORE, MODULE_NAME, _on_rewind_restore)
module_hooks.register(module_hooks.ROUND_ABORT, MODULE_NAME, _on_round_abort)
module_hooks.register(module_hooks.STATE_READ, MODULE_NAME, _read_state)


__all__ = [
    "MODULE_NAME",
    "SCHEMA_VERSION",
    "apply_changes",
    "gm_context_block",
    "gm_view",
    "parse_relationship_schema",
    "publish_schema",
    "reset",
    "rewind",
    "schema_for",
    "seat_view",
]
