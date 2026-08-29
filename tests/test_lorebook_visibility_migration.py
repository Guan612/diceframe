"""内置世界书可见性迁移：老安装升级路径、幂等与用户编辑保护。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.lorebook.bootstrap import (
    LEGACY_BUNDLED_CONTENT,
    ensure_world_from_template,
    seed_builtin_worlds,
)
from src.lorebook.store import LorebookStore

TEMPLATE = {
    "world_id": "demo_world",
    "world_name": "测试世界",
    "language": "zh-CN",
    "starter_lorebook": [
        {
            "id": "npc_pub", "name": "酒馆老板", "type": "npc", "keywords": ["老板"],
            "content": "新版本公开正文", "tier": "core", "visible_to": ["*"],
        },
        {
            "id": "loc_secret", "name": "暗巷", "type": "location", "keywords": ["暗巷"],
            "content": "秘密现场线索", "tier": "background", "visible_to": [],
        },
    ],
}

OLD_PUB_CONTENT = "旧版官方正文（重审计前）"


def _register_old_content(world_id: str, entry_id: str, content: str) -> None:
    LEGACY_BUNDLED_CONTENT.setdefault(world_id, {})[entry_id] = content


@pytest.fixture()
def store(tmp_path):
    store = LorebookStore(tmp_path / "lorebook.db")
    store.open()
    yield store
    store.close()


@pytest.fixture(autouse=True)
def clean_manifest():
    saved = dict(LEGACY_BUNDLED_CONTENT.get("demo_world", {}))
    LEGACY_BUNDLED_CONTENT.pop("demo_world", None)
    yield
    LEGACY_BUNDLED_CONTENT.pop("demo_world", None)
    if saved:
        LEGACY_BUNDLED_CONTENT["demo_world"] = saved


def _seed_old_state(store: LorebookStore) -> None:
    store.create_world("demo_world", "测试世界")
    store.add_entry({
        "id": "npc_pub", "world_id": "demo_world", "name": "酒馆老板",
        "type": "npc", "keywords": ["老板"], "content": OLD_PUB_CONTENT,
        "tier": "core", "visible_to": [],
    })


def test_unchanged_old_entry_upgrades_and_new_secret_entry_is_added(store, monkeypatch):
    monkeypatch.setitem(LEGACY_BUNDLED_CONTENT, "demo_world", {})
    _register_old_content("demo_world", "npc_pub", OLD_PUB_CONTENT)
    _seed_old_state(store)

    inserted = ensure_world_from_template(store, "demo_world", TEMPLATE)

    upgraded = store.get_entry("npc_pub")
    assert upgraded["content"] == "新版本公开正文"
    assert upgraded["visible_to"] == ["*"]
    # 新拆出的秘密条目按新 id 正常新增
    assert inserted == 1
    assert store.get_entry("loc_secret")["visible_to"] == []


def test_user_edited_content_is_never_touched(store, monkeypatch):
    monkeypatch.setitem(LEGACY_BUNDLED_CONTENT, "demo_world", {})
    _register_old_content("demo_world", "npc_pub", OLD_PUB_CONTENT)
    store.create_world("demo_world", "测试世界")
    store.add_entry({
        "id": "npc_pub", "world_id": "demo_world", "name": "酒馆老板",
        "type": "npc", "keywords": ["老板"], "content": "用户自己重写的正文",
        "tier": "core", "visible_to": [],
    })

    ensure_world_from_template(store, "demo_world", TEMPLATE)

    upgraded = store.get_entry("npc_pub")
    assert upgraded["content"] == "用户自己重写的正文"
    assert upgraded["visible_to"] == []


def test_user_visibility_decision_is_respected(store, monkeypatch):
    monkeypatch.setitem(LEGACY_BUNDLED_CONTENT, "demo_world", {})
    _register_old_content("demo_world", "npc_pub", OLD_PUB_CONTENT)
    store.create_world("demo_world", "测试世界")
    store.add_entry({
        "id": "npc_pub", "world_id": "demo_world", "name": "酒馆老板",
        "type": "npc", "keywords": ["老板"], "content": OLD_PUB_CONTENT,
        "tier": "core", "visible_to": ["莱拉"],
    })

    ensure_world_from_template(store, "demo_world", TEMPLATE)

    upgraded = store.get_entry("npc_pub")
    assert upgraded["content"] == OLD_PUB_CONTENT
    assert upgraded["visible_to"] == ["莱拉"]


def test_migration_is_idempotent(store, monkeypatch):
    monkeypatch.setitem(LEGACY_BUNDLED_CONTENT, "demo_world", {})
    _register_old_content("demo_world", "npc_pub", OLD_PUB_CONTENT)
    _seed_old_state(store)

    assert ensure_world_from_template(store, "demo_world", TEMPLATE) >= 0
    first = store.get_entry("npc_pub")
    assert first["visible_to"] == ["*"]

    calls_before = _content_of(store, "npc_pub")
    ensure_world_from_template(store, "demo_world", TEMPLATE)
    assert _content_of(store, "npc_pub") == calls_before
    assert store.get_entry("npc_pub")["visible_to"] == ["*"]


def _content_of(store: LorebookStore, entry_id: str) -> str:
    return str(store.get_entry(entry_id)["content"])


def test_real_template_migration_on_coc_horror(store):
    """真实模板 + 真实清单：内容未变的公开条目升级后仅可见性翻转。"""
    template_path = Path("templates/worlds/coc_horror.json")
    template = json.loads(template_path.read_text(encoding="utf-8"))
    target = next(e for e in template["starter_lorebook"] if e["id"] == "loc_arkham")

    store.create_world("coc_horror", "克苏鲁恐怖·阿卡姆疑云")
    store.add_entry({
        "id": "loc_arkham", "world_id": "coc_horror", "name": target["name"],
        "type": "location", "keywords": target["keywords"], "content": target["content"],
        "tier": target.get("tier", "background"), "visible_to": [],
    })

    ensure_world_from_template(store, "coc_horror", template)

    upgraded = store.get_entry("loc_arkham")
    assert upgraded["visible_to"] == ["*"]
    assert upgraded["content"] == target["content"]


def test_real_seed_builtin_worlds_upgrades_old_install(store, tmp_path):
    """端到端：seed_builtin_worlds 在老安装上同时完成升级与新秘密条目新增。"""
    template_path = Path("templates/worlds/coc_horror.json")
    template = json.loads(template_path.read_text(encoding="utf-8"))
    howard = next(e for e in template["starter_lorebook"] if e["id"] == "loc_howard_house")
    # 老安装里存的是拆分前的原始全文（清单里记录的正是这份原文）
    legacy_content = LEGACY_BUNDLED_CONTENT["coc_horror"]["loc_howard_house"]

    worlds_dir = tmp_path / "worlds"
    worlds_dir.mkdir()
    (worlds_dir / "coc_horror.json").write_text(
        json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")

    store.create_world("coc_horror", "克苏鲁恐怖·阿卡姆疑云")
    store.add_entry({
        "id": "loc_howard_house", "world_id": "coc_horror", "name": "霍华德的住所",
        "type": "location", "keywords": howard["keywords"], "content": legacy_content,
        "tier": "background", "visible_to": [],
    })

    seed_builtin_worlds(store, worlds_dir)

    upgraded = store.get_entry("loc_howard_house")
    assert upgraded["visible_to"] == ["*"]
    assert "上了锁的工具棚" not in upgraded["content"]
    oddities = store.get_entry("loc_howard_house_oddities")
    assert oddities and oddities["visible_to"] == []
