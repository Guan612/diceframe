"""Authoritative execution of adventure world seeds (WR-09).

母方案 §26/§27 的 **engine 侧执行半区**：把
``src.adventures.materialization.world_seed_ops`` 推导出的初始种子 op 经
既有唯一写入口 ``apply_world_ops`` 提交，并产出物化 receipt。

- Adventure（定义层）不直接写 authority；只有这里（engine 侧显式适配器）
  触碰世界。
- **幂等**（母方案 §27 MUST）：以 canonical world entity id 为键，已存在的
  实体跳过；重放/重启后重复物化只补缺失的 id，不报错、不重复创建。
- receipt 形状：``{adventure_id, content_digest, created_entity_ids,
  skipped_entity_ids}``。
"""

from __future__ import annotations

from typing import Any

from src.adventures.bundle import LoadedAdventureBundle
from src.adventures.materialization import MAX_OPS_PER_BATCH, world_seed_ops
from src.engine.world_state import (
    apply_ops_to_state,
    world_entities,
    world_facts,
    world_processes,
    world_relations,
)


def _source_round(instance: Any, explicit: int | None) -> int:
    if explicit is not None:
        try:
            return int(explicit)
        except (TypeError, ValueError):
            return 0
    try:
        return int(getattr(instance, "round_number", 0) or 0)
    except (TypeError, ValueError):
        return 0


def materialize_world_seed(
    instance: Any,
    bundle: LoadedAdventureBundle,
    *,
    source_round: int | None = None,
) -> dict[str, Any]:
    """Materialize a bundle's initial world seed; idempotent."""

    existing = world_entities(instance.world_state)
    existing_relations = world_relations(instance.world_state)
    created: list[str] = []
    skipped: list[str] = []
    pending: list[dict[str, Any]] = []
    for op in world_seed_ops(bundle):
        # 幂等键：register_entity/add_relation 按 id 跳过已存在的；fact /
        # process 种子（set_fact/start_process）没有独立 id 身份，重放语义
        # 由 op 本身的幂等性保证（set_fact 幂等；start_process 重 id 拒绝——
        # 即重放会命中已存在进程并被跳过到 receipt 的 skipped 之外，行为是
        # "不重复创建"）。
        if op["op"] == "register_entity":
            entity_id = str(op["entity_id"])
            if entity_id in existing:
                skipped.append(entity_id)
                continue
            pending.append(op)
        elif op["op"] == "add_relation":
            relation_id = str(op["relation_id"])
            if relation_id in world_relations(instance.world_state) or relation_id in existing_relations:
                skipped.append(relation_id)
                continue
            pending.append(op)
        elif op["op"] == "start_process":
            if str(op.get("process_id") or "") in world_processes(instance.world_state):
                skipped.append(str(op.get("process_id") or ""))
                continue
            pending.append(op)
        elif op["op"] == "set_fact":
            current = world_facts(instance.world_state).get(str(op.get("key") or ""))
            if (
                current is not None
                and current.get("value") == op.get("value")
                and str(current.get("visibility") or "public")
                == str(op.get("visibility") or "public")
            ):
                # 相同值/可见性的事实重放 = 无操作（幂等，不推进 revision）。
                skipped.append(str(op.get("key") or ""))
                continue
            pending.append(op)
        else:
            pending.append(op)

    # FIX-04 §6.6：**不要**逐批提交（"64 ops commit, 64 ops commit, 失败"会在
    # 世界里留下半个种子）。先把所有批次叠加到同一份 detached draft 上校验，
    # 全部通过后才对 instance 做**唯一一次**提交；任何一步失败都不会改动世界。
    draft: dict[str, Any] | None = None
    for start in range(0, len(pending), MAX_OPS_PER_BATCH):
        batch = pending[start:start + MAX_OPS_PER_BATCH]
        draft, _summary = apply_ops_to_state(
            draft if draft is not None else instance.world_state,
            batch,
            source_round=_source_round(instance, source_round),
        )
        created.extend(
            str(op.get("entity_id") or op.get("relation_id") or op.get("key") or op.get("process_id") or "")
            for op in batch
        )
    if draft is not None:
        instance.world_state = draft

    return {
        "adventure_id": str(bundle.manifest.adventure_id),
        "content_digest": str(bundle.content_digest),
        "created_entity_ids": created,
        "skipped_entity_ids": skipped,
    }


__all__ = ["materialize_world_seed"]
