from copy import deepcopy

import pytest

from src.engine.game_instance import GameInstance
from src.rulesets.automation import apply_director_automation, summarize_automation_batches


class _FailingRuntime:
    def director_automatic_intent(self, instance, proposal):
        return {"type": "start"}

    def resolve_intent(self, instance, intent, rng):
        return {"ok": True, "event_batch": {"intent_type": intent["type"]}}

    def apply_event_batch(self, instance, batch):
        instance.ruleset_state["changed"] = True
        instance.players["p"]["hp"] = 0
        instance.scene = "mutated scene"
        raise ValueError("failed after mutation")


def test_director_automation_rolls_back_partial_runtime_mutation():
    instance = GameInstance(
        game_key=("test", "automation-rollback", "bot"),
        ruleset_state={"version": 1},
        players={"p": {"hp": 10}},
        scene="original scene",
    )
    before = deepcopy((instance.ruleset_state, instance.players, instance.scene))
    with pytest.raises(ValueError, match="failed after mutation"):
        apply_director_automation(_FailingRuntime(), instance, {"kind": "combat"}, object())
    assert (instance.ruleset_state, instance.players, instance.scene) == before


def test_automation_batches_have_a_public_narration_summary():
    batches = [{"events": [{"type": "dnd2024.tutorial.choice_applied"}]}]

    zh = summarize_automation_batches(batches)
    en = summarize_automation_batches(batches, chinese=False)
    # 契约：automation 有面向玩家的公开摘要且区分语言；具体措辞不锁。
    assert zh and en
    assert zh != en
