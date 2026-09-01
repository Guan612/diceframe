"""Architecture debt scanners used by CI fitness-function tests.

The scanners deliberately operate on dependency-bearing syntax rather than
source snapshots.  Existing debt is recorded by the tests as an explicit
allowlist; new files, dependency modes, concrete runtime identifiers, event
namespaces, or concrete frontend imports therefore fail the architecture gate.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True, order=True)
class DependencyDebt:
    """One stable dependency-boundary violation discovered in production code."""

    path: str
    kind: str
    target: str


_BACKEND_GENERIC_DIRECTORIES = (
    "src/commands",
    "src/engine",
    "src/llm",
    "src/webui/services",
)
_PYTHON_SUFFIX = ".py"
_FRONTEND_SUFFIXES = frozenset({".js", ".jsx", ".ts", ".tsx", ".vue"})
_CONCRETE_RULESET_MODULE = "src.rulesets.dnd2024"
_CONCRETE_RUNTIME_ID = "core:dnd2024"
_CONCRETE_EVENT_PREFIX = "dnd2024."
_CONCRETE_FRONTEND_SEGMENT = "rulesets/dnd2024/"
_CONCRETE_FRONTEND_OWNER = "frontend-v2/src/features/rulesets/dnd2024"

# These patterns only inspect module specifiers in static import/export
# declarations and dynamic import() expressions.  They do not match arbitrary
# strings or UI copy in Vue/TypeScript source.
_STATIC_IMPORT = re.compile(
    r"(?:^|[;\n])\s*(?:import|export)\s+(?:[^'\"\n]*?\s+from\s+)?['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
_DYNAMIC_IMPORT = re.compile(r"\bimport\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _python_files(root: Path, directories: Iterable[str]) -> Iterable[Path]:
    for directory in directories:
        base = root / directory
        if base.exists():
            yield from sorted(base.rglob(f"*{_PYTHON_SUFFIX}"))


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _function_arguments(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterable[ast.arg]:
    yield from node.args.posonlyargs
    yield from node.args.args
    yield from node.args.kwonlyargs
    if node.args.vararg is not None:
        yield node.args.vararg
    if node.args.kwarg is not None:
        yield node.args.kwarg


def _mentions_webapi(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name) and node.id == "WebAPI":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "WebAPI":
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.rsplit(".", 1)[-1] == "WebAPI":
                return True
    return False


def scan_service_locator_debt(root: Path) -> set[DependencyDebt]:
    """Find services that receive or reach back through the WebAPI facade."""

    found: set[DependencyDebt] = set()
    for path in _python_files(root, ("src/webui/services",)):
        relative = _relative(root, path)
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "src.webui.api":
                if any(alias.name == "WebAPI" for alias in node.names):
                    found.add(DependencyDebt(relative, "webapi_import", "src.webui.api.WebAPI"))
            elif isinstance(node, ast.Import):
                if any(alias.name == "src.webui.api" for alias in node.names):
                    found.add(DependencyDebt(relative, "webapi_import", "src.webui.api"))

            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            api_arguments = {
                argument.arg: argument
                for argument in _function_arguments(node)
                if argument.arg == "api"
            }
            if not api_arguments:
                continue
            if any(_mentions_webapi(argument.annotation) for argument in api_arguments.values()):
                found.add(DependencyDebt(relative, "webapi_parameter", "WebAPI"))

            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Attribute)
                    and isinstance(child.value, ast.Name)
                    and child.value.id == "api"
                    and child.attr.startswith("_")
                    and not child.attr.startswith("__")
                ):
                    found.add(DependencyDebt(relative, "private_facade_access", "api._*"))
                elif (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and isinstance(child.func.value, ast.Name)
                    and child.func.value.id == "api"
                    and not child.func.attr.startswith("_")
                ):
                    found.add(DependencyDebt(relative, "facade_service_call", "api.<service>()"))
    return found


def _import_modules(node: ast.Import | ast.ImportFrom) -> Iterable[str]:
    if isinstance(node, ast.Import):
        yield from (alias.name for alias in node.names)
        return
    if node.module:
        yield node.module


def scan_backend_concrete_ruleset_debt(root: Path) -> set[DependencyDebt]:
    """Find concrete D&D knowledge in generic backend production paths."""

    found: set[DependencyDebt] = set()
    for path in _python_files(root, _BACKEND_GENERIC_DIRECTORIES):
        relative = _relative(root, path)
        for node in ast.walk(_tree(path)):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for module in _import_modules(node):
                    if module == _CONCRETE_RULESET_MODULE or module.startswith(
                        f"{_CONCRETE_RULESET_MODULE}."
                    ):
                        found.add(DependencyDebt(relative, "concrete_import", module))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value == _CONCRETE_RUNTIME_ID:
                    found.add(DependencyDebt(relative, "runtime_id", node.value))
                elif node.value.startswith(_CONCRETE_EVENT_PREFIX):
                    found.add(DependencyDebt(relative, "event_type", node.value))
    return found


def _frontend_module_specifiers(source: str) -> Iterable[str]:
    for pattern in (_STATIC_IMPORT, _DYNAMIC_IMPORT):
        yield from (match.group(1) for match in pattern.finditer(source))


def scan_frontend_concrete_ruleset_debt(root: Path) -> set[DependencyDebt]:
    """Find concrete D&D imports outside the D&D-owned frontend feature."""

    source_root = root / "frontend-v2" / "src"
    found: set[DependencyDebt] = set()
    if not source_root.exists():
        return found
    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or path.suffix not in _FRONTEND_SUFFIXES:
            continue
        relative = _relative(root, path)
        if relative == _CONCRETE_FRONTEND_OWNER or relative.startswith(
            f"{_CONCRETE_FRONTEND_OWNER}/"
        ):
            continue
        source = path.read_text(encoding="utf-8-sig")
        for module in _frontend_module_specifiers(source):
            normalized = module.replace("\\", "/")
            if _CONCRETE_FRONTEND_SEGMENT in normalized:
                found.add(DependencyDebt(relative, "concrete_import", normalized))
    return found


def assert_debt_matches_allowlist(
    actual: set[DependencyDebt],
    allowed: set[DependencyDebt] | frozenset[DependencyDebt],
    *,
    boundary: str,
) -> None:
    """Require the allowlist to exactly describe current debt.

    Exact matching makes stale entries fail after a migration, forcing the
    allowlist to shrink.  Unlisted entries fail immediately when debt grows.
    """

    unexpected = sorted(actual - allowed)
    stale = sorted(allowed - actual)
    if not unexpected and not stale:
        return
    details = [f"{boundary} debt baseline changed:"]
    details.extend(f"  unexpected: {item}" for item in unexpected)
    details.extend(f"  stale allowlist entry: {item}" for item in stale)
    raise AssertionError("\n".join(details))


def debt_by_path(debt: Iterable[DependencyDebt]) -> Mapping[str, tuple[DependencyDebt, ...]]:
    """Group debt for concise diagnostics and release/report summaries."""

    grouped: dict[str, list[DependencyDebt]] = {}
    for item in sorted(debt):
        grouped.setdefault(item.path, []).append(item)
    return {path: tuple(items) for path, items in grouped.items()}
