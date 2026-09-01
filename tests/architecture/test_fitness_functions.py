"""Debt baselines for dependency directions that are being retired gradually.

The allowlists describe the P0 repository state. They must only shrink: the
scanner rejects both new debt and stale entries left behind after a migration.
Synthetic regressions use ``tmp_path`` so tests never touch runtime data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.architecture_fitness import (
    DependencyDebt,
    assert_debt_matches_allowlist,
    scan_backend_concrete_ruleset_debt,
    scan_frontend_concrete_ruleset_debt,
    scan_service_locator_debt,
)

ROOT = Path(__file__).resolve().parents[2]

_SERVICE_TARGETS = {
    "facade_service_call": "api.<service>()",
    "private_facade_access": "api._*",
    "webapi_import": "src.webui.api.WebAPI",
    "webapi_parameter": "WebAPI",
}


def _service_debt(path: str, *kinds: str) -> set[DependencyDebt]:
    return {
        DependencyDebt(f"src/webui/services/{path}", kind, _SERVICE_TARGETS[kind])
        for kind in kinds
    }


_STANDARD_WEBAPI_DEBT = (
    "private_facade_access",
    "webapi_import",
    "webapi_parameter",
)
_STANDARD_WEBAPI_AND_SERVICE_CALL_DEBT = (
    "facade_service_call",
    *_STANDARD_WEBAPI_DEBT,
)

# Historical service-locator debt. Do not add entries. Remove a file or
# category in the same PR that removes the corresponding dependency.
SERVICE_LOCATOR_ALLOWLIST = frozenset().union(
    _service_debt("adventures.py", *_STANDARD_WEBAPI_DEBT),
    _service_debt("character_cards.py", *_STANDARD_WEBAPI_DEBT),
    _service_debt("characters.py", *_STANDARD_WEBAPI_AND_SERVICE_CALL_DEBT),
    _service_debt("plugins.py", *_STANDARD_WEBAPI_AND_SERVICE_CALL_DEBT),
    _service_debt("ruleset_advancement.py", *_STANDARD_WEBAPI_DEBT),
    _service_debt("ruleset_characters.py", *_STANDARD_WEBAPI_DEBT),
    _service_debt("ruleset_rest.py", *_STANDARD_WEBAPI_DEBT),
    _service_debt("turns.py", *_STANDARD_WEBAPI_AND_SERVICE_CALL_DEBT),
    _service_debt("worlds.py", *_STANDARD_WEBAPI_DEBT),
)

# Historical concrete-ruleset knowledge in otherwise generic backend modules.
# Each entry is a dependency semantic, not a line/function/source snapshot.
BACKEND_CONCRETE_RULESET_ALLOWLIST = frozenset(
    {
        DependencyDebt("src/webui/services/adventures.py", "runtime_id", "core:dnd2024"),
        DependencyDebt(
            "src/webui/services/characters.py",
            "concrete_import",
            "src.rulesets.dnd2024.advancement_access",
        ),
        DependencyDebt("src/webui/services/characters.py", "runtime_id", "core:dnd2024"),
        DependencyDebt(
            "src/webui/services/ruleset_advancement.py",
            "concrete_import",
            "src.rulesets.dnd2024",
        ),
        DependencyDebt(
            "src/webui/services/ruleset_advancement.py",
            "concrete_import",
            "src.rulesets.dnd2024.progression.catalog",
        ),
        DependencyDebt(
            "src/webui/services/ruleset_advancement.py", "runtime_id", "core:dnd2024"
        ),
        DependencyDebt(
            "src/webui/services/ruleset_gameplay.py", "runtime_id", "core:dnd2024"
        ),
        *(
            DependencyDebt("src/webui/services/ruleset_gameplay.py", "event_type", event)
            for event in (
                "dnd2024.combat.ended",
                "dnd2024.combat.started",
                "dnd2024.party_decision.resolved",
                "dnd2024.tutorial.choice_applied",
                "dnd2024.tutorial.completed",
                "dnd2024.tutorial.started",
            )
        ),
    }
)

# Historical direct imports outside the D&D-owned frontend feature directory.
FRONTEND_CONCRETE_RULESET_ALLOWLIST = frozenset(
    {
        DependencyDebt(
            "frontend-v2/src/components/play/CombatMessageComposer.vue",
            "concrete_import",
            "@/features/rulesets/dnd2024/api",
        ),
        DependencyDebt(
            "frontend-v2/src/features/admin/CharactersView.vue",
            "concrete_import",
            "@/features/rulesets/dnd2024/progression/Dnd2024AdvancementPanel.vue",
        ),
        DependencyDebt(
            "frontend-v2/src/features/rulesets/ProfessionalCharacterCenter.vue",
            "concrete_import",
            "@/features/rulesets/dnd2024/api",
        ),
        *(
            DependencyDebt(
                "frontend-v2/src/features/play/PlayView.vue", "concrete_import", target
            )
            for target in (
                "@/features/rulesets/dnd2024/api",
                "@/features/rulesets/dnd2024/campaign/Dnd2024CampaignPanel.vue",
                "@/features/rulesets/dnd2024/combat/Dnd2024CombatPanel.vue",
            )
        ),
    }
)


def test_service_locator_debt_matches_shrink_only_baseline() -> None:
    assert_debt_matches_allowlist(
        scan_service_locator_debt(ROOT),
        SERVICE_LOCATOR_ALLOWLIST,
        boundary="services -> WebAPI",
    )


def test_backend_concrete_ruleset_debt_matches_shrink_only_baseline() -> None:
    assert_debt_matches_allowlist(
        scan_backend_concrete_ruleset_debt(ROOT),
        BACKEND_CONCRETE_RULESET_ALLOWLIST,
        boundary="generic backend -> dnd2024",
    )


def test_frontend_concrete_ruleset_debt_matches_shrink_only_baseline() -> None:
    assert_debt_matches_allowlist(
        scan_frontend_concrete_ruleset_debt(ROOT),
        FRONTEND_CONCRETE_RULESET_ALLOWLIST,
        boundary="generic frontend -> dnd2024",
    )


def test_new_service_locator_dependency_is_rejected(tmp_path: Path) -> None:
    service = tmp_path / "src/webui/services/new_service.py"
    service.parent.mkdir(parents=True)
    service.write_text(
        "from src.webui.api import WebAPI\n"
        "def run(api: WebAPI):\n"
        "    return api._reg.list_all()\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError):
        assert_debt_matches_allowlist(
            scan_service_locator_debt(tmp_path), set(), boundary="services -> WebAPI"
        )


def test_removing_allowlist_entry_while_debt_remains_is_rejected() -> None:
    actual = scan_service_locator_debt(ROOT)
    shortened = set(SERVICE_LOCATOR_ALLOWLIST)
    shortened.remove(next(iter(shortened)))

    with pytest.raises(AssertionError):
        assert_debt_matches_allowlist(actual, shortened, boundary="services -> WebAPI")


def test_new_generic_backend_concrete_ruleset_import_is_rejected(tmp_path: Path) -> None:
    module = tmp_path / "src/engine/new_runtime_bridge.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "from src.rulesets.dnd2024.runtime import Dnd2024Runtime\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError):
        assert_debt_matches_allowlist(
            scan_backend_concrete_ruleset_debt(tmp_path),
            set(),
            boundary="generic backend -> dnd2024",
        )


def test_new_generic_frontend_concrete_ruleset_import_is_rejected(tmp_path: Path) -> None:
    component = tmp_path / "frontend-v2/src/components/NewPanel.vue"
    component.parent.mkdir(parents=True)
    component.write_text(
        '<script setup lang="ts">\n'
        "import { submitRulesetIntent } from '@/features/rulesets/dnd2024/api'\n"
        "</script>\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError):
        assert_debt_matches_allowlist(
            scan_frontend_concrete_ruleset_debt(tmp_path),
            set(),
            boundary="generic frontend -> dnd2024",
        )
