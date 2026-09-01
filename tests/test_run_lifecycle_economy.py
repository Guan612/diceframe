from __future__ import annotations

import pytest

from src.engine.economy import queue_proposal, resolve_proposal
from src.engine.game_instance import GameInstance, GameRegistry
from src.migrations.instance import migrate_game_state_payload

from webapi_harness import web_api  # noqa: F401


def _instance() -> GameInstance:
    instance = GameInstance(game_key=("web", "economy", "bot"), gm_uid="gm")
    instance.players = {
        "gm": {"character_name": "GM", "character_sheet": {"gold": 30, "currency": {"amount": 30}}},
        "p2": {"character_name": "P2", "character_sheet": {"gold": 20, "currency": {"amount": 20}}},
    }
    return instance


def test_save_migration_assigns_stable_run_and_imports_pending_payment() -> None:
    legacy = {
        "game_key": ["web", "legacy", "bot"],
        "state": "paused",
        "started_at": "2025-01-01T00:00:00+00:00",
        "pending_payments": [{"id": "pay_old", "uid": "p1", "amount": 3, "status": "pending"}],
    }
    first = migrate_game_state_payload(legacy)
    second = migrate_game_state_payload(first)

    assert first == second
    assert first["instance_schema_version"] == 2
    assert first["run_id"].startswith("run_")
    assert first["memory_namespace"] == "('web', 'legacy', 'bot')"
    assert first["economy"]["proposals"][0]["id"] == "pay_old"


def test_narrative_reward_requires_gm_and_commits_once() -> None:
    instance = _instance()
    proposal = queue_proposal(
        instance,
        kind="reward",
        recipient_uid="p2",
        amount=5,
        approval_policy="gm",
        source="narrative",
        source_ref="round:1:reward:p2:5",
    )

    forbidden = resolve_proposal(instance, proposal["id"], actor_uid="p2", accepted=True)
    accepted = resolve_proposal(instance, proposal["id"], actor_uid="gm", accepted=True)
    duplicate = resolve_proposal(instance, proposal["id"], actor_uid="gm", accepted=True)

    assert forbidden["code"] == "FORBIDDEN"
    assert accepted["ok"] is True
    assert instance.get_character_sheet("p2")["currency"]["amount"] == 25
    assert len(instance.economy["transactions"]) == 1
    assert sum(
        entry["delta"] for entry in accepted["transaction"]["entries"]
    ) == 0
    assert duplicate["code"] == "ALREADY_RESOLVED"


def test_transfer_moves_currency_between_players_with_balanced_ledger() -> None:
    instance = _instance()
    proposal = queue_proposal(
        instance,
        kind="transfer",
        payer_uid="gm",
        recipient_uid="p2",
        amount=7,
        approval_policy="payer",
        source_ref="player-transfer:1",
    )

    result = resolve_proposal(
        instance, proposal["id"], actor_uid="gm", accepted=True,
    )

    assert result["ok"] is True
    assert instance.get_character_sheet("gm")["currency"]["amount"] == 23
    assert instance.get_character_sheet("p2")["currency"]["amount"] == 27
    assert sum(entry["delta"] for entry in result["transaction"]["entries"]) == 0


def test_team_split_is_all_or_nothing() -> None:
    instance = _instance()
    proposal = queue_proposal(
        instance,
        kind="fee",
        amount=15,
        approval_policy="all_contributors",
        contributors=[{"uid": "gm", "amount": 5}, {"uid": "p2", "amount": 10}],
        source_ref="gate:city:fee",
    )

    first = resolve_proposal(instance, proposal["id"], actor_uid="gm", accepted=True)
    assert first["committed"] is False
    assert instance.get_character_sheet("gm")["currency"]["amount"] == 30
    second = resolve_proposal(instance, proposal["id"], actor_uid="p2", accepted=True)

    assert second["ok"] is True
    assert instance.get_character_sheet("gm")["currency"]["amount"] == 25
    assert instance.get_character_sheet("p2")["currency"]["amount"] == 10


def test_team_split_insufficient_funds_rejects_without_partial_debit() -> None:
    instance = _instance()
    proposal = queue_proposal(
        instance,
        kind="fee",
        amount=45,
        approval_policy="all_contributors",
        contributors=[{"uid": "gm", "amount": 5}, {"uid": "p2", "amount": 40}],
        source_ref="gate:city:expensive-fee",
    )

    assert resolve_proposal(
        instance, proposal["id"], actor_uid="gm", accepted=True,
    )["committed"] is False
    rejected = resolve_proposal(
        instance, proposal["id"], actor_uid="p2", accepted=True,
    )

    assert rejected["code"] == "INSUFFICIENT_FUNDS"
    assert instance.get_character_sheet("gm")["currency"]["amount"] == 30
    assert instance.get_character_sheet("p2")["currency"]["amount"] == 20
    assert proposal["status"] == "rejected"
    assert proposal not in instance.pending_payments


