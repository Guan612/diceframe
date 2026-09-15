from src.migrations.instance import migrate_game_state_payload


def test_schema10_manual_rolls_default_to_record_only_purpose():
    payload = migrate_game_state_payload({
        "instance_schema_version": 10,
        "manual_roll_requests": [{"id": "mr-1", "results": {}}],
    })
    assert payload["instance_schema_version"] == 11
    assert payload["manual_roll_requests"][0]["purpose"] == "free"
