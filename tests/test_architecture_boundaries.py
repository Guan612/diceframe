from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
FORBIDDEN_CORE_IMPORTS = (
    "src.compat.rules_v1",
    "src.compat.content_v1",
    "src.compat.worlds_v1",
    "src.webui",
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


def test_v2_locale_authority_is_backend_materialized() -> None:
    rules_service = (ROOT / "src" / "webui" / "services" / "rules.py").read_text(encoding="utf-8")
    create_view = (ROOT / "frontend-v2" / "src" / "features" / "create" / "CreateView.vue").read_text(encoding="utf-8")
    assert "RuleBundleLoader" in rules_service
    assert "rule_name_en" not in create_view
    assert "description_en" not in create_view
