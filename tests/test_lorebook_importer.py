from src.lorebook.importer import commit_lorebook_import, detect_lorebook_format, preview_lorebook_import
from src.lorebook.store import LorebookStore


def test_lorebook_v3_preview_is_format_neutral_and_preserves_unknowns():
    payload = {"spec": "lorebook_v3", "data": {"lorebook": {"name": "Book", "mystery": 1, "entries": [{"id": "e", "keys": "one,two", "content": "text"}]}}}
    preview = preview_lorebook_import(payload)
    assert preview["format"] == "lorebook_v3"
    assert preview["counts"]["entries"] == 1
    assert preview["book"].entries[0].keys == ["one", "two"]
    assert preview["book"].preserved_extensions["raw"] == {"mystery": 1}


def test_sillytavern_preview_warns_timed_semantics_and_maps_secondary_keys():
    payload = {"name": "ST", "entries": [{"uid": 1, "key": ["a"], "keysecondary": "b,c", "content": "x", "sticky": 2}]}
    preview = preview_lorebook_import(payload)
    assert detect_lorebook_format(payload) == "sillytavern"
    assert preview["book"].entries[0].secondary_keys == ["b", "c"]
    assert preview["warnings"]


def test_character_book_detects_as_character_card_v3():
    payload = {"spec": "chara_card_v3", "data": {"name": "NPC", "character_book": {"entries": []}}}
    assert detect_lorebook_format(payload) == "character_card_v3"


def test_character_book_nested_data_is_imported():
    payload = {"spec": "chara_card_v3", "data": {"name": "NPC", "character_book": {"name": "NPC lore", "entries": [{"id": "1", "name": "Secret", "keys": ["door"], "content": "hidden"}]}}}
    preview = preview_lorebook_import(payload)
    assert preview["counts"]["entries"] == 1
    assert preview["book"].entries[0].name == "Secret"


def test_import_ids_are_book_scoped_and_recreating_book_does_not_delete_bindings(tmp_path):
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    try:
        draft = preview_lorebook_import({"name": "same", "entries": [{"uid": 1, "key": ["x"], "content": "one"}]})["book"]
        book_id = commit_lorebook_import(store, draft, {"id": "binding:one", "scope_kind": "world", "scope_id": "w"}, book_id="book:one")
        commit_lorebook_import(store, draft, {"id": "binding:two", "scope_kind": "world", "scope_id": "w2"}, book_id="book:two")
        assert book_id == "book:one"
        assert store.list_book_entries("book:one")[0]["id"] != store.list_book_entries("book:two")[0]["id"]
        store.create_lorebook({"id": "book:one", "name": "replacement"})
        assert store.list_bindings(scope_kind="world", scope_id="w")[0]["book_id"] == "book:one"
        assert store.list_book_entries("book:one")
    finally:
        store.close()
