from src.lorebook.importer import detect_lorebook_format, preview_lorebook_import


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
