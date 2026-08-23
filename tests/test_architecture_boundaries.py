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
