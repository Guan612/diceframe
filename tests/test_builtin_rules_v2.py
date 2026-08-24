from __future__ import annotations

import pytest

from src.rules.loader import RuleBundleLoader
from src.rules.rule_system import RuleSystem


RULE_IDS = (
    "freeform_fantasy",
    "freeform_coc",
    "freeform_cyberpunk",
    "freeform_wuxia",
    "tavern_free",
)
LEGACY_RULES = "tests/fixtures/legacy_rules"


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_builtin_rule_locales_share_mechanics(rule_id: str) -> None:
    loader = RuleBundleLoader()
    systems = [
        RuleSystem(loader.load_rule("templates/rules", rule_id, locale))
        for locale in ("zh-CN", "en", "ja")
    ]

    assert all(system.template.get("rule_schema_version") == 2 for system in systems)
    assert len({system.mechanics_snapshot() for system in systems}) == 1


def test_builtin_rule_locale_base_fallback_and_display_name() -> None:
    loader = RuleBundleLoader()
    template = loader.load_rule("templates/rules", "freeform_fantasy", "en-US")

    assert template["active_locale"] == "en"
    assert template["rule_name"] == "Classic Fantasy Freeform"


@pytest.mark.parametrize(
    ("locale", "sanity_name", "luck_name"),
    (
        ("zh-CN", "理智值", "幸运值"),
        ("en", "Sanity", "Luck"),
        ("ja", "正気度", "幸運"),
    ),
)
def test_coc_special_stats_locale_overlays(locale: str, sanity_name: str, luck_name: str) -> None:
    loader = RuleBundleLoader()
    system = RuleSystem(loader.load_rule("templates/rules", "freeform_coc", locale))
    stats = {str(item["key"]): item for item in system.template["special_stats"]}

    assert stats["sanity"]["name"] == sanity_name
    assert stats["luck"]["name"] == luck_name
    assert stats["sanity"]["max"] == 99
    assert stats["luck"]["max"] == 99


def test_legacy_full_copy_rules_remain_loadable() -> None:
    loader = RuleBundleLoader()

    for path in (
        f"{LEGACY_RULES}/freeform_fantasy_en.json",
        f"{LEGACY_RULES}/freeform_coc_ja.json",
        f"{LEGACY_RULES}/tavern_free_en.json",
    ):
        template = loader.load(path)
        assert template["rule_id"]
