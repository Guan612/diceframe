from __future__ import annotations

import asyncio

import pytest

from src.engine.economy import queue_effect_group, queue_proposal, resolve_proposal
from src.engine.game_instance import GameInstance, GameRegistry
from src.llm.client import LLMResponse
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
    effect_group = queue_effect_group(
        instance,
        [proposal],
        {"state_update": {"scene_change": "付费区域"}},
    )

    instance.remove_payments_for_player("p2")

    assert proposal["status"] == "cancelled"
    assert proposal["resolution_code"] == "PLAYER_REMOVED"
    assert proposal not in instance.pending_payments
    assert effect_group is not None
    assert effect_group["status"] == "discarded"
    assert "effects" not in effect_group
    assert instance.economy["outcomes"][-1]["status"] == "cancelled"


def test_declining_payment_discards_deferred_narrative_effects() -> None:
    instance = _instance()
    proposal = queue_proposal(
        instance,
        kind="payment",
        payer_uid="gm",
        recipient_uid="gm",
        amount=10,
        reason="购买通行许可",
    )
    effect_group = queue_effect_group(
        instance,
        [proposal],
        {
            "state_update": {
                "scene_change": "城门内",
                "loot": [{"player": "gm", "item": "通行许可"}],
            },
            "confirmed": ["已经进入城内"],
        },
    )

    result = resolve_proposal(
        instance,
        proposal["id"],
        actor_uid="gm",
        accepted=False,
    )

    assert result["ok"] is True
    assert result["outcome"]["status"] == "declined"
    assert result["outcome"]["effects_status"] == "discarded"
    assert instance.get_character_sheet("gm")["currency"]["amount"] == 30
    assert effect_group is not None
    assert effect_group["status"] == "discarded"
    assert "effects" not in effect_group


def test_multiple_proposals_form_one_all_or_nothing_effect_barrier() -> None:
    instance = _instance()
    first = queue_proposal(
        instance,
        kind="payment",
        payer_uid="gm",
        recipient_uid="gm",
        amount=3,
    )
    second = queue_proposal(
        instance,
        kind="payment",
        payer_uid="p2",
        recipient_uid="p2",
        amount=4,
    )
    group = queue_effect_group(
        instance,
        [first, second],
        {"state_update": {"scene_change": "队伍共同进入的区域"}},
    )

    first_result = resolve_proposal(
        instance, first["id"], actor_uid="gm", accepted=True,
    )
    second_result = resolve_proposal(
        instance, second["id"], actor_uid="p2", accepted=True,
    )

    assert group is not None
    assert first_result.get("effect_group") is None
    assert first_result["outcome"]["effects_status"] == "pending"
    assert second_result["effect_group"]["id"] == group["id"]
    assert group["status"] == "ready"


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
    effect_group = queue_effect_group(
        instance,
        [proposal],
        {"state_update": {"scene_change": "队伍包下的房间"}},
    )

    second_view = api.game_detail(created["game_key"], second_uid)
    assert [item["id"] for item in second_view["economy_proposals"]] == [proposal["id"]]

    first = await api.resolve_payment(
        created["game_key"], proposal["id"], True, first_uid,
    )
    assert first["committed"] is False
    assert instance.get_character_sheet(first_uid)["currency"]["amount"] == 20
    assert instance.scene != "队伍包下的房间"
    assert effect_group is not None and effect_group["status"] == "pending"
    assert any(event.get("code") == "economy_approved" for event in instance.health_events)

    second = await api.resolve_payment(
        created["game_key"], proposal["id"], True, second_uid,
    )
    assert second["ok"] is True
    assert instance.get_character_sheet(first_uid)["currency"]["amount"] == 16
    assert instance.get_character_sheet(second_uid)["currency"]["amount"] == 14
    assert instance.scene == "队伍包下的房间"
    assert effect_group["status"] == "committed"
    assert "effects" not in effect_group
    assert instance.economy["outcomes"][-1]["effects_status"] == "committed"


