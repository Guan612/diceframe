import sqlite3

from src.lorebook.activation import migrate_timed_state
from src.lorebook.exporter import export_lorebook_v3
from src.lorebook.importer import preview_lorebook_import, commit_lorebook_import
from src.lorebook.store import LorebookStore


def test_golden_old_db_import_preview_bind_export_restart(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("CREATE TABLE worlds (id TEXT PRIMARY KEY, name TEXT NOT NULL); CREATE TABLE lorebook_entries (id TEXT PRIMARY KEY, world_id TEXT NOT NULL, name TEXT NOT NULL, content TEXT); INSERT INTO worlds VALUES ('w', 'Old'); INSERT INTO lorebook_entries VALUES ('e', 'w', 'Old entry', 'legacy');")
    conn.commit(); conn.close()
    store = LorebookStore(path); store.open()
    try:
        assert store.get_lorebook("world:w")
        preview = preview_lorebook_import({"entries": [{"uid": "st", "key": ["harbor"], "content": "rumor", "sticky": 1}]})
        assert preview["format"] == "sillytavern"
        book_id = commit_lorebook_import(store, preview["book"], {"id": "binding:game", "scope_kind": "world", "scope_id": "w"}, book_id="book:st")
        assert store.list_book_entries(book_id)[0]["name"] == ""
        exported = export_lorebook_v3(store, book_id)
        assert exported["spec"] == "lorebook_v3"
        assert migrate_timed_state({"e": {"status": "cooldown", "remaining": 2}})["e"]["cooldown_remaining"] == 2
    finally:
        store.close()
    store = LorebookStore(path); store.open()
    try:
        assert store.list_entries("w")
        assert store.list_book_entries("book:st")
    finally:
        store.close()
