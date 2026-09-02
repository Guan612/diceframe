"""Memory database schema migrations."""

from __future__ import annotations

import sqlite3

from .sqlite import ensure_column, run_migrations


def _v1(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "memory_entries", "embedding", "TEXT")


def _v2(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_economy_deliveries (
            game_key TEXT NOT NULL,
            delivery_id TEXT NOT NULL,
            before_state TEXT NOT NULL,
            after_state TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'applied'
                CHECK(status IN ('applied','reversed')),
            created_at TEXT NOT NULL,
            reversed_at TEXT,
            PRIMARY KEY (game_key, delivery_id)
        );

        CREATE INDEX IF NOT EXISTS idx_memory_economy_delivery_status
            ON memory_economy_deliveries(game_key, status);
        """
    )


def migrate(conn: sqlite3.Connection) -> int:
    return run_migrations(conn, ((1, _v1), (2, _v2)))