@pytest.mark.asyncio
async def test_private_payment_outcome_does_not_leak_into_party_log(web_api) -> None:
    api, _lorebook, registry, _llm, _worlds = web_api
    created = await api.create_game(
        "template_world",
        "Private Economy",
        players=[
            {"character_name": "One", "attributes": {"str": 10}, "gold": 20},
            {"character_name": "Two", "attributes": {"str": 10}, "gold": 20},
        ],
    )
    instance = registry.get(api._parse_key(created["game_key"]))
    payer_uid, other_uid = list(instance.players)
    instance.gm_uid = payer_uid
    instance.append_log_entry({
        "round": instance.round_number,
        "actions": [],
        "gm_response": "一次私下报价。",
        "state_changes": [],
    })
    proposal = queue_proposal(
        instance,
        kind="payment",
        payer_uid=payer_uid,
        recipient_uid=payer_uid,
        amount=2,
        reason="不应公开的私下报价",
        visibility="private",
    )

    result = await api.resolve_payment(
        created["game_key"], proposal["id"], False, payer_uid,
    )

    assert result["ok"] is True
    assert "economy_resolutions" not in instance.log[-1]
    assert not any("私下报价" in item for item in instance.log[-1]["state_changes"])
    assert instance.private_log[payer_uid][-1]["kind"] == "economy_resolution"
    assert other_uid not in instance.private_log


@pytest.mark.asyncio
async def test_payment_decision_commits_or_discards_linked_effects(web_api) -> None:
    api, _lorebook, registry, _llm, _worlds = web_api
    created = await api.create_game(
        "template_world",
        "Decision Barrier",
        players=[{"character_name": "Hero", "attributes": {"str": 10}, "gold": 20}],
    )
    instance = registry.get(api._parse_key(created["game_key"]))
    uid = next(iter(instance.players))
    instance.gm_uid = uid
    instance.append_log_entry({
        "round": instance.round_number,
        "actions": [],
        "gm_response": "商人提出交易。",
        "state_changes": [],
    })
    accepted = queue_proposal(
        instance,
        kind="purchase",
        payer_uid=uid,
        recipient_uid=uid,
        amount=5,
        reason="购买城门通行证",
        visibility="party",
    )
    accepted_group = queue_effect_group(
        instance,
        [accepted],
        {
            "state_update": {
                "scene_change": "城门内",
                "loot": [{"player": uid, "item": "城门通行证"}],
            },
            "confirmed": ["已经取得城门通行证"],
            "xp_rewards": {uid: 7},
        },
    )

    committed = await api.resolve_payment(
        created["game_key"], accepted["id"], True, uid,
    )

    assert committed["effects_committed"] is True
    assert instance.get_character_sheet(uid)["currency"]["amount"] == 15
    assert instance.scene == "城门内"
    sheet = instance.get_character_sheet(uid)
    owned_items = [
        item
        for field in ("inventory", "key_items", "equipment")
        for item in sheet.get(field, [])
        if isinstance(item, dict)
    ]
    assert any(item.get("name") == "城门通行证" for item in owned_items)
    assert "已经取得城门通行证" in instance.confirmed_items
    assert instance.get_character_sheet(uid)["xp"] == 7
    assert accepted_group is not None and accepted_group["status"] == "committed"
    assert instance.log[-1]["economy_resolutions"][-1]["status"] == "committed"

    declined = queue_proposal(
        instance,
        kind="payment",
        payer_uid=uid,
        recipient_uid=uid,
        amount=4,
        reason="乘坐马车",
        visibility="party",
    )
    declined_group = queue_effect_group(
        instance,
        [declined],
        {"state_update": {"scene_change": "远方驿站"}},
    )

    rejected = await api.resolve_payment(
        created["game_key"], declined["id"], False, uid,
    )

    assert rejected["accepted"] is False
    assert instance.get_character_sheet(uid)["currency"]["amount"] == 15
    assert instance.scene == "城门内"
    assert declined_group is not None and declined_group["status"] == "discarded"
    assert "effects" not in declined_group
    assert instance.log[-1]["economy_resolutions"][-1]["status"] == "declined"


