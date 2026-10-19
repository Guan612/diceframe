"""P3：节点完成模式（completion: gm 默认 | auto）与引擎自动结算。

覆盖：图契约的 completion 字段（缺省不物化、非法值 fail closed）、初始化即
结算 auto 入口节点、人工完成命令级联结算 auto 后继（同一命令内）、门控后开
的 auto 节点经 advance_adventure_world 结算、auto 事务的 world 后果真实落
地、默认 gm 节点行为不变。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.adventures import AdventureResolver
from src.adventures.graph_v2 import AdventureGraphV2Error, validate_graph_v2
from src.engine.game_instance import GameInstance
from src.engine.modules import adventure_runtime_state
from src.engine.world_state import apply_world_ops, world_facts
from src.webui.services import adventure_runtime
from src.webui.services.adventure_materialization import materialize_world_seed

PACKAGE_ID = "v2_auto"
ADVENTURE_ID = "user:v2_auto"
WORLD_ID = "autoworld"


def _graph(**overrides: object) -> dict:
    record: dict = {
        "id": PACKAGE_ID,
        "format": "diceframe:adventure-graph-v2",
        "chapters": [{"id": "ch1", "name": "第一章"}],
        "nodes": [
            {
                "id": "entry", "type": "scene", "chapter_id": "ch1",
                "on_complete": [
                    {"type": "world_op", "op": {"op": "set_fact", "key": "stage.done", "value": True}},
                ],
                # watch 立即开放；settle 的门控挂在已完成节点的出边上，
                # 由 advance_adventure_world 在门控晚满足时开放（§6.8）。
                "transitions": [
                    {"to": "watch"},
                    {"to": "settle", "conditions": [
                        {"type": "world.fact_equals", "key": "clock.day14", "value": True},
                    ]},
                ],
            },
            {
                "id": "watch", "type": "scene", "chapter_id": "ch1",
                "transitions": [],
            },
            {
                "id": "settle", "type": "scene", "chapter_id": "ch1", "completion": "auto",
                "on_complete": [
                    {"type": "world_op", "op": {"op": "set_fact", "key": "finale.settled", "value": True}},
                ],
                "transitions": [{"to": "epilogue"}],
            },
            {"id": "epilogue", "type": "scene", "chapter_id": "ch1", "transitions": []},
        ],
        "objectives": [{"id": "obj_entry", "name": "开局", "node_ids": ["entry"]}],
        "milestones": [{"id": "mile_settle", "name": "结算", "node_ids": ["settle"]}],
        "start_node_ids": ["entry"],
    }
    record.update(overrides)
    return record


def _install(tmp_path: Path, graph: dict) -> AdventureResolver:
    root = tmp_path / "adventures"
    package = root / PACKAGE_ID
    files = {
        "manifest.json": json.dumps({
            "schema_version": 1, "adventure_id": ADVENTURE_ID, "version": "1.0.0",
            "format": "diceframe:adventure-graph-v2", "world_policy": "portable",
            "recommended_world_id": WORLD_ID,
            "required_runtime": {"id": "core:dnd2024", "minimum_version": 1},
            "default_locale": "zh-CN", "supported_locales": ["zh-CN"],
        }, ensure_ascii=False).encode("utf-8"),
        "locales/zh-CN/adventure.json": json.dumps({
            "locale_schema_version": 1, "locale": "zh-CN",
            "target": {"kind": "adventure", "id": PACKAGE_ID},
            "fields": {"tutorial": {"name": "auto 冒险", "summary": "测试用。"}},
        }, ensure_ascii=False).encode("utf-8"),
        "adventure.json": json.dumps({
            "schema_version": 1, "kind": "adventure", "id": PACKAGE_ID,
            "source_ref": "diceframe-test:v2-auto",
            "recommended_world_id": WORLD_ID, "automation_level": "guided",
            **graph,
        }, ensure_ascii=False).encode("utf-8"),
    }
    for name, payload in files.items():
        target = package / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return AdventureResolver.single_directory(root, source_kind="user")


def _deps(resolver: AdventureResolver) -> adventure_runtime.AdventureRuntimeDependencies:
    return adventure_runtime.AdventureRuntimeDependencies(
        resolve_binding=lambda instance: resolver.resolve_binding(
            instance.adventure_binding, "zh-CN",
        ),
        materialize_world_seed=materialize_world_seed,
    )


def _instance(resolver: AdventureResolver) -> GameInstance:
    instance = GameInstance(
        game_key=("test", "adv2-auto", "bot"),
        world_id=WORLD_ID, rule_id="dnd2024_srd", language="zh-CN", gm_uid="gm",
    )
    binding = resolver.resolve_with_source(ADVENTURE_ID, "zh-CN").binding(WORLD_ID)
    assert instance.bind_adventure(binding) is True
    return instance


def _progress(instance: GameInstance) -> dict:
    return adventure_runtime_state.progress_snapshot(instance)


# ---- 图契约 -----------------------------------------------------------------


def test_completion_field_is_validated_and_default_not_materialized() -> None:
    graph = validate_graph_v2(_graph())
    settle = next(node for node in graph["nodes"] if node["id"] == "settle")
    entry = next(node for node in graph["nodes"] if node["id"] == "entry")
    assert settle["completion"] == "auto"
    assert "completion" not in entry  # 缺省 gm 不物化，存量图字节不变


def test_invalid_completion_mode_fails_closed() -> None:
    with pytest.raises(AdventureGraphV2Error, match="completion mode"):
        validate_graph_v2(_graph(nodes=[
            {"id": "entry", "type": "scene", "completion": "whenever", "transitions": []},
        ], start_node_ids=["entry"]))


# ---- 引擎结算 ----------------------------------------------------------------


def test_manual_completion_cascades_auto_successor_in_one_command(tmp_path) -> None:
    resolver = _install(tmp_path, _graph())
    instance = _instance(resolver)
    deps = _deps(resolver)
    adventure_runtime.initialize_adventure_run(deps, instance)

    result = adventure_runtime.complete_adventure_node(deps, instance, "entry")

    progress = _progress(instance)
    # entry 完成激活 watch（gm 节点，等人确认）；settle 尚未解锁。
    assert set(progress["active_nodes"]) == {"watch"}
    assert "settle" not in result["auto_completed"]
    # 解锁条件由 watch 的门控控制：先满足事实，再推进世界。
    apply_world_ops(instance, [{"op": "set_fact", "key": "clock.day14", "value": True}])
    advanced = adventure_runtime.advance_adventure_world(deps, instance)
    assert advanced["activated_nodes"] == ["settle"]
    assert [row["node_id"] for row in advanced["auto_completed"]] == ["settle"]
    # auto 事务真实执行了 outcome 与门控推进。
    progress = _progress(instance)
    assert world_facts(instance.world_state).get("finale.settled", {}).get("value") is True
    assert "settle" in progress["completed_nodes"]
    assert set(progress["active_nodes"]) == {"watch", "epilogue"}


def test_auto_start_node_settles_during_initialization(tmp_path) -> None:
    graph = _graph(
        nodes=[
            {
                "id": "kickoff", "type": "scene", "chapter_id": "ch1", "completion": "auto",
                "on_complete": [
                    {"type": "world_op", "op": {"op": "set_fact", "key": "boot.done", "value": True}},
                ],
                "transitions": [{"to": "entry"}],
            },
            next(node for node in _graph()["nodes"] if node["id"] == "entry")
            | {"transitions": []},
        ],
        start_node_ids=["kickoff"],
        objectives=[{"id": "obj_entry", "name": "开局", "node_ids": ["entry"]}],
        milestones=[],
    )
    resolver = _install(tmp_path, graph)
    instance = _instance(resolver)

    receipt = adventure_runtime.initialize_adventure_run(_deps(resolver), instance)

    assert [row["node_id"] for row in receipt["auto_completed"]] == ["kickoff"]
    progress = _progress(instance)
    assert "kickoff" in progress["completed_nodes"]
    assert set(progress["active_nodes"]) == {"entry"}
    assert world_facts(instance.world_state).get("boot.done", {}).get("value") is True


def test_default_gm_nodes_never_auto_complete(tmp_path) -> None:
    resolver = _install(tmp_path, _graph())
    instance = _instance(resolver)
    deps = _deps(resolver)
    adventure_runtime.initialize_adventure_run(deps, instance)
    # 无 auto 节点可结算：命令级联与 advance 都返回空。
    advanced = adventure_runtime.advance_adventure_world(deps, instance)
    assert advanced["auto_completed"] == []
    assert adventure_runtime.settle_auto_completions(deps, instance) == []
    assert set(_progress(instance)["active_nodes"]) == {"entry"}
