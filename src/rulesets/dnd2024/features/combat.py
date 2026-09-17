"""Combat capability projection for D&D 2024 class features.

The combat engine consumes a *capability id*, its action/resource cost, whether
it needs a hostile target, and the underlying canonical actions it performs.
Which class grants that capability, and from which level, is answered here --
never by the combat engine, and never by the frontend.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from .models import (
    ClassFeatureDefinition,
    CombatCapabilityView,
    Dnd2024ClassFeatureCatalog,
    CapabilityCostView,
    FeatureCapability,
)
from .resources import ResourceDefinition


@dataclass(frozen=True, slots=True)
class CombatContext:
    """The action-economy budget a capability is evaluated against."""

    action: int = 0
    bonus_action: int = 0
    reaction: int = 0

    @classmethod
    def from_economy(cls, economy: Mapping[str, Any] | None) -> CombatContext:
        source: Mapping[str, Any] = economy if isinstance(economy, Mapping) else {}

        def budget(key: str) -> int:
            value = source.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, int):
                return 0
            return max(0, value)

        return cls(
            action=budget("action"),
            bonus_action=budget("bonus_action"),
            reaction=budget("reaction"),
        )

    def remaining(self, action: str) -> int:
        if action == "bonus_action":
            return self.bonus_action
        if action == "action":
            return self.action
        return 0


def _cost_views(
    catalog: Dnd2024ClassFeatureCatalog,
    capability: FeatureCapability,
    context: CombatContext,
    definitions: Mapping[str, ResourceDefinition],
) -> tuple[CapabilityCostView, ...]:
    views: list[CapabilityCostView] = []
    if capability.cost.action:
        views.append(CapabilityCostView(
            kind=capability.cost.action,
            name=catalog.label(capability.cost.action, capability.cost.action),
            amount=1,
            current=context.remaining(capability.cost.action),
            maximum=1,
        ))
    for resource_cost in capability.cost.resources:
        definition = definitions.get(resource_cost.resource_id)
        views.append(CapabilityCostView(
            kind="resource",
            name=catalog.label(resource_cost.resource_id, resource_cost.resource_id),
            amount=resource_cost.amount,
            current=int(definition.current) if definition is not None else 0,
            maximum=int(definition.maximum) if definition is not None else 0,
        ))
    return tuple(views)


def _blocked_reason(
    catalog: Dnd2024ClassFeatureCatalog,
    capability: FeatureCapability,
    context: CombatContext,
    definitions: Mapping[str, ResourceDefinition],
) -> str:
    for resource_cost in capability.cost.resources:
        definition = definitions.get(resource_cost.resource_id)
        name = catalog.label(resource_cost.resource_id, resource_cost.resource_id)
        if definition is None:
            return f"{name} is not available to this character"
        if int(definition.current) < resource_cost.amount:
            return (
                f"not enough {name}: this capability needs {resource_cost.amount}, "
                f"the character has {int(definition.current)}"
            )
    action = capability.cost.action
    if action and context.remaining(action) < 1:
        return f"the {action.replace('_', ' ')} has already been spent"
    return ""


def combat_capabilities(
    catalog: Dnd2024ClassFeatureCatalog,
    owned: tuple[ClassFeatureDefinition, ...],
    context: CombatContext,
    definitions: Mapping[str, ResourceDefinition],
    *,
    include_unavailable: bool = False,
) -> tuple[CombatCapabilityView, ...]:
    """Project the capabilities the character may declare right now.

    Only capabilities the character actually owns are considered; a capability
    whose action or resource cost cannot be paid is returned with a reason when
    ``include_unavailable`` is set, and omitted otherwise.  The combat layer
    therefore never has to re-derive class level, feature ownership, or
    resource maxima.
    """

    result: list[CombatCapabilityView] = []
    for definition in owned:
        for capability in definition.capabilities:
            blocked = _blocked_reason(catalog, capability, context, definitions)
            if blocked and not include_unavailable:
                continue
            result.append(CombatCapabilityView(
                id=capability.id,
                feature_id=definition.id,
                name=catalog.label(capability.id, capability.id),
                available=not blocked,
                blocked_reason=blocked,
                requires_hostile_target=capability.requires_hostile_target,
                costs=_cost_views(catalog, capability, context, definitions),
            ))
    return tuple(result)


def unarmed_strike_profile(
    base: Mapping[str, Any], *, martial_arts_die: str,
) -> dict[str, Any]:
    """Return the actor-specific effective profile of the canonical Unarmed Strike.

    The canonical identity, damage type, and reach still come from the combat
    catalog; only the base damage is replaced by the feature-derived Martial
    Arts die.  No new attack identity is ever created here.
    """

    profile = deepcopy(dict(base))
    if martial_arts_die:
        profile["damage"] = martial_arts_die
        profile["martial_arts"] = True
    return profile
