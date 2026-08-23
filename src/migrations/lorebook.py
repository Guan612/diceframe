"""Lorebook database schema migrations."""

from __future__ import annotations

import sqlite3

from .sqlite import ensure_column, run_migrations


def _v1(conn: sqlite3.Connection) -> None:
    for name, definition in (
        ("is_constant", "INTEGER DEFAULT 0"),
        ("match_mode", "TEXT DEFAULT 'any'"),
        ("sticky", "INTEGER DEFAULT 0"),
        ("cooldown", "INTEGER DEFAULT 0"),
        ("delay", "INTEGER DEFAULT 0"),
        ("order", "INTEGER DEFAULT 100"),
        ("probability", "INTEGER DEFAULT 100"),
        ("group", "TEXT DEFAULT ''"),
        ("group_weight", "INTEGER DEFAULT 1"),
        ("connected_to", "TEXT DEFAULT '[]'"),
    ):
        ensure_column(conn, "lorebook_entries", name, definition)
    ensure_column(conn, "worlds", "language", "TEXT DEFAULT 'zh-CN'")
    ensure_column(conn, "lorebook_entries", "source_plugin", "TEXT DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_source ON lorebook_entries(source_plugin)")


def _v2(conn: sqlite3.Connection) -> None:
    """补齐早期数据库缺失的现行可选列。

    ``LorebookStore`` 的建表 SQL 只作用于新表，历史表会跳过
    ``CREATE TABLE IF NOT EXISTS``。因此所有当前 CRUD 会用到的非核心列都
    必须在 migration 中显式补齐，且默认值要兼容 SQLite 的 ALTER TABLE。
    """
    for name, definition in (
        ("description", "TEXT DEFAULT ''"),
        ("language", "TEXT DEFAULT 'zh-CN'"),
        ("author", "TEXT DEFAULT ''"),
        ("version", "TEXT DEFAULT '1.0'"),
        # SQLite 不允许 ADD COLUMN 使用 datetime('now') 这类非字面量默认值。
        ("created_at", "TEXT DEFAULT ''"),
        ("updated_at", "TEXT DEFAULT ''"),
    ):
        ensure_column(conn, "worlds", name, definition)

    for name, definition in (
        ("unreliable", "INTEGER DEFAULT 0"),
        ("sync_on_enter", "INTEGER DEFAULT 0"),
        ("tier", "TEXT DEFAULT 'background'"),
        ("triggers_recursive", "TEXT DEFAULT '[]'"),
        ("visible_to", "TEXT DEFAULT '[]'"),
        ("is_constant", "INTEGER DEFAULT 0"),
        ("match_mode", "TEXT DEFAULT 'any'"),
        ("sticky", "INTEGER DEFAULT 0"),
        ("cooldown", "INTEGER DEFAULT 0"),
        ("delay", "INTEGER DEFAULT 0"),
        ("order", "INTEGER DEFAULT 100"),
        ("probability", "INTEGER DEFAULT 100"),
        ("group", "TEXT DEFAULT ''"),
        ("group_weight", "INTEGER DEFAULT 1"),
        ("connected_to", "TEXT DEFAULT '[]'"),
        ("source_plugin", "TEXT DEFAULT ''"),
        ("created_at", "TEXT DEFAULT ''"),
        ("updated_at", "TEXT DEFAULT ''"),
    ):
        ensure_column(conn, "lorebook_entries", name, definition)


def migrate(conn: sqlite3.Connection) -> int:
    return run_migrations(conn, ((1, _v1), (2, _v2)))
