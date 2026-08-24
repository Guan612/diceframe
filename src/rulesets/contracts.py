"""Pure contracts shared by generic and first-party ruleset runtimes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol, runtime_checkable


CharacterBuilderMode = Literal["legacy", "guided", "professional"]
CharacterLifecycleMode = Literal["legacy", "rules_aware"]


@dataclass(frozen=True, slots=True)
class RulesetCapabilities:
    """Feature switches exposed to API clients without leaking runtime classes."""

    experience_profile: str = "generic"
    character_builder: CharacterBuilderMode = "legacy"
    character_lifecycle: CharacterLifecycleMode = "legacy"
    authoritative_intents: bool = False
    deterministic_combat: bool = False
    versioned_state: bool = False
    session_zero: bool = False
    tutorial_coach: bool = False
    narrative_adventure: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RulesetBinding:
    """A rule template's explicit request for a runtime implementation."""

    runtime_id: str = "core:legacy"
    minimum_version: int = 1


@dataclass(frozen=True, slots=True)
class RulesetRuntimeMetadata:
    """JSON-safe description of the runtime selected for a rule template."""

    runtime_id: str
    runtime_version: int
    requested_minimum_version: int
    capabilities: RulesetCapabilities

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.runtime_id,
            "version": self.runtime_version,
            "requested_minimum_version": self.requested_minimum_version,
            "capabilities": self.capabilities.to_dict(),
        }


@runtime_checkable
class RulesetRuntime(Protocol):
    """Boundary implemented by legacy and professional ruleset runtimes.

    Web-specific request objects and UI component details must never cross this
    contract. Methods intentionally exchange plain, JSON-compatible data.
    """

    runtime_id: str
    runtime_version: int
    capabilities: RulesetCapabilities

    def describe_experience(self, rule: Any, locale: str) -> dict[str, Any]: ...

    def builder_choices(self, rule: Any, draft: dict[str, Any]) -> dict[str, Any]: ...

    def validate_character(self, rule: Any, draft: dict[str, Any]) -> list[str]: ...

    def derive_character(self, rule: Any, draft: dict[str, Any]) -> dict[str, Any]: ...

    def finalize_character(self, rule: Any, draft: dict[str, Any]) -> dict[str, Any]: ...

    def normalize_character_submission(
        self, rule: Any, character: dict[str, Any], locale: str = "",
    ) -> dict[str, Any]: ...

    def available_intents(self, instance: Any, actor_id: str) -> list[dict[str, Any]]: ...

    def validate_intent(self, instance: Any, intent: dict[str, Any]) -> dict[str, Any]: ...

    def resolve_intent(self, instance: Any, intent: dict[str, Any], rng: Any) -> dict[str, Any]: ...

    def apply_event_batch(self, instance: Any, batch: dict[str, Any]) -> dict[str, Any]: ...

    def gameplay_view(
        self, instance: Any, viewer_id: str = "", viewer_is_gm: bool = False,
    ) -> dict[str, Any]: ...

    def build_llm_view(self, instance: Any) -> dict[str, Any]: ...

    def project_legacy_character(self, character: dict[str, Any]) -> dict[str, Any]: ...

    def migrate_state(self, payload: dict[str, Any], from_version: int) -> dict[str, Any]: ...


@runtime_checkable
class AuthoritativeIntentHooks(Protocol):
    """Runtime-owned request and projection hooks for authoritative intents."""

    def prepare_intent_submission(
        self, intent: dict[str, Any], requester_id: str, requester_is_gm: bool,
    ) -> dict[str, Any]: ...

    def memory_deltas_from_event_batch(
        self, batch: dict[str, Any], instance: Any,
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class NarrativeAdventureRuntime(Protocol):
    """Optional out-of-combat free-declaration narration boundary."""

    def prepare_adventure_narration(
        self, instance: Any, actor_id: str, declaration: dict[str, Any], locale: str,
    ) -> dict[str, Any]: ...
