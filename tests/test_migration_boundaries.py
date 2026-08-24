from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "src" / "migrations"


def test_persisted_schema_upgrade_operations_stay_in_migrations() -> None:
    """Prevent startup stores from growing one-off ALTER/rebuild logic again."""
    forbidden = ("ALTER TABLE", "DROP TABLE", "RENAME TO", "PRAGMA table_info", "PRAGMA user_version", "ensure_column(")
    violations: list[str] = []
    for path in (ROOT / "src").rglob("*.py"):
        if MIGRATIONS in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker.lower() in text.lower():
                violations.append(f"{path.relative_to(ROOT)} contains {marker}")
    assert not violations, "\n".join(violations)
