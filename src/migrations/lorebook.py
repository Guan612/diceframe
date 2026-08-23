"""Lorebook database schema migrations."""

from __future__ import annotations

import sqlite3

from .sqlite import ensure_column, run_migrations, table_columns

_LOREBOOK_COLUMNS = (
    "id", "world_id", "name", "type", "keywords", "content", "unreliable",
    "sync_on_enter", "tier", "triggers_recursive", "visible_to", "is_constant",
    "match_mode", "sticky", "cooldown", "delay", "order", "probability",
    "group", "group_weight", "connected_to", "source_plugin", "created_at", "updated_at",
)

_REBUILT_ENTRIES_SQL = """
CREATE TABLE lorebook_entries_new (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'other',
    keywords TEXT NOT NULL DEFAULT '[]',
    content TEXT NOT NULL DEFAULT '',
    unreliable INTEGER DEFAULT 0,
    sync_on_enter INTEGER DEFAULT 0,
    tier TEXT DEFAULT 'background' CHECK(tier IN ('core','background','archived')),
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
"""


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
    ensure_column(conn, "worlds", "author", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "worlds", "version", "TEXT NOT NULL DEFAULT '1.0'")
    ensure_column(conn, "worlds", "created_at", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "worlds", "updated_at", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "lorebook_entries", "source_plugin", "TEXT DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_source ON lorebook_entries(source_plugin)")


def _v2(conn: sqlite3.Connection) -> None:
    """Converge historical tables to the current schema when required."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='lorebook_entries'"
    ).fetchone()
    table_sql = str(row[0] or "") if row else ""
    normalized = table_sql.upper().replace('"', "")
    old_columns = table_columns(conn, "lorebook_entries")
    missing_columns = set(_LOREBOOK_COLUMNS) - old_columns
    needs_rebuild = bool(missing_columns)
    needs_rebuild |= "TYPE IN" in normalized
    needs_rebuild |= "TIER IN" not in normalized or "MATCH_MODE IN" not in normalized
    if not needs_rebuild:
        return

    shared = [column for column in _LOREBOOK_COLUMNS if column in old_columns]
    # ``executescript`` implicitly commits in sqlite3, which would break the
    # migration runner's rollback contract. This block contains one statement.
    conn.execute(_REBUILT_ENTRIES_SQL)
    if shared:
        columns = ", ".join(f'"{column}"' for column in shared)
        conn.execute(
            f"INSERT INTO lorebook_entries_new ({columns}) "
            f"SELECT {columns} FROM lorebook_entries"
        )
    conn.execute("DROP TABLE lorebook_entries")
    conn.execute("ALTER TABLE lorebook_entries_new RENAME TO lorebook_entries")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_world ON lorebook_entries(world_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_type ON lorebook_entries(world_id, type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_tier ON lorebook_entries(world_id, tier)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_source ON lorebook_entries(source_plugin)")


def migrate(conn: sqlite3.Connection) -> int:
    return run_migrations(conn, ((1, _v1), (2, _v2)))
