from src.compat.saves import normalize_save_payload


def test_legacy_dnd_save_projects_known_names_to_canonical_ids_without_rewriting_display():
    payload = {"players": {"p1": {"character_sheet": {"class": "战士", "equipment": [{"name": "长剑"}]}}}}
    normalized = normalize_save_payload(payload)
    sheet = normalized["players"]["p1"]["character_sheet"]
    assert sheet["class_id"] == "fighter"
    assert sheet["equipment"][0]["item_key"] == "longsword"
    assert sheet["equipment"][0]["name"] == "长剑"
