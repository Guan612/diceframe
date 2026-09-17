"""The D&D 2024 class feature boundary.

One module answers "what does this character actually have": its class, its
class level, the class features it owns, their simple scalar parameters, its
class resource maxima, and the combat capabilities it may declare right now.

It never mutates state, never resolves dice, and never touches CombatState.
Callers (combat, view, projection, frontend payloads) ask this boundary instead
of each re-parsing the class level for themselves.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from src.rulesets.bundle import LoadedRulesetBundle
from src.rulesets.dnd2024.progression.catalog import (
    Dnd2024ProgressionCatalog,
    ProgressionCatalogError,
)

from .combat import (
    CombatContext,
    combat_capabilities as _project_capabilities,
    unarmed_strike_profile as _unarmed_profile,
)
from .models import (
    ClassFeatureDefinition,
    ClassFeatureError,
    CombatCapabilityView,
    Dnd2024ClassFeatureCatalog,
    FeatureCapability,
    FeatureView,
)
from .resources import (
    Dnd2024ClassResourceCatalog,
    ResourceDefinition,
    resource_state,
)


def _humanize(feature_id: str) -> str:
    return str(feature_id).replace("_", " ").strip().title()


class Dnd2024ClassFeatureResolver:
    """Resolve class features, class resources, and combat capabilities."""

    catalog: Dnd2024ClassFeatureCatalog
    resources: Dnd2024ClassResourceCatalog
    progression: Dnd2024ProgressionCatalog | None
    available: bool

    def __init__(self, bundle: LoadedRulesetBundle):
        self.bundle = bundle
        # 与 ``Dnd2024Runtime._sync_class_resources`` 相同的边界：bundle 没有
        # 声明这套可选内容时，职业特性整体降级为「不存在」，而不是让每一个
        # 角色投影都失败。声明存在但格式非法时仍然 fail closed。
        self.available = (
            bundle.get("class_feature_catalog", "srd_class_features") is not None
            and bundle.get("rest_catalog", "srd_recovery") is not None
            and bundle.get("progression_catalog", "srd_classes") is not None
        )
        if not self.available:
            self.catalog = Dnd2024ClassFeatureCatalog.empty()
            self.resources = Dnd2024ClassResourceCatalog.empty()
            self.progression = None
            return
        self.catalog = Dnd2024ClassFeatureCatalog.from_bundle(bundle)
        self.resources = Dnd2024ClassResourceCatalog.from_bundle(bundle)
        self.progression = Dnd2024ProgressionCatalog.from_bundle(bundle)
        self._validate_declarations()

    # ------------------------------------------------------------------
    # identity
    # ------------------------------------------------------------------

    def class_state(self, character: Mapping[str, Any] | None) -> tuple[str, int] | None:
        """Return ``(class_id, level)`` for a single-class character, else ``None``.

        A character that is not a professional D&D character (a companion with a
        partial sheet, a legacy import, an enemy) simply has no class features;
        this boundary degrades to "owns nothing" instead of raising.
        """

        if not isinstance(character, Mapping):
            return None
        build = character.get("build")
        if not isinstance(build, Mapping):
            return None
        class_levels = build.get("class_levels")
        if not isinstance(class_levels, list) or len(class_levels) != 1:
            return None
        row = class_levels[0]
        if not isinstance(row, Mapping):
            return None
        class_ref = str(row.get("class_ref") or "")
        class_id = class_ref.removeprefix("class:")
        if not class_id:
            return None
        level = row.get("level")
        if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 20:
            return None
        return class_id, level

    # ------------------------------------------------------------------
    # feature availability
    # ------------------------------------------------------------------

    def features_for(
        self, character: Mapping[str, Any] | None,
    ) -> tuple[ClassFeatureDefinition, ...]:
        """Every declared feature the character owns, in catalog order."""

        state = self.class_state(character)
        if state is None:
            return ()
        class_id, level = state
        granted = self._granted_feature_ids(class_id, level)
        owned: list[ClassFeatureDefinition] = []
        for feature_id in self.catalog.by_class.get(class_id, ()):
            definition = self.catalog.features.get(feature_id)
            if definition is None or definition.minimum_level > level:
                continue
            if definition.option_of:
                # 选项特性（例如 Monk's Focus 的三个用法）只有在授予它的
                # 特性已经被职业表授予时才算拥有。
                if definition.option_of not in granted:
                    continue
            elif feature_id not in granted:
                continue
            owned.append(definition)
        return tuple(owned)

    def has_feature(
        self, character: Mapping[str, Any] | None, feature_id: str,
    ) -> bool:
        wanted = str(feature_id or "")
        if not wanted:
            return False
        return any(item.id == wanted for item in self.features_for(character))

    def feature_value(
        self,
        character: Mapping[str, Any] | None,
        feature_id: str,
        key: str,
        default: Any = None,
    ) -> Any:
        """One scalar/table parameter of an owned feature.

        A parameter named ``<key>_track`` resolves against the class progression
        table, so a level-derived value (the Martial Arts die) is read from the
        same bundle table that advancement uses instead of being copied here.
        An optional ``<key>_format`` template renders the table value into its
        printable form (``1d{die}``); it is a single placeholder, never an
        expression.
        """

        definition = next(
            (item for item in self.features_for(character) if item.id == str(feature_id)),
            None,
        )
        if definition is None:
            return default
        return self._value(definition, character, key, default)

    def feature_views(
        self, character: Mapping[str, Any] | None,
    ) -> tuple[FeatureView, ...]:
        """Presentation-safe views of the owned features, with resolved values."""

        views: list[FeatureView] = []
        for definition in self.features_for(character):
            values: dict[str, Any] = {}
            for key, raw in definition.parameters.items():
                if key.endswith("_format"):
                    continue
                if key.endswith("_track"):
                    resolved = self._value(
                        definition, character, key[: -len("_track")], None,
                    )
                    if resolved is not None:
                        values[key[: -len("_track")]] = resolved
                else:
                    values[key] = deepcopy(raw)
            views.append(FeatureView(
                id=definition.id,
                name=self.catalog.label(definition.id, _humanize(definition.id)),
                summary=definition.summary,
                source_ref=definition.source_ref,
                minimum_level=definition.minimum_level,
                values=values,
            ))
        return tuple(views)

    def actor_projection(self, character: Mapping[str, Any] | None) -> dict[str, Any]:
        """One-pass projection of everything combat needs from this boundary.

        Combat keeps consuming plain data: the actor's canonical class
        resources (with their localized names), and the feature-derived
        Unarmed Strike parameters.  Neither the combat engine nor the frontend
        re-derives a class level or a Martial Arts die.
        """

        owned = self.features_for(character)
        return {
            "class_resources": [
                definition.to_dict()
                for definition in self._resource_definitions(owned, character)
            ],
            "unarmed_damage_die": self._unarmed_die(owned, character),
            "unarmed_ability_choice": list(self._ability_choice(owned, character)),
        }

    # ------------------------------------------------------------------
    # class resources
    # ------------------------------------------------------------------

    def class_resource_definition(
        self, character: Mapping[str, Any] | None, resource_id: str,
    ) -> ResourceDefinition | None:
        """The character's own view of one class resource, or ``None`` if unowned."""

        state = self.class_state(character)
        if state is None:
            return None
        class_id, level = state
        wanted = str(resource_id or "")
        declaration = self.resources.declaration(class_id, wanted)
        owner = next(
            (
                definition for definition in self.catalog.class_features(class_id)
                if definition.resource_id == wanted
            ),
            None,
        )
        if declaration is None:
            if owner is None:
                return None
            minimum_level = owner.minimum_level
            source_ref = owner.source_ref
        else:
            minimum_level = declaration.minimum_level
            source_ref = declaration.source_ref
        if level < minimum_level:
            return None
        entry = resource_state(character, wanted)
        current = entry.get("current", 0)
        maximum = entry.get("maximum", 0)
        return ResourceDefinition(
            id=wanted,
            name=self.catalog.label(wanted, _humanize(wanted)),
            current=current if isinstance(current, int) and not isinstance(current, bool) else 0,
            maximum=maximum if isinstance(maximum, int) and not isinstance(maximum, bool) else 0,
            minimum_level=minimum_level,
            source_ref=source_ref,
            recovery=declaration.recovery() if declaration is not None else {},
        )

    def resource_definitions(
        self, character: Mapping[str, Any] | None,
    ) -> tuple[ResourceDefinition, ...]:
        """Every class resource declared by the features the character owns."""

        return self._resource_definitions(self.features_for(character), character)

    def _resource_definitions(
        self,
        owned: tuple[ClassFeatureDefinition, ...],
        character: Mapping[str, Any] | None,
    ) -> tuple[ResourceDefinition, ...]:
        resource_ids: list[str] = []
        for definition in owned:
            if definition.resource_id and definition.resource_id not in resource_ids:
                resource_ids.append(definition.resource_id)
        result: list[ResourceDefinition] = []
        for resource_id in resource_ids:
            resolved = self.class_resource_definition(character, resource_id)
            if resolved is not None:
                result.append(resolved)
        return tuple(result)

    # ------------------------------------------------------------------
    # combat capabilities
    # ------------------------------------------------------------------

    def combat_capabilities(
        self,
        character: Mapping[str, Any] | None,
        combat_context: Mapping[str, Any] | None = None,
        *,
        include_unavailable: bool = False,
    ) -> tuple[CombatCapabilityView, ...]:
        """Capabilities the character may declare in the given combat context."""

        owned = self.features_for(character)
        definitions = {
            definition.id: definition for definition in self.resource_definitions(character)
        }
        return _project_capabilities(
            self.catalog,
            owned,
            CombatContext.from_economy(combat_context),
            definitions,
            include_unavailable=include_unavailable,
        )

    def declared_capability(
        self, character: Mapping[str, Any] | None, capability_id: str,
    ) -> FeatureCapability | None:
        """The owned capability declaration with this id, or ``None``."""

        wanted = str(capability_id or "")
        for definition in self.features_for(character):
            for capability in definition.capabilities:
                if capability.id == wanted:
                    return capability
        return None

    def unarmed_strike_die(self, character: Mapping[str, Any] | None) -> str:
        """The feature-derived base damage of this character's Unarmed Strike."""

        return self._unarmed_die(self.features_for(character), character)

    def _unarmed_die(
        self, owned: tuple[ClassFeatureDefinition, ...], character: Mapping[str, Any] | None,
    ) -> str:
        for definition in owned:
            die = self._value(definition, character, "unarmed_damage_die", "")
            if isinstance(die, str) and die:
                return die
        return ""

    def unarmed_ability_choice(
        self, character: Mapping[str, Any] | None,
    ) -> tuple[str, ...]:
        """The abilities this character may use for Unarmed Strikes."""

        return self._ability_choice(self.features_for(character), character)

    def _ability_choice(
        self, owned: tuple[ClassFeatureDefinition, ...], character: Mapping[str, Any] | None,
    ) -> tuple[str, ...]:
        for definition in owned:
            choice = self._value(definition, character, "unarmed_ability_choice", ())
            if isinstance(choice, (list, tuple)) and choice:
                return tuple(str(item) for item in choice)
        return ()

    def effective_unarmed_strike(
        self, character: Mapping[str, Any] | None, base: Mapping[str, Any],
    ) -> dict[str, Any]:
        """The actor-specific effective profile of the canonical Unarmed Strike."""

        return _unarmed_profile(base, martial_arts_die=self.unarmed_strike_die(character))

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _value(
        self,
        definition: ClassFeatureDefinition,
        character: Mapping[str, Any] | None,
        key: str,
        default: Any,
    ) -> Any:
        name = str(key)
        if name in definition.parameters:
            return deepcopy(definition.parameters[name])
        track_id = definition.parameters.get(f"{name}_track")
        if not isinstance(track_id, str) or not track_id:
            return default
        resolved = self._track_value(character, definition.class_id, track_id, default)
        template = definition.parameters.get(f"{name}_format")
        if isinstance(template, str) and template:
            if not isinstance(resolved, int):
                return default
            return template.format(die=resolved)
        return resolved

    def _granted_feature_ids(self, class_id: str, level: int) -> frozenset[str]:
        if self.progression is None:
            return frozenset()
        progression = self.progression.classes.get(str(class_id))
        if progression is None:
            return frozenset()
        granted: set[str] = set()
        for row in progression["features_by_level"][:level]:
            granted.update(str(feature_id) for feature_id in row)
        return frozenset(granted)

    def _track_value(
        self,
        character: Mapping[str, Any] | None,
        class_id: str,
        track_id: str,
        default: Any,
    ) -> Any:
        state = self.class_state(character)
        if state is None or self.progression is None:
            return default
        try:
            snapshot = self.progression.snapshot(f"class:{class_id}", state[1])
        except ProgressionCatalogError:
            return default
        tracks = snapshot["tracks"]
        if track_id not in tracks:
            return default
        return int(tracks[track_id])

    def _validate_declarations(self) -> None:
        """Fail closed when a declared parameter has no backing bundle table."""

        progression_catalog = self.progression
        if progression_catalog is None:  # pragma: no cover - guarded by ``available``
            return
        for definition in self.catalog.features.values():
            progression = progression_catalog.classes.get(definition.class_id)
            if progression is None:
                raise ClassFeatureError(
                    f"class feature {definition.id} references an unknown class table"
                )
            for key, value in definition.parameters.items():
                if key.endswith("_format"):
                    if (
                        not isinstance(value, str)
                        or value.count("{die}") != 1
                        or value.replace("{die}", "").count("{") != 0
                        or value.replace("{die}", "").count("}") != 0
                    ):
                        raise ClassFeatureError(
                            f"{definition.id}.{key} must be a single-placeholder template"
                        )
                    continue
                if not key.endswith("_track"):
                    continue
                if not isinstance(value, str) or not value:
                    raise ClassFeatureError(f"{definition.id}.{key} must name a track")
                if value not in progression["tracks"]:
                    raise ClassFeatureError(
                        f"{definition.id}.{key} names an unknown progression track: {value}"
                    )
            if definition.resource_id:
                declaration = self.resources.declaration(
                    definition.class_id, definition.resource_id,
                )
                if declaration is None:
                    raise ClassFeatureError(
                        f"{definition.id} references an undeclared class resource: "
                        f"{definition.resource_id}"
                    )
