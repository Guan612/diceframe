"""AI hosting controls in game setup, roster and away handling (plan, PR5).

PR1 made *who plays a seat* persistent, PR2 made it authoritative, and PR3/PR4
made an AI-hosted seat actually play (exploration + combat).  This file locks
down the last piece: the room and the people in it can now *say* who controls a
seat, and a seat handed to the AI because its player stepped away is temporary
in a way that cannot silently become permanent.

Behaviour under test:

* creation carries a per-card control choice, a room-level default for the cards
  the creator did not decide, and a client that sends nothing at all still gets
  today's behaviour (every seat ``human``);
* an unknown control mode at creation fails closed instead of quietly building a
  default seat;
* ``away_control_policy`` is a persisted room setting: ``pause`` by default,
  ``pause`` for every save written before the setting existed, ``pause`` for a
  corrupt stored value, and it survives save/load;
* with ``ai_takeover``, stepping away hands the seat to the server AI in the
  *temporary* shape (``temporary=true`` with ``resume_mode=human``) and coming
  back returns it, while ``pause`` leaves control exactly where it was;
* a GM can hand a human seat to the AI and take it back, and that switch changes
  **only** the control record -- character sheet, HP, ready state and the combat
  actor stay put;
* every control transition only happens at a safe boundary; otherwise the caller
  gets the retryable ``CONTROL_CHANGE_BUSY``;
* temporary hosting is distinguishable from permanent hosting, and it never
  becomes permanent across save/load.

The tests drive the real Web API surface (``create_game``, ``set_player_away``,
``set_player_control``, ``set_away_control_policy``) on a real ``GameInstance``.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.engine.game_instance import GameInstance, GameState
from src.engine.player_control import (
    DEFAULT_AWAY_CONTROL_POLICY,
    PlayerControlError,
    away_control_policy,
    begin_away_hosting,
    control_mode,
    end_away_hosting,
    get_control,
    is_temporarily_ai_controlled,
    normalize_away_control_policy,
    set_away_control_policy,
    set_control,
)
from src.migrations.instance import (
    CURRENT_INSTANCE_SCHEMA_VERSION,
    migrate_game_state_payload,
)

pytest_plugins = ["tests.webapi_harness"]


CHARACTERS = [
    {"character_name": "阿岚", "attributes": {"str": 12}},
    {"character_name": "米拉", "attributes": {"str": 11}},
    {"character_name": "白露", "attributes": {"str": 10}},
]


async def _create(api, **kwargs) -> tuple[str, Any]:
    created = await api.create_game(
        "template_world", "模板世界", players=[dict(c) for c in CHARACTERS], **kwargs,
    )
    assert created.get("ok") is not False, created
    instance = api.get_game_instance(created["game_key"])
    return created["game_key"], instance


def _uids(instance: GameInstance) -> list[str]:
    return sorted(instance.players)


# ---- 1. 开房：逐卡控制 + 未认领默认 -----------------------------------------


@pytest.mark.asyncio
async def test_creation_applies_a_per_card_control_choice(web_api) -> None:
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    characters = [dict(c) for c in CHARACTERS]
    characters[0]["control"] = "human"
    characters[1]["control"] = "ai"
    characters[2]["control"] = "unclaimed"

    created = await api.create_game(
        "template_world", "模板世界", players=characters,
    )
    instance = api.get_game_instance(created["game_key"])
    uids = sorted(instance.players)

    assert [control_mode(instance, uid) for uid in uids] == ["human", "ai", "unclaimed"]
    # 每张卡的返回值也带上它自己的控制记录，前端不必再猜。
    assert [player.get("control", {}).get("mode") for player in created["players"]] == [
        "human", "ai", "unclaimed",
    ]


@pytest.mark.asyncio
async def test_per_card_choice_beats_the_room_default(web_api) -> None:
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    characters = [dict(c) for c in CHARACTERS]
    characters[0]["control"] = "human"  # 显式覆盖全局默认

    created = await api.create_game(
        "template_world", "模板世界", players=characters,
        unclaimed_control_default="ai",
    )
    instance = api.get_game_instance(created["game_key"])
    uids = sorted(instance.players)

    assert [control_mode(instance, uid) for uid in uids] == ["human", "ai", "ai"]


@pytest.mark.asyncio
async def test_creation_without_any_control_information_keeps_todays_behaviour(
    web_api,
) -> None:
    """旧客户端不发控制信息时，每个席位仍然是 human。"""

    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    _game_key, instance = await _create(api)

    assert {control_mode(instance, uid) for uid in instance.players} == {"human"}


@pytest.mark.asyncio
async def test_creation_fails_closed_on_an_unknown_control_mode(web_api) -> None:
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    characters = [dict(c) for c in CHARACTERS]
    characters[1]["control"] = "remote_bot"

    created = await api.create_game(
        "template_world", "模板世界", players=characters,
    )

    assert created.get("ok") is False
    assert created.get("error_code") == "INVALID_PLAYER_CONTROL"


# ---- 2. 房间设置 away_control_policy ----------------------------------------


def test_away_policy_defaults_to_pause() -> None:
    instance = GameInstance(game_key="g")

    assert instance.away_control_policy == DEFAULT_AWAY_CONTROL_POLICY == "pause"
    assert away_control_policy(instance) == "pause"


def test_away_policy_only_accepts_the_two_known_values() -> None:
    instance = GameInstance(game_key="g")

    assert set_away_control_policy(instance, "ai_takeover") == "ai_takeover"
    assert away_control_policy(instance) == "ai_takeover"
    with pytest.raises(PlayerControlError):
        set_away_control_policy(instance, "ai_everything")
    # 拒绝之后仍然是上一个合法值，不会被写坏。
    assert away_control_policy(instance) == "ai_takeover"


def test_a_save_written_before_the_setting_existed_becomes_pause() -> None:
    """v14 存档没有这个字段，唯一不猜测的答案是旧版本行为。"""

    migrated = migrate_game_state_payload({
        "instance_schema_version": 14,
        "game_key": ["web", "away-policy", "bot"],
        "players": {},
    })

    assert migrated["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    assert migrated["away_control_policy"] == "pause"


def test_a_corrupt_stored_policy_reads_as_pause() -> None:
    assert normalize_away_control_policy("nonsense") == "pause"
    assert normalize_away_control_policy(None) == "pause"

    migrated = migrate_game_state_payload({
        "instance_schema_version": 14,
        "away_control_policy": "nonsense",
        "players": {},
    })
    assert migrated["away_control_policy"] == "pause"


def test_away_policy_migration_is_idempotent() -> None:
    once = migrate_game_state_payload({
        "instance_schema_version": 14,
        "away_control_policy": "ai_takeover",
        "players": {},
    })
    twice = migrate_game_state_payload(once)

    assert once["away_control_policy"] == "ai_takeover"
    assert twice["away_control_policy"] == "ai_takeover"


def test_away_policy_survives_save_and_load() -> None:
    instance = GameInstance(game_key="g")
    set_away_control_policy(instance, "ai_takeover")

    recovered = GameInstance.from_dict(instance.to_dict())

    assert away_control_policy(recovered) == "ai_takeover"


@pytest.mark.asyncio
async def test_room_policy_is_settable_through_the_api(web_api) -> None:
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    game_key, instance = await _create(api)

    ok = await api.set_away_control_policy(game_key, "ai_takeover")
    assert ok["ok"] is True
    assert away_control_policy(instance) == "ai_takeover"

    bad = await api.set_away_control_policy(game_key, "whatever")
    assert bad["ok"] is False
    assert bad.get("error_code") == "AWAY_POLICY_UNSUPPORTED"


# ---- 3. 暂离语义 -------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_leaves_control_exactly_where_it_was(web_api) -> None:
    """默认 pause 保持旧语义：暂离只改在场状态，角色不交给 AI。"""

    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    game_key, instance = await _create(api)
    uid = sorted(instance.players)[0]

    result = await api.set_player_away(game_key, uid, True)

    assert result["ok"] is True
    assert control_mode(instance, uid) == "human"
    assert uid in instance.away_players


@pytest.mark.asyncio
async def test_ai_takeover_hands_over_temporarily_and_gives_it_back(web_api) -> None:
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    game_key, instance = await _create(api)
    await api.set_away_control_policy(game_key, "ai_takeover")
    uid = sorted(instance.players)[0]
    sheet_before = dict(instance.players[uid]["character_sheet"])

    await api.set_player_away(game_key, uid, True)

    record = get_control(instance, uid)
    assert record["mode"] == "ai"
    assert record["temporary"] is True
    assert record["resume_mode"] == "human"
    assert is_temporarily_ai_controlled(instance, uid) is True

    back = await api.set_player_away(game_key, uid, False)

    assert back["ok"] is True
    assert control_mode(instance, uid) == "human"
    assert get_control(instance, uid)["temporary"] is False
    assert get_control(instance, uid)["resume_mode"] is None
    assert is_temporarily_ai_controlled(instance, uid) is False
    # 「无损」：暂离与回来都不动角色卡。
    assert dict(instance.players[uid]["character_sheet"]) == sheet_before


def test_returning_does_not_steal_a_permanently_hosted_seat() -> None:
    """回来只归还「临时托管」；GM 永久交给 AI 的席位不会被抢回。"""

    instance = GameInstance(game_key="g")
    instance.put_player("p1", {"character_name": "阿岚"})
    set_control(instance, "p1", "ai")

    assert end_away_hosting(instance, "p1")["mode"] == "ai"
    assert is_temporarily_ai_controlled(instance, "p1") is False


def test_away_hosting_is_a_no_op_for_a_seat_without_a_human() -> None:
    instance = GameInstance(game_key="g")
    instance.put_player("p1", {"character_name": "阿岚"})
    set_control(instance, "p1", "unclaimed")

    assert begin_away_hosting(instance, "p1")["mode"] == "unclaimed"


@pytest.mark.asyncio
async def test_temporary_hosting_does_not_become_permanent(web_api) -> None:
    """重启 / 重新加载之后，临时托管仍然可以归还，而不是变成永久 AI。"""

    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    game_key, instance = await _create(api)
    await api.set_away_control_policy(game_key, "ai_takeover")
    uid = sorted(instance.players)[0]
    await api.set_player_away(game_key, uid, True)

    reloaded = GameInstance.from_dict(instance.to_dict())

    assert is_temporarily_ai_controlled(reloaded, uid) is True
    assert get_control(reloaded, uid)["resume_mode"] == "human"
    assert end_away_hosting(reloaded, uid)["mode"] == "human"
    assert control_mode(reloaded, uid) == "human"


# ---- 4. GM 托管控件 ----------------------------------------------------------


@pytest.mark.asyncio
async def test_gm_can_hand_a_human_seat_to_the_ai_and_take_it_back(web_api) -> None:
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    game_key, instance = await _create(api)
    uid = sorted(instance.players)[1]
    assert control_mode(instance, uid) == "human"

    hosted = await api.set_player_control(game_key, uid, "ai")
    assert hosted["ok"] is True
    assert control_mode(instance, uid) == "ai"
    # GM 的明确决定不是「暂离临时托管」，所以不带临时标记。
    assert is_temporarily_ai_controlled(instance, uid) is False

    stopped = await api.set_player_control(game_key, uid, "human")
    assert stopped["ok"] is True
    assert control_mode(instance, uid) == "human"


@pytest.mark.asyncio
async def test_gm_switch_changes_only_the_control_record(web_api) -> None:
    """切换托管不得复制角色、重置 ready / HP，也不得重建战斗 actor。"""

    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    game_key, instance = await _create(api)
    uids = sorted(instance.players)
    uid = uids[1]
    instance.players[uid]["character_sheet"]["hp"] = 7
    instance.ready_players.add(uid)
    instance.combat_enemies = [{"actor_id": "enemy:1", "hp": 9}]
    sheet_before = dict(instance.players[uid]["character_sheet"])
    sheet_name_before = instance.players[uid]["character_name"]
    player_keys_before = set(instance.players[uid])

    await api.set_player_control(game_key, uid, "ai")

    assert dict(instance.players[uid]["character_sheet"]) == sheet_before
    assert instance.players[uid]["character_sheet"]["hp"] == 7
    assert instance.ready_players == {uid}
    assert instance.combat_enemies == [{"actor_id": "enemy:1", "hp": 9}]
    # 席位本身没有被重建：键集合不变，角色名不变。
    assert set(instance.players[uid]) == player_keys_before
    assert instance.players[uid]["character_name"] == sheet_name_before
    assert len(instance.players) == len(uids)


@pytest.mark.asyncio
async def test_gm_switch_refuses_an_unsupported_mode(web_api) -> None:
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    game_key, instance = await _create(api)
    uid = sorted(instance.players)[1]

    result = await api.set_player_control(game_key, uid, "unclaimed")

    assert result["ok"] is False
    assert result.get("error_code") == "CONTROL_MODE_UNSUPPORTED"
    assert control_mode(instance, uid) == "human"


# ---- 5. 安全边界 -------------------------------------------------------------


@pytest.mark.asyncio
async def test_control_changes_are_refused_while_a_round_is_in_flight(web_api) -> None:
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    game_key, instance = await _create(api)
    await api.set_away_control_policy(game_key, "ai_takeover")
    uid = sorted(instance.players)[0]
    instance.state = GameState.ACTIVE_JUDGMENT

    hosted = await api.set_player_control(game_key, uid, "ai")
    away = await api.set_player_away(game_key, uid, True)

    for result in (hosted, away):
        assert result["ok"] is False
        assert result.get("error_code") == "CONTROL_CHANGE_BUSY"
    assert control_mode(instance, uid) == "human"


@pytest.mark.asyncio
async def test_away_and_back_work_at_the_safe_boundary(web_api) -> None:
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    game_key, instance = await _create(api)
    await api.set_away_control_policy(game_key, "ai_takeover")
    uid = sorted(instance.players)[0]
    instance.state = GameState.ACTIVE_ACTION

    assert (await api.set_player_away(game_key, uid, True))["ok"] is True
    assert (await api.set_player_away(game_key, uid, False))["ok"] is True


# ---- 6. 徽章状态可从服务端派生 ------------------------------------------------


@pytest.mark.asyncio
async def test_roster_reports_human_ai_and_unclaimed_seats(web_api) -> None:
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    game_key, instance = await _create(api)
    uids = sorted(instance.players)
    await api.set_player_control(game_key, uids[1], "ai")
    set_control(instance, uids[2], "unclaimed")

    status = instance.multiplayer_status()

    assert [p["user_id"] for p in status["ai_players"]] == [uids[1]]
    assert [p["user_id"] for p in status["unclaimed_players"]] == [uids[2]]
    assert status["ai_count"] == 1
    assert status["unclaimed_count"] == 1
    # ready / waiting 只统计真人席位，托管与未认领不会挡推进。
    assert status["ready_count"] == 0
    assert [p["user_id"] for p in status["waiting_players"]] == [uids[0]]


@pytest.mark.asyncio
async def test_temporary_hosting_is_distinguishable_from_permanent(web_api) -> None:
    """徽章要能区分「AI 临时托管」与「AI 托管」。"""

    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    game_key, instance = await _create(api)
    uids = sorted(instance.players)

    await api.set_player_control(game_key, uids[1], "ai")
    assert is_temporarily_ai_controlled(instance, uids[1]) is False

    await api.set_away_control_policy(game_key, "ai_takeover")
    await api.set_player_away(game_key, uids[0], True)
    assert is_temporarily_ai_controlled(instance, uids[0]) is True

    # 两种 AI 席位都在 ai_players 里，但临时标记只在其中一个上。
    status = instance.multiplayer_status()
    assert {p["user_id"] for p in status["ai_players"]} == {uids[0], uids[1]}


# ---- 7. 认领路径在开房之后仍然成立 -------------------------------------------


@pytest.mark.asyncio
async def test_an_unclaimed_creation_card_can_still_be_claimed(web_api) -> None:
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    characters = [dict(c) for c in CHARACTERS]
    characters[2]["control"] = "unclaimed"
    created = await api.create_game(
        "template_world", "模板世界", players=characters,
    )
    instance = api.get_game_instance(created["game_key"])
    uid = sorted(instance.players)[2]
    assert control_mode(instance, uid) == "unclaimed"

    joined = await api.create_player(
        created["game_key"], {"user_id": uid, "name": "随便填"},
    )

    assert joined["ok"] is True
    assert control_mode(instance, uid) == "human"