def test_team_split_rejects_incomplete_or_duplicate_contributor_plan() -> None:
    instance = _instance()

    with pytest.raises(ValueError):
        queue_proposal(
            instance,
            kind="fee",
            amount=10,
            approval_policy="all_contributors",
            contributors=[{"uid": "gm", "amount": 4}, {"uid": "gm", "amount": 4}],
        )


def test_removing_party_member_cancels_their_unresolved_group_proposal() -> None:
    instance = _instance()
    proposal = queue_proposal(
        instance,
        kind="fee",
        amount=10,
        approval_policy="all_contributors",
        contributors=[{"uid": "gm", "amount": 5}, {"uid": "p2", "amount": 5}],
    )

    instance.remove_payments_for_player("p2")

    assert proposal["status"] == "cancelled"
    assert proposal["resolution_code"] == "PLAYER_REMOVED"
    assert proposal not in instance.pending_payments


@pytest.mark.asyncio
async def test_team_split_is_visible_to_each_contributor_and_waits_for_all(web_api) -> None:
    api, _lorebook, registry, _llm, _worlds = web_api
    created = await api.create_game(
        "template_world",
        "Party Economy",
        players=[
            {"character_name": "One", "attributes": {"str": 10}, "gold": 20},
            {"character_name": "Two", "attributes": {"str": 10}, "gold": 20},
        ],
    )
    instance = registry.get(api._parse_key(created["game_key"]))
    first_uid, second_uid = list(instance.players)
    instance.gm_uid = first_uid
    proposal = queue_proposal(
        instance,
        kind="fee",
        amount=10,
        approval_policy="all_contributors",
        contributors=[
            {"uid": first_uid, "amount": 4},
            {"uid": second_uid, "amount": 6},
        ],
    )

    second_view = api.game_detail(created["game_key"], second_uid)
    assert [item["id"] for item in second_view["economy_proposals"]] == [proposal["id"]]

    first = await api.resolve_payment(
        created["game_key"], proposal["id"], True, first_uid,
    )
    assert first["committed"] is False
    assert instance.get_character_sheet(first_uid)["currency"]["amount"] == 20
    assert any(event.get("code") == "economy_approved" for event in instance.health_events)

    second = await api.resolve_payment(
        created["game_key"], proposal["id"], True, second_uid,
    )
    assert second["ok"] is True
    assert instance.get_character_sheet(first_uid)["currency"]["amount"] == 16
    assert instance.get_character_sheet(second_uid)["currency"]["amount"] == 14


@pytest.mark.asyncio
async def test_restart_rotates_run_and_memory_but_preserves_character_assets(web_api) -> None:
    api, _lorebook, registry, _llm, _worlds = web_api
    created = await api.create_game(
        "template_world",
        "Lifecycle",
        players=[{"character_name": "Hero", "attributes": {"str": 10}, "gold": 23}],
    )
    instance = registry.get(api._parse_key(created["game_key"]))
    uid = next(iter(instance.players))
    sheet = instance.get_character_sheet(uid)
    sheet.update({"hp": 0, "deceased": True, "status": "downed", "death_saves": {"failure": 2}})
    old_run = instance.run_id
    old_namespace = instance.memory_namespace
    queue_proposal(instance, kind="payment", payer_uid=uid, recipient_uid=uid, amount=2)
    instance.append_log_entry({
        "round": 99,
        "actions": [],
        "gm_response": "previous-run-only",
    })
    await registry.save(instance)

    result = await api.restart_game(created["game_key"])
    restarted = registry.get(api._parse_key(created["game_key"]))

    assert result["ok"] is True
    assert restarted.run_id != old_run
    assert restarted.memory_namespace != old_namespace
    assert restarted.get_character_sheet(uid)["currency"]["amount"] == 23
    assert restarted.get_character_sheet(uid)["hp"] == restarted.get_character_sheet(uid)["max_hp"]
    assert restarted.get_character_sheet(uid).get("deceased") is False
    assert "death_saves" not in restarted.get_character_sheet(uid)
    assert restarted.pending_payments == []
    assert restarted.economy["transactions"] == []
    recovered = await GameRegistry(registry.save_dir).load(restarted.game_key)
    assert recovered is not None
    assert recovered.run_id == restarted.run_id
    assert all(
        entry.get("gm_response") != "previous-run-only"
        for entry in recovered.log
    )