@pytest.mark.asyncio
async def test_in_flight_narration_is_discarded_after_economy_decision(
    web_api,
    monkeypatch,
) -> None:
    api, _lorebook, registry, llm, _worlds = web_api
    created = await api.create_game(
        "template_world",
        "Decision Race",
        players=[{"character_name": "Hero", "attributes": {"str": 10}, "gold": 20}],
    )
    instance = registry.get(api._parse_key(created["game_key"]))
    uid = next(iter(instance.players))
    instance.gm_uid = uid
    await instance.activate()
    await instance.start_round()
    await instance.add_action(uid, "我等待商人的答复")
    assert await instance.try_advance() is True
    instance.complete_round_check_preparation()
    proposal = queue_proposal(
        instance,
        kind="payment",
        payer_uid=uid,
        recipient_uid=uid,
        amount=3,
        reason="商人的旧报价",
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed_call(*, system_prompt, user_message, **kwargs):
        entered.set()
        await release.wait()
        return LLMResponse(
            content="这条叙事已经过期。\n---\nSCENE:错误场景",
            narration="这条叙事已经过期。",
            state_update=None,
            memory_delta=None,
            info_asymmetry=None,
            plot_update=None,
            total_tokens=8,
            is_narration_only=False,
            provider_used="fake",
        )

    monkeypatch.setattr(llm, "call", delayed_call)
    processing = asyncio.create_task(api._handler.process_round(instance))
    await entered.wait()
    declined = await api.resolve_payment(
        created["game_key"], proposal["id"], False, uid,
    )
    assert declined["ok"] is True
    release.set()

    narration, private = await processing

    assert narration == ""
    assert private is None
    assert instance.scene != "错误场景"
    assert not any(entry.get("gm_response") == "这条叙事已经过期。" for entry in instance.log)


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
    pending = queue_proposal(
        instance, kind="payment", payer_uid=uid, recipient_uid=uid, amount=2,
    )
    queue_effect_group(
        instance,
        [pending],
        {"state_update": {"scene_change": "不应进入的场景"}},
    )
    declined = queue_proposal(
        instance, kind="payment", payer_uid=uid, recipient_uid=uid, amount=1,
    )
    resolve_proposal(
        instance, declined["id"], actor_uid=uid, accepted=False,
    )
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
    assert restarted.economy["effect_groups"] == []
    assert restarted.economy["outcomes"] == []
    assert restarted.economy["decision_revision"] == 0
    recovered = await GameRegistry(registry.save_dir).load(restarted.game_key)
    assert recovered is not None
    assert recovered.run_id == restarted.run_id
    assert all(
        entry.get("gm_response") != "previous-run-only"
        for entry in recovered.log
    )

    reset_pending = queue_proposal(
        restarted,
        kind="payment",
        payer_uid=uid,
        recipient_uid=uid,
        amount=2,
    )
    queue_effect_group(
        restarted,
        [reset_pending],
        {"state_update": {"scene_change": "重置后不应出现"}},
    )
    reset_run = restarted.run_id
    reset_result = await api.reset_game(created["game_key"])
    reset_instance = registry.get(api._parse_key(created["game_key"]))

    assert reset_result["ok"] is True
    assert reset_instance.run_id != reset_run
    assert reset_instance.players == {}
    assert reset_instance.pending_payments == []
    assert reset_instance.economy["proposals"] == []
    assert reset_instance.economy["transactions"] == []
    assert reset_instance.economy["effect_groups"] == []
    assert reset_instance.economy["outcomes"] == []
    assert reset_instance.economy["decision_revision"] == 0
