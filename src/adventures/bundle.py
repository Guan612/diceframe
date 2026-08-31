"""Safe loader for standalone, locale-separated adventure packages."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ADVENTURE_GRAPH_FORMAT = "diceframe:adventure-graph-v1"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_REF_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*:[a-z0-9][a-z0-9_.-]*$")
_PACKAGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]*$")
_AUTOMATION_LEVELS = frozenset({"deterministic", "guided", "reference"})
_FORBIDDEN_KEYS = frozenset({
    "python", "javascript", "script", "code", "eval", "module", "callable",
})
_LOCALE_FIELDS = {
    "adventure": frozenset({"name", "summary", "tutorial"}),
    "scene": frozenset({"name", "description"}),
    "npc": frozenset({"name", "description", "summary"}),
    "map_location": frozenset({"name", "description"}),
    "encounter_catalog": frozenset({"name", "labels"}),
}


class AdventureBundleError(ValueError):
    """Raised when an adventure package is incomplete or unsafe."""


@dataclass(frozen=True, slots=True)
class AdventureBundleManifest:
    schema_version: int
    adventure_id: str
    version: str
    format: str
    world_policy: str
    recommended_world_id: str
    required_runtime_id: str
    required_runtime_version: int
    default_locale: str
    supported_locales: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LoadedAdventureBundle:
    root: Path
    manifest: AdventureBundleManifest
    locale: str
    content_digest: str
    entities: dict[str, dict[str, dict[str, Any]]]

    @property
    def adventure(self) -> dict[str, Any]:
        values = self.entities.get("adventure", {})
        if len(values) != 1:  # validated by the loader
            raise AdventureBundleError("adventure package must contain one adventure")
        return deepcopy(next(iter(values.values())))

    def get(self, kind: str, entity_id: str) -> dict[str, Any] | None:
        value = self.entities.get(kind, {}).get(entity_id)
        return deepcopy(value) if value is not None else None

    def list(self, kind: str) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self.entities.get(kind, {}).values()]

    def binding(self, world_id: str) -> dict[str, Any]:
        return {
            "adventure_id": self.manifest.adventure_id,
            "version": self.manifest.version,
            "format": self.manifest.format,
            "content_digest": self.content_digest,
            "world_id": str(world_id or ""),
        }


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdventureBundleError(f"invalid JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AdventureBundleError(f"JSON root must be an object: {path}")
    return value


def _required_text(
    value: Any, field: str, pattern: re.Pattern[str] | None = None,
) -> str:
    parsed = str(value or "").strip()
    if not parsed:
        raise AdventureBundleError(f"{field} must not be empty")
    if pattern is not None and not pattern.fullmatch(parsed):
        raise AdventureBundleError(f"{field} has an invalid format: {parsed}")
    return parsed


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise AdventureBundleError(f"{field} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AdventureBundleError(f"{field} must be a positive integer") from exc
    if parsed < 1:
        raise AdventureBundleError(f"{field} must be a positive integer")
    return parsed


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _validate_no_executable_content(value: dict[str, Any], path: Path) -> None:
    for node in _walk(value):
        forbidden = _FORBIDDEN_KEYS.intersection(str(key).lower() for key in node)
        if forbidden:
            raise AdventureBundleError(
                f"executable content key is forbidden in {path}: {sorted(forbidden)[0]}"
            )


def _merge_locale(target: dict[str, Any], fields: dict[str, Any], kind: str) -> None:
    allowed = _LOCALE_FIELDS.get(kind, frozenset())
    unknown = set(fields).difference(allowed)
    if unknown:
        raise AdventureBundleError(
            f"adventure locale cannot override {kind}.{sorted(unknown)[0]}"
        )
    for key, value in fields.items():
        target[key] = deepcopy(value)


class AdventureBundleLoader:
    """Load and validate installed adventure directories as one atomic unit."""

    def __init__(self, adventures_dir: str | Path):
        self.adventures_dir = Path(adventures_dir)

    def list(self, locale: str = "") -> list[LoadedAdventureBundle]:
        if not self.adventures_dir.is_dir():
            return []
        return [
            self.load(path.name, locale)
            for path in sorted(self.adventures_dir.iterdir())
            if path.is_dir() and (path / "manifest.json").is_file()
        ]

    def resolve(self, adventure_id: str, locale: str = "") -> LoadedAdventureBundle:
        wanted = _required_text(adventure_id, "adventure_id", _PACKAGE_ID_RE)
        matches = [
            bundle for bundle in self.list(locale)
            if bundle.manifest.adventure_id == wanted
        ]
        if len(matches) != 1:
            raise AdventureBundleError(
                f"adventure package is {'missing' if not matches else 'duplicated'}: {wanted}"
            )
        return matches[0]

    def load(self, directory_id: str, locale: str = "") -> LoadedAdventureBundle:
        directory_id = _required_text(directory_id, "directory_id", _ID_RE)
        base = self.adventures_dir.resolve()
        root = (base / directory_id).resolve()
        if not root.is_relative_to(base) or not root.is_dir():
            raise AdventureBundleError(f"adventure package does not exist: {directory_id}")
        manifest = self._manifest(root)
        active_locale = self._locale(manifest, locale)
        entities, source_paths = self._entities(root)
        self._validate_graph(entities)
        self._apply_locale(root, manifest.default_locale, entities)
        if active_locale != manifest.default_locale:
            self._apply_locale(root, active_locale, entities)
        locale_paths = (
            sorted((root / "locales").rglob("*.json"))
            if (root / "locales").is_dir()
            else []
        )
        digest = self._digest(root, root / "manifest.json", *source_paths, *locale_paths)
        return LoadedAdventureBundle(
            root=root,
            manifest=manifest,
            locale=active_locale,
            content_digest=digest,
            entities=entities,
        )

    def _manifest(self, root: Path) -> AdventureBundleManifest:
        raw = _read_object(root / "manifest.json")
        if _positive_int(raw.get("schema_version"), "schema_version") != 1:
            raise AdventureBundleError("unsupported adventure manifest schema")
        runtime = raw.get("required_runtime")
        if not isinstance(runtime, dict):
            raise AdventureBundleError("required_runtime must be an object")
        locales = raw.get("supported_locales")
        if not isinstance(locales, list) or not locales:
            raise AdventureBundleError("supported_locales must be a non-empty array")
        parsed_locales = tuple(_required_text(item, "supported_locale") for item in locales)
        if len(set(parsed_locales)) != len(parsed_locales):
            raise AdventureBundleError("supported_locales must not contain duplicates")
        default_locale = _required_text(raw.get("default_locale"), "default_locale")
        if default_locale not in parsed_locales:
            raise AdventureBundleError("default_locale must be listed in supported_locales")
        world_policy = _required_text(raw.get("world_policy"), "world_policy")
        if world_policy not in {"fixed", "portable", "agnostic"}:
            raise AdventureBundleError("world_policy must be fixed, portable, or agnostic")
        format_id = _required_text(raw.get("format"), "format", _PACKAGE_ID_RE)
        if format_id != ADVENTURE_GRAPH_FORMAT:
            raise AdventureBundleError(f"unsupported adventure format: {format_id}")
        recommended_world_id = str(raw.get("recommended_world_id") or "").strip()
        if world_policy == "fixed" and not recommended_world_id:
            raise AdventureBundleError("fixed adventures require recommended_world_id")
        return AdventureBundleManifest(
            schema_version=1,
            adventure_id=_required_text(raw.get("adventure_id"), "adventure_id", _PACKAGE_ID_RE),
            version=_required_text(raw.get("version"), "version"),
            format=format_id,
            world_policy=world_policy,
            recommended_world_id=recommended_world_id,
            required_runtime_id=_required_text(
                runtime.get("id"), "required_runtime.id", _PACKAGE_ID_RE,
            ),
            required_runtime_version=_positive_int(
                runtime.get("minimum_version"), "required_runtime.minimum_version",
            ),
            default_locale=default_locale,
            supported_locales=parsed_locales,
        )

    @staticmethod
    def _locale(manifest: AdventureBundleManifest, requested: str) -> str:
        normalized = str(requested or "").replace("_", "-")
        if normalized in manifest.supported_locales:
            return normalized
        base = normalized.split("-", 1)[0].lower()
        for candidate in manifest.supported_locales:
            if candidate.split("-", 1)[0].lower() == base:
                return candidate
        return manifest.default_locale

    def _entities(
        self, root: Path,
    ) -> tuple[dict[str, dict[str, dict[str, Any]]], list[Path]]:
        paths = [root / "adventure.json"]
        content_root = root / "content"
        if content_root.is_dir():
            paths.extend(sorted(content_root.rglob("*.json")))
        entities: dict[str, dict[str, dict[str, Any]]] = {}
        for path in paths:
            value = _read_object(path)
            _validate_no_executable_content(value, path)
            if _positive_int(value.get("schema_version"), "entity.schema_version") != 1:
                raise AdventureBundleError(f"unsupported adventure entity schema: {path}")
            kind = _required_text(value.get("kind"), "entity.kind", _ID_RE)
            entity_id = _required_text(value.get("id"), "entity.id", _ID_RE)
            _required_text(value.get("source_ref"), "entity.source_ref")
            automation = _required_text(value.get("automation_level"), "automation_level")
            if automation not in _AUTOMATION_LEVELS:
                raise AdventureBundleError(f"invalid automation_level in {path}")
            bucket = entities.setdefault(kind, {})
            if entity_id in bucket:
                raise AdventureBundleError(f"duplicate adventure entity {kind}:{entity_id}")
            bucket[entity_id] = value
        return entities, paths

    def _validate_graph(self, entities: dict[str, dict[str, dict[str, Any]]]) -> None:
        adventures = entities.get("adventure", {})
        if len(adventures) != 1:
            raise AdventureBundleError("adventure package must contain one adventure entity")
        adventure = next(iter(adventures.values()))
        chapters = {
            str(item.get("id") or ""): item
            for item in adventure.get("chapters") or [] if isinstance(item, dict)
        }
        steps = {
            str(item.get("id") or ""): item
            for item in adventure.get("steps") or [] if isinstance(item, dict)
        }
        choices = {
            str(item.get("id") or ""): item
            for item in adventure.get("choices") or [] if isinstance(item, dict)
        }
        encounter_ids = {
            str(preset.get("id") or "")
            for catalog in entities.get("encounter_catalog", {}).values()
            for preset in catalog.get("presets") or []
            if isinstance(preset, dict) and str(preset.get("id") or "")
        }
        if str(adventure.get("start_step_id") or "") not in steps:
            raise AdventureBundleError("adventure start_step_id is invalid")
        for step_id, step in steps.items():
            if not _ID_RE.fullmatch(step_id):
                raise AdventureBundleError(f"adventure step id is invalid: {step_id}")
            if str(step.get("chapter_id") or "") not in chapters:
                raise AdventureBundleError(f"adventure step has no chapter: {step_id}")
            scene_ref = str(step.get("scene_ref") or "")
            if scene_ref and not self._has_ref(entities, scene_ref):
                raise AdventureBundleError(f"adventure scene ref is missing: {scene_ref}")
            encounter_id = str(step.get("encounter_preset_id") or "")
            if encounter_id and encounter_id not in encounter_ids:
                raise AdventureBundleError(
                    f"adventure encounter preset is missing: {encounter_id}"
                )
            for choice_id in step.get("choice_ids") or []:
                choice = choices.get(str(choice_id))
                if choice is None or choice.get("step_id") != step_id:
                    raise AdventureBundleError(f"adventure choice is invalid: {choice_id}")
        for choice_id, choice in choices.items():
            if not _ID_RE.fullmatch(choice_id):
                raise AdventureBundleError(f"adventure choice id is invalid: {choice_id}")
            next_step = str(choice.get("next_step_id") or "")
            if next_step and next_step not in steps:
                raise AdventureBundleError(f"adventure next step is missing: {next_step}")
        for scene in entities.get("scene", {}).values():
            for ref in [scene.get("map_location_ref"), *(scene.get("npc_refs") or [])]:
                if ref and not self._has_ref(entities, str(ref)):
                    raise AdventureBundleError(f"adventure entity ref is missing: {ref}")

    @staticmethod
    def _has_ref(entities: dict[str, dict[str, dict[str, Any]]], ref: str) -> bool:
        if not _REF_RE.fullmatch(ref):
            return False
        kind, entity_id = ref.split(":", 1)
        return entity_id in entities.get(kind, {})

    def _apply_locale(
        self, root: Path, locale: str, entities: dict[str, dict[str, dict[str, Any]]],
    ) -> None:
        locale_root = root / "locales" / locale
        if not locale_root.is_dir():
            raise AdventureBundleError(f"adventure locale directory is missing: {locale}")
        for path in sorted(locale_root.rglob("*.json")):
            value = _read_object(path)
            if _positive_int(value.get("locale_schema_version"), "locale_schema_version") != 1:
                raise AdventureBundleError(f"unsupported adventure locale schema: {path}")
            if str(value.get("locale") or "") != locale:
                raise AdventureBundleError(f"adventure locale file has the wrong locale: {path}")
            target = value.get("target")
            fields = value.get("fields")
            if not isinstance(target, dict) or not isinstance(fields, dict):
                raise AdventureBundleError(f"adventure locale target/fields are invalid: {path}")
            kind = _required_text(target.get("kind"), "locale.target.kind", _ID_RE)
            entity_id = _required_text(target.get("id"), "locale.target.id", _ID_RE)
            entity = entities.get(kind, {}).get(entity_id)
            if entity is None:
                raise AdventureBundleError(f"adventure locale target is missing: {kind}:{entity_id}")
            _merge_locale(entity, fields, kind)

    @staticmethod
    def _digest(root: Path, *paths: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(paths, key=lambda item: item.as_posix()):
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            value = json.loads(path.read_text(encoding="utf-8"))
            digest.update(
                json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
            )
        return f"sha256:{digest.hexdigest()}"
