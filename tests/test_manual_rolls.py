import asyncio
from types import SimpleNamespace

from src.webui.services.manual_rolls import ManualRollDependencies, ManualRollService


def test_manual_roll_create_resolve_is_idempotent_and_bound_to_target():
    instance = SimpleNamespace(
        gm_uid="gm",
        run_id="run-1",
        round_number=2,
        players={"p1": {"character_name": "Alice"}},
        manual_roll_requests=[],
        last_activity="",
    )
    saves = []

    async def save(value):
        saves.append(value)

    service = ManualRollService(
        ManualRollDependencies(lambda _: ("g", "1", "1"), lambda _: instance, save)
    )

    async def scenario():
        created = await service.create(
            "game", "gm", {"operation_id": "op-1", "run_id": "run-1", "target_uids": ["p1"], "formula": "d20+2"}
        )
        repeated = await service.create(
            "game", "gm", {"operation_id": "op-1", "run_id": "run-1", "target_uids": ["p1"], "formula": "d20+2"}
        )
        assert repeated["request"]["id"] == created["request"]["id"]
        denied = await service.resolve(
            "game", "other", created["request"]["id"], {"run_id": "run-1", "target_uid": "p1"}
        )
        assert denied["ok"] is False
        result = await service.resolve(
            "game", "p1", created["request"]["id"], {"run_id": "run-1", "target_uid": "p1"}
        )
        again = await service.resolve(
            "game", "p1", created["request"]["id"], {"run_id": "run-1", "target_uid": "p1"}
        )
        assert result["result"] == again["result"]
        assert created["request"]["status"] == "resolved"
        assert len(saves) == 2

    asyncio.run(scenario())


def test_manual_roll_purpose_check_and_contest_are_evaluated_without_state_effects():
    instance = SimpleNamespace(
        gm_uid="gm", run_id="run-1", round_number=1,
        players={"p1": {"character_name": "Alice"}, "p2": {"character_name": "Bob"}},
        manual_roll_requests=[], last_activity="",
    )
    saves = []

    async def save(value):
        saves.append(value)

    service = ManualRollService(
        ManualRollDependencies(lambda _: ("g", "1", "1"), lambda _: instance, save)
    )

    async def scenario():
        checked = await service.create(
            "game", "gm", {
                "operation_id": "check-1", "run_id": "run-1", "target_uids": ["p1"],
                "formula": "d20+2", "purpose": "check", "target": 15,
            }
        )
        result = await service.resolve(
            "game", "p1", checked["request"]["id"], {"run_id": "run-1", "target_uid": "p1"}
        )
        assert result["result"]["target"] == 15
        assert result["result"]["verdict"] in {"success", "failure"}

        contest = await service.create(
            "game", "gm", {
                "operation_id": "contest-1", "run_id": "run-1", "target_uids": ["p1", "p2"],
                "formula": "d20", "purpose": "contest",
            }
        )
        await service.resolve("game", "p1", contest["request"]["id"], {"run_id": "run-1", "target_uid": "p1"})
        final = await service.resolve("game", "p2", contest["request"]["id"], {"run_id": "run-1", "target_uid": "p2"})
        assert all(item.get("verdict") in {"winner", "loss"} for item in final["request"]["results"].values())

    asyncio.run(scenario())
