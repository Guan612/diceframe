from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
FORBIDDEN_CORE_IMPORTS = (
    "src.compat.rules_v1",
    "src.compat.content_v1",
    "src.compat.worlds_v1",
    "src.webui",
    "src.rulesets.dnd2024",
)


def test_core_domains_do_not_import_compat_or_webui_adapters() -> None:
    paths = [ROOT / "src" / name for name in ("engine", "generation", "lorebook", "memory", "rules")]
    violations: list[str] = []
    for directory in paths:
        for path in directory.rglob("*.py"):
            if path.name == "loader.py":
                continue
            text = path.read_text(encoding="utf-8")
            for imported in FORBIDDEN_CORE_IMPORTS:
                if imported in text:
                    violations.append(f"{path.relative_to(ROOT)} imports {imported}")
    assert not violations, "\n".join(violations)


def test_builtin_v2_rules_do_not_reintroduce_full_locale_copies() -> None:
    product_rules = ROOT / "templates" / "rules"
    legacy_copies = []
    for path in (*product_rules.glob("*_en.json"), *product_rules.glob("*_ja.json")):
        try:
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not data.get("abstract"):
            legacy_copies.append(path)
    assert not legacy_copies
    fixtures = ROOT / "tests" / "fixtures" / "legacy_rules"
    assert list(fixtures.glob("*_en.json"))


def test_ruleset_runtime_layer_does_not_import_webui_or_compat() -> None:
    directory = ROOT / "src" / "rulesets"
    violations: list[str] = []
    for path in directory.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for imported in ("src.webui", "src.compat"):
            if imported in text:
                violations.append(f"{path.relative_to(ROOT)} imports {imported}")
    assert not violations, "\n".join(violations)


def test_dnd_combat_does_not_import_campaign_or_ui_layers() -> None:
    directory = ROOT / "src" / "rulesets" / "dnd2024" / "combat"
    violations: list[str] = []
    for path in directory.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for imported in ("src.rulesets.dnd2024.campaign", "src.webui", "frontend-v2"):
            if imported in text:
                violations.append(f"{path.relative_to(ROOT)} imports {imported}")
    assert not violations, "\n".join(violations)


def test_dnd_adventures_are_standalone_and_not_copied_into_ruleset() -> None:
    ruleset = ROOT / "templates" / "rulesets" / "dnd2024_srd"
    assert not list((ruleset / "presets" / "adventures").glob("*.json"))
    assert not list(ruleset.rglob("*lanterns_of_greymoor*"))

    installed = ROOT / "templates" / "adventures" / "lanterns_of_greymoor"
    assert (installed / "manifest.json").is_file()
    runtime = (ROOT / "src" / "rulesets" / "dnd2024" / "runtime.py").read_text(
        encoding="utf-8"
    )
    assert "from src.adventures import" in runtime


def test_standalone_adventure_loader_has_no_dnd_or_webui_dependency() -> None:
    directory = ROOT / "src" / "adventures"
    violations = []
    for path in directory.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for imported in ("src.rulesets.dnd2024", "src.webui", "src.compat"):
            if imported in text:
                violations.append(f"{path.relative_to(ROOT)} imports {imported}")
    assert not violations, "\n".join(violations)


def test_v2_locale_authority_is_backend_materialized() -> None:
    rules_service = (ROOT / "src" / "webui" / "services" / "rules.py").read_text(encoding="utf-8")
    create_view = (ROOT / "frontend-v2" / "src" / "features" / "create" / "CreateView.vue").read_text(encoding="utf-8")
    assert "RuleBundleLoader" in rules_service
    assert "rule_name_en" not in create_view
    assert "description_en" not in create_view
