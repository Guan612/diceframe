"""Lorebook SQLite 存储 —— 世界书条目的 CRUD 操作。

查询构造走 peewee（src.lorebook.models）；连接、PRAGMA、SCHEMA 建表、
user_version 迁移与事务提交仍由本类持有，行为契约与迁移前一致。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from peewee import SQL

from src.lorebook.models import Lorebook, LorebookBinding, LorebookEntry, LorebookEmbedding, World
from src.lorebook.models import database as _models_database
from src.migrations.lorebook import migrate as migrate_lorebook

logger = logging.getLogger("trpg")

# 单次 IN(...) 查询的 entry 数量上限，避免撞 SQLite 的参数个数限制。
_CACHE_CHUNK = 400

SCHEMA = """
CREATE TABLE IF NOT EXISTS worlds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    language TEXT DEFAULT 'zh-CN',
    author TEXT DEFAULT '',
    version TEXT DEFAULT '1.0',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lorebook_entries (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'other',
    keywords TEXT NOT NULL DEFAULT '[]',
    content TEXT NOT NULL DEFAULT '',
    unreliable INTEGER DEFAULT 0,
    sync_on_enter INTEGER DEFAULT 0,
    tier TEXT DEFAULT 'background'
        CHECK(tier IN ('core','background','archived')),
    triggers_recursive TEXT DEFAULT '[]',
    visible_to TEXT DEFAULT '[]',
    is_constant INTEGER DEFAULT 0,
    match_mode TEXT DEFAULT 'any' CHECK(match_mode IN ('any','all','not_any','not_all')),
    sticky INTEGER DEFAULT 0,
    cooldown INTEGER DEFAULT 0,
    delay INTEGER DEFAULT 0,
    "order" INTEGER DEFAULT 100,
    probability INTEGER DEFAULT 100,
    "group" TEXT DEFAULT '',
    group_weight INTEGER DEFAULT 1,
    connected_to TEXT DEFAULT '[]',
    source_plugin TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lorebook_embeddings (
    entry_id TEXT NOT NULL,
    language TEXT NOT NULL,
    embedding_profile TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (entry_id, language, embedding_profile)
);
"""

_CURRENT_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_lorebook_world ON lorebook_entries(world_id)",
    "CREATE INDEX IF NOT EXISTS idx_lorebook_type ON lorebook_entries(world_id, type)",
    "CREATE INDEX IF NOT EXISTS idx_lorebook_tier ON lorebook_entries(world_id, tier)",
    "CREATE INDEX IF NOT EXISTS idx_lorebook_source ON lorebook_entries(source_plugin)",
)


class LorebookStore:
    """世界书 SQLite 存储管理器。

    V1 使用单连接 + threading.Lock，读多写少的场景足够。
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def open(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        migrate_lorebook(self._conn)
        for statement in _CURRENT_INDEXES:
            self._conn.execute(statement)
        if self._conn.execute("PRAGMA foreign_key_check").fetchone():
            raise sqlite3.IntegrityError("lorebook foreign key check failed")
        self._conn.commit()
        _models_database.attach(self._conn)
        logger.info("Lorebook 数据库已打开: %s", self.db_path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
            _models_database.detach()
            logger.info("Lorebook 数据库已关闭")

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        assert self._conn, "数据库未打开"
        with self._lock:
            return self._conn.execute(sql, params)

    # ---- 世界 CRUD ----

    def create_world(self, world_id: str, name: str, **kwargs) -> None:
        # INSERT OR REPLACE 会重置 created_at 并按外键级联清掉旧条目，
        # 与迁移前行为一致，属既有语义（模板导入依赖）。
        with self._lock:
            World.insert(
                id=world_id,
                name=name,
                description=kwargs.get("description", ""),
                language=kwargs.get("language", "zh-CN"),
                author=kwargs.get("author", ""),
                version=kwargs.get("version", "1.0"),
            ).on_conflict_replace().execute()
            self._ensure_primary_book_locked(world_id, name=name, language=kwargs.get("language", "zh-CN"))
            self._conn.commit()

    def get_world(self, world_id: str) -> dict | None:
        with self._lock:
            world = World.get_or_none(World.id == world_id)
        return dict(world.__data__) if world else None

    def update_world_language(self, world_id: str, language: str) -> None:
        """Correct world language metadata without replacing the world or its entries."""
        with self._lock:
            World.update(
                language=language, updated_at=SQL("datetime('now')"),
            ).where(World.id == world_id).execute()
            self._conn.commit()

    def list_worlds(self) -> list[dict]:
        with self._lock:
            rows = list(World.select().order_by(World.updated_at.desc()))
        return [dict(w.__data__) for w in rows]

    def delete_world(self, world_id: str) -> None:
        with self._lock:
            Lorebook.delete().where(Lorebook.id == self.primary_world_book_id(world_id)).execute()
            World.delete().where(World.id == world_id).execute()
            self._conn.commit()

    # ---- canonical lorebook/book bindings ----

    @staticmethod
    def primary_world_book_id(world_id: str) -> str:
        return f"world:{world_id}"

    def _ensure_primary_book_locked(self, world_id: str, *, name: str | None = None,
                                    language: str = "zh-CN") -> str:
        book_id = self.primary_world_book_id(world_id)
        world = self._conn.execute(
            "SELECT name, description, language FROM worlds WHERE id = ?", (world_id,)
        ).fetchone()
        name = name or (str(world[0]) if world else world_id)
        description = str(world[1]) if world else ""
        language = str(world[2] or language) if world else language
        self._conn.execute(
            "INSERT OR IGNORE INTO lorebooks "
            "(id, name, description, language, source_kind, source_id) VALUES (?, ?, ?, ?, 'world', ?)",
            (book_id, name, description, language, world_id),
        )
        self._conn.execute(
            "INSERT OR IGNORE INTO lorebook_bindings "
            "(id, book_id, scope_kind, scope_id, role) VALUES (?, ?, 'world', ?, 'primary')",
            (f"binding:{book_id}:primary", book_id, world_id),
        )
        return book_id

    def ensure_primary_world_book(self, world_id: str) -> str:
        with self._lock:
            book_id = self._ensure_primary_book_locked(world_id)
            self._conn.commit()
            return book_id

    def create_lorebook(self, book: dict) -> None:
        with self._lock:
            Lorebook.insert(
                id=book["id"], name=book.get("name", book["id"]),
                description=book.get("description", ""), language=book.get("language", "zh-CN"),
                enabled=int(book.get("enabled", True)), scan_depth=int(book.get("scan_depth", 0)),
                token_budget=int(book.get("token_budget", 0)),
                recursive_scanning=int(book.get("recursive_scanning", False)),
                settings_json=json.dumps(book.get("settings", book.get("settings_json", {})), ensure_ascii=False)
                if not isinstance(book.get("settings_json"), str) else book["settings_json"],
                source_kind=book.get("source_kind", "native"), source_id=book.get("source_id", ""),
                source_version=book.get("source_version", ""), source_digest=book.get("source_digest", ""),
            ).on_conflict_ignore().execute()
            self._conn.commit()

    def get_lorebook(self, book_id: str) -> dict | None:
        with self._lock:
            row = Lorebook.get_or_none(Lorebook.id == book_id)
        return _book_to_dict(row) if row else None

    def list_lorebooks(self, *, scope_kind: str | None = None, scope_id: str | None = None) -> list[dict]:
        with self._lock:
            query = Lorebook.select()
            if scope_kind is not None or scope_id is not None:
                query = query.join(LorebookBinding, on=(LorebookBinding.book_id == Lorebook.id))
                if scope_kind is not None:
                    query = query.where(LorebookBinding.scope_kind == scope_kind)
                if scope_id is not None:
                    query = query.where(LorebookBinding.scope_id == scope_id)
                query = query.distinct()
            rows = list(query.order_by(Lorebook.updated_at.desc()))
        return [_book_to_dict(row) for row in rows]

    def bind_lorebook(self, binding: dict) -> None:
        with self._lock:
            LorebookBinding.insert(
                id=binding["id"], book_id=binding["book_id"], scope_kind=binding["scope_kind"],
                scope_id=binding.get("scope_id", ""), role=binding.get("role", ""),
                enabled=int(binding.get("enabled", True)), order=int(binding.get("order", 100)),
            ).on_conflict_replace().execute()
            self._conn.commit()

    def list_bindings(self, *, scope_kind: str | None = None, scope_id: str | None = None) -> list[dict]:
        with self._lock:
            query = LorebookBinding.select()
            if scope_kind is not None:
                query = query.where(LorebookBinding.scope_kind == scope_kind)
            if scope_id is not None:
                query = query.where(LorebookBinding.scope_id == scope_id)
            rows = list(query.order_by(LorebookBinding.order, LorebookBinding.id))
        return [dict(row.__data__) for row in rows]

    # ---- 条目 CRUD ----

    def add_entry(self, entry: dict) -> None:
        with self._lock:
            requested_book_id = entry.get("book_id")
            # Legacy world-copy callers clone a row verbatim, including the old
            # ``world:<source>`` book id. A target world remains authoritative for
            # that compatibility path; explicit standalone imports have no world_id
            # and keep their canonical book id.
            if entry.get("world_id") and requested_book_id and str(requested_book_id).startswith("world:") and requested_book_id != self.primary_world_book_id(entry["world_id"]):
                requested_book_id = None
            book_id = requested_book_id or self._ensure_primary_book_locked(entry["world_id"])
            LorebookEntry.insert(
                id=entry["id"],
                book_id=book_id,
                world_id=entry.get("world_id"),
                name=entry["name"],
                type=entry.get("type", "other"),
                keywords=json.dumps(entry.get("keywords", []), ensure_ascii=False),
                content=entry.get("content", ""),
                unreliable=int(entry.get("unreliable", False)),
                sync_on_enter=int(entry.get("sync_on_enter", False)),
                tier=entry.get("tier", "background"),
                triggers_recursive=json.dumps(
                    entry.get("triggers_recursive", []), ensure_ascii=False),
                visible_to=json.dumps(entry.get("visible_to", []), ensure_ascii=False),
                is_constant=int(entry.get("is_constant", False)),
                match_mode=entry.get("match_mode", "any"),
                sticky=int(entry.get("sticky", 0)),
                cooldown=int(entry.get("cooldown", 0)),
                delay=int(entry.get("delay", 0)),
                order=int(entry.get("order", 100)),
                probability=int(entry.get("probability", 100)),
                group=entry.get("group", ""),
                group_weight=int(entry.get("group_weight", 1)),
                connected_to=json.dumps(entry.get("connected_to", []), ensure_ascii=False),
                source_plugin=entry.get("source_plugin", ""),
                enabled=int(entry.get("enabled", True)),
                secondary_keys=json.dumps(entry.get("secondary_keys", []), ensure_ascii=False),
                selective_logic=entry.get("selective_logic", "and"),
                use_regex=int(entry.get("use_regex", False)),
                case_sensitive=int(entry.get("case_sensitive", False)),
                match_whole_words=int(entry.get("match_whole_words", False)),
                scan_depth=int(entry.get("scan_depth", 0)), priority=int(entry.get("priority", 0)),
                vector_activation=str(entry.get("vector_activation", "off") or "off"),
                non_recursable=int(entry.get("non_recursable", False)),
                prevent_further_recursion=int(entry.get("prevent_further_recursion", False)),
                delay_until_recursion=int(entry.get("delay_until_recursion", False)),
                recursion_level=int(entry.get("recursion_level", 0)),
                groups=json.dumps(entry.get("groups", []), ensure_ascii=False),
                prioritize_inclusion=int(entry.get("prioritize_inclusion", False)),
                group_scoring=entry.get("group_scoring", ""), prompt_slot=entry.get("prompt_slot", ""),
                extensions_json=json.dumps(entry.get("extensions", entry.get("extensions_json", {})), ensure_ascii=False)
                if not isinstance(entry.get("extensions_json"), str) else entry["extensions_json"],
                provenance_json=json.dumps(entry.get("provenance", entry.get("provenance_json", {})), ensure_ascii=False)
                if not isinstance(entry.get("provenance_json"), str) else entry["provenance_json"],
            ).on_conflict_replace().execute()
            self._conn.commit()

    def get_entry(self, entry_id: str) -> dict | None:
        with self._lock:
            entry = LorebookEntry.get_or_none(LorebookEntry.id == entry_id)
        return _entry_to_dict(entry) if entry else None

    def update_entry(self, entry_id: str, updates: dict) -> None:
        allowed = {"name", "type", "content", "unreliable",
                   "sync_on_enter", "tier", "keywords", "triggers_recursive", "visible_to",
                   "is_constant", "match_mode", "sticky", "cooldown", "delay", "order",
                   "probability", "group", "group_weight", "connected_to", "enabled",
                   "secondary_keys", "selective_logic", "use_regex", "case_sensitive",
                   "match_whole_words", "scan_depth", "priority", "vector_activation",
                   "non_recursable", "prevent_further_recursion", "delay_until_recursion",
                   "recursion_level", "groups", "prioritize_inclusion", "group_scoring",
                   "prompt_slot", "extensions_json", "provenance_json"}
        fields = {}
        for k, v in updates.items():
            if k not in allowed:
                continue
            if k in ("keywords", "triggers_recursive", "visible_to", "connected_to", "secondary_keys", "groups"):
                v = json.dumps(v, ensure_ascii=False)
            elif k in ("extensions_json", "provenance_json") and not isinstance(v, str):
                v = json.dumps(v, ensure_ascii=False)
            elif k == "vector_activation":
                v = str(v or "off")
                if v not in {"off", "hybrid", "vector_only"}:
                    v = "off"
            elif k in ("unreliable", "sync_on_enter", "is_constant", "enabled", "use_regex",
                       "case_sensitive", "match_whole_words", "non_recursable",
                       "prevent_further_recursion", "delay_until_recursion", "prioritize_inclusion",
                       "sticky", "cooldown", "delay", "order",
                       "probability", "group_weight", "scan_depth", "priority", "recursion_level"):
                v = int(v)
            fields[k] = v
        if not fields:
            return
        with self._lock:
            LorebookEntry.update(
                **fields, updated_at=SQL("datetime('now')"),
            ).where(LorebookEntry.id == entry_id).execute()
            self._conn.commit()

    def delete_entry(self, entry_id: str) -> None:
        with self._lock:
            LorebookEntry.delete().where(LorebookEntry.id == entry_id).execute()
            # 派生缓存跟着条目走，避免删除后残留向量行。
            self._delete_embeddings_locked([entry_id])
            self._conn.commit()

    def delete_world_cascade(self, world_id: str) -> None:
        """删除世界及其所有条目。"""
        with self._lock:
            entry_ids = [
                str(row.id) for row in
                LorebookEntry.select(LorebookEntry.id).where(LorebookEntry.world_id == world_id)
            ]
            LorebookEntry.delete().where(LorebookEntry.world_id == world_id).execute()
            self._delete_embeddings_locked(entry_ids)
            World.delete().where(World.id == world_id).execute()
            self._conn.commit()

    def count_entries_by_plugin(self, plugin_id: str) -> int:
        with self._lock:
            return LorebookEntry.select().where(
                LorebookEntry.source_plugin == plugin_id,
            ).count()

    def delete_entries_by_plugin(self, plugin_id: str) -> int:
        """删除该插件来源的全部世界书条目，返回删除条数。"""
        with self._lock:
            entry_ids = [
                str(row.id) for row in
                LorebookEntry.select(LorebookEntry.id).where(
                    LorebookEntry.source_plugin == plugin_id,
                )
            ]
            rowcount = LorebookEntry.delete().where(
                LorebookEntry.source_plugin == plugin_id,
            ).execute()
            self._delete_embeddings_locked(entry_ids)
            self._conn.commit()
        return rowcount

    def list_plugin_worlds(self, plugin_id: str) -> list[dict]:
        """该插件创建的、仍含其来源条目的世界（用于条件删除判定）。"""
        with self._lock:
            rows = list(
                World.select()
                .join(LorebookEntry, on=(LorebookEntry.world_id == World.id))
                .where(LorebookEntry.source_plugin == plugin_id)
                .distinct()
            )
        return [dict(w.__data__) for w in rows]

    def list_entries(self, world_id: str, entry_type: str | None = None) -> list[dict]:
        with self._lock:
            book_id = self._ensure_primary_book_locked(world_id)
            # Compatibility projection: legacy world consumers see the primary
            # book plus canonical books explicitly bound to this world.
            query = LorebookEntry.select().where(
                (LorebookEntry.book_id == book_id) | (LorebookEntry.world_id == world_id)
            )
            if entry_type:
                query = query.where(LorebookEntry.type == entry_type)
            rows = list(query.order_by(LorebookEntry.tier, LorebookEntry.name))
        return [_entry_to_dict(e) for e in rows]

    def list_book_entries(self, book_id: str, entry_type: str | None = None) -> list[dict]:
        with self._lock:
            query = LorebookEntry.select().where(LorebookEntry.book_id == book_id)
            if entry_type:
                query = query.where(LorebookEntry.type == entry_type)
            rows = list(query.order_by(LorebookEntry.tier, LorebookEntry.name))
        return [_entry_to_dict(e) for e in rows]

    # ---- embedding 派生缓存（migration v4） ----

    def load_embedding_cache(
        self, entry_ids: list[str], language: str, embedding_profile: str,
    ) -> dict[str, dict]:
        """读取 (entry_id, language, profile) 命中的向量缓存。

        返回 ``entry_id -> {"content_hash": str, "embedding": list[float]}``。缓存行损坏
        （不是合法 JSON 数组，或含非数字 / NaN / Inf）一律按缺失处理，由调用方重新
        embedding —— 派生缓存的坏数据不能让正常回合抛异常。
        """

        ids = [str(entry_id).strip() for entry_id in entry_ids or [] if str(entry_id).strip()]
        if not ids:
            return {}
        result: dict[str, dict] = {}
        with self._lock:
            for start in range(0, len(ids), _CACHE_CHUNK):
                chunk = ids[start:start + _CACHE_CHUNK]
                rows = list(
                    LorebookEmbedding.select().where(
                        (LorebookEmbedding.language == str(language or ""))
                        & (LorebookEmbedding.embedding_profile == str(embedding_profile or ""))
                        & (LorebookEmbedding.entry_id.in_(chunk))
                    )
                )
                for row in rows:
                    data = dict(row.__data__)
                    try:
                        vector = json.loads(data.get("embedding") or "[]")
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if not isinstance(vector, list) or not vector:
                        continue
                    # 坏向量（非数字 / NaN / Inf）按缺失处理，绝不抛给调用方。
                    try:
                        numbers = [float(value) for value in vector]
                    except (TypeError, ValueError):
                        continue
                    if any(
                        number != number or number in (float("inf"), float("-inf"))
                        for number in numbers
                    ):
                        continue
                    result[str(data.get("entry_id") or "")] = {
                        "content_hash": str(data.get("content_hash") or ""),
                        "embedding": numbers,
                    }
        return result

    def save_embedding_cache(self, rows: list[dict]) -> None:
        """写入 / 覆盖派生缓存行；坏行（无 id 或空向量）直接跳过。"""

        payload = []
        for row in rows or []:
            entry_id = str(row.get("entry_id") or "").strip()
            vector = row.get("embedding")
            if not entry_id or not isinstance(vector, (list, tuple)) or not vector:
                continue
            payload.append({
                "entry_id": entry_id,
                "language": str(row.get("language") or ""),
                "embedding_profile": str(row.get("embedding_profile") or ""),
                "content_hash": str(row.get("content_hash") or ""),
                "embedding": json.dumps([float(value) for value in vector]),
            })
        if not payload:
            return
        with self._lock:
            for row in payload:
                LorebookEmbedding.insert(**row).on_conflict_replace().execute()
            self._conn.commit()

    def _delete_embeddings_locked(self, entry_ids: list[str]) -> None:
        """删除若干 entry 的缓存行（调用方必须已持有 ``self._lock``）。"""

        ids = [str(entry_id).strip() for entry_id in entry_ids or [] if str(entry_id).strip()]
        for start in range(0, len(ids), _CACHE_CHUNK):
            chunk = ids[start:start + _CACHE_CHUNK]
            LorebookEmbedding.delete().where(
                LorebookEmbedding.entry_id.in_(chunk),
            ).execute()

    def search_entries(self, world_id: str, keyword: str) -> list[dict]:
        # peewee 的 SQLite 方言把 ilike 编译为 SQL LIKE（like 会被编译成 GLOB，
        # 通配符语义不同，不要改用 like）。
        pattern = f"%{keyword}%"
        with self._lock:
            book_id = self._ensure_primary_book_locked(world_id)
            rows = list(
                LorebookEntry.select()
                .where(
                    (LorebookEntry.book_id == book_id)
                    & (
                        LorebookEntry.name.ilike(pattern)
                        | LorebookEntry.content.ilike(pattern)
                        | LorebookEntry.keywords.ilike(pattern)
                    )
                )
                .order_by(LorebookEntry.tier, LorebookEntry.name)
            )
        return [_entry_to_dict(e) for e in rows]

    def search_book_entries(self, book_id: str, keyword: str) -> list[dict]:
        pattern = f"%{keyword}%"
        with self._lock:
            rows = list(LorebookEntry.select().where(
                (LorebookEntry.book_id == book_id)
                & (LorebookEntry.name.ilike(pattern)
                   | LorebookEntry.content.ilike(pattern)
                   | LorebookEntry.keywords.ilike(pattern))
            ).order_by(LorebookEntry.tier, LorebookEntry.name))
        return [_entry_to_dict(e) for e in rows]


def _entry_to_dict(entry: LorebookEntry) -> dict:
    d = dict(entry.__data__)
    d["keywords"] = json.loads(d.get("keywords", "[]"))
    d["triggers_recursive"] = json.loads(d.get("triggers_recursive", "[]"))
    d["visible_to"] = json.loads(d.get("visible_to", "[]"))
    d["connected_to"] = json.loads(d.get("connected_to", "[]"))
    for key, default in (("secondary_keys", "[]"), ("groups", "[]"),
                         ("extensions_json", "{}"), ("provenance_json", "{}")):
        raw = d.get(key, default)
        try:
            d[key.removesuffix("_json") if key.endswith("_json") else key] = json.loads(raw or default)
        except (TypeError, json.JSONDecodeError):
            d[key.removesuffix("_json") if key.endswith("_json") else key] = [] if default == "[]" else {}
    d["source_plugin"] = d.get("source_plugin", "") or ""
    return d


def _book_to_dict(book: Lorebook) -> dict:
    d = dict(book.__data__)
    try:
        d["settings"] = json.loads(d.get("settings_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        d["settings"] = {}
    return d
