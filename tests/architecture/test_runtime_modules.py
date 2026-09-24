"""Runtime module dependency, ownership and aggregate-size boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
MODULES = SRC / "engine" / "modules"
MAX_TOP_LEVEL_FIELDS = 95


def _runtime_nodes(node: ast.AST):
    """Ignore type-only bodies, but still inspect runtime else branches."""
    yield node
    if isinstance(node, ast.If) and (
        isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"
        or isinstance(node.test, ast.Attribute) and node.test.attr == "TYPE_CHECKING"
    ):
        for child in node.orelse:
            yield from _runtime_nodes(child)
        return
    for child in ast.iter_child_nodes(node):
        yield from _runtime_nodes(child)


def test_runtime_modules_do_not_import_game_instance() -> None:
    violations: list[str] = []
    paths = [SRC / "engine" / "module_state.py", *sorted(MODULES.glob("*.py"))]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in _runtime_nodes(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    parts = list(path.relative_to(ROOT).with_suffix("").parts[:-1])
                    module = ".".join(parts[:len(parts) - node.level + 1] + ([module] if module else []))
                names = [module, *(f"{module}.{alias.name}" for alias in node.names)]
            if any(name == "src.engine.game_instance" or name.startswith("src.engine.game_instance.") for name in names):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: runtime GameInstance import")
    assert not violations, "\n".join(violations)


def test_only_module_owners_write_module_slots() -> None:
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path.parent == MODULES or path == SRC / "migrations" / "instance.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            # Store/Del also covers annotated/augmented assignments and nested
            # indexing, so a second subscript cannot bypass slot ownership.
            if not isinstance(node, ast.Subscript) or not isinstance(node.ctx, (ast.Store, ast.Del)):
                continue
            value = node.value
            while isinstance(value, ast.Subscript):
                value = value.value
            if isinstance(value, ast.Attribute) and value.attr == "modules":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: module slot write outside owner")
    assert not violations, "\n".join(violations)


def test_game_instance_top_level_field_count_does_not_grow() -> None:
    path = SRC / "engine" / "game_instance.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    instance = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "GameInstance")
    count = sum(isinstance(node, ast.AnnAssign) for node in instance.body)
    assert count <= MAX_TOP_LEVEL_FIELDS, f"GameInstance has {count} fields (maximum {MAX_TOP_LEVEL_FIELDS})"
