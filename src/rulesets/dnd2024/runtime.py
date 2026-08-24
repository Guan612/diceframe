"""Top-level first-party D&D 2024 runtime boundary."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from src.rulesets.bundle import LoadedRulesetBundle, RulesetBundleLoader
from src.rulesets.contracts import RulesetCapabilities
from src.rulesets.dnd2024.adventure import NarrativeAdventureMixin
from src.rulesets.dnd2024.character.builder import Dnd2024CharacterBuilder
from src.rulesets.dnd2024.campaign import CAMPAIGN_INTENT_TYPES, Dnd2024CampaignEngine
from src.rulesets.dnd2024.combat import Dnd2024CombatEngine
from src.rulesets.dnd2024.progression import (
    Dnd2024AdvancementEngine,
    Dnd2024ProgressionCatalog,
    ProgressionCatalogError,
)
from src.rulesets.dnd2024.resting import Dnd2024RestEngine
from src.rulesets.dnd2024.spells import Dnd2024SpellSelection, SpellCatalogError


class Dnd2024Runtime(NarrativeAdventureMixin):
    runtime_id = "core:dnd2024"
    runtime_version = 1
    capabilities = RulesetCapabilities(
        experience_profile="dnd2024",
        character_builder="professional",
        character_lifecycle="rules_aware",
        authoritative_intents=True,
        deterministic_combat=True,
        versioned_state=True,
        session_zero=True,
        tutorial_coach=True,
        narrative_adventure=True,
    )

    def __init__(self, bundles_dir: str | Path | None = None):
        default = Path(__file__).resolve().parents[3] / "templates" / "rulesets"
        self._loader = RulesetBundleLoader(bundles_dir or default)
        self._bundle_cache: dict[str, LoadedRulesetBundle] = {}

    def load_bundle(self, locale: str = "") -> LoadedRulesetBundle:
        cache_key = str(locale or "").replace("_", "-")
        cached = self._bundle_cache.get(cache_key)
        if cached is not None:
            return cached
        bundle = self._loader.load("dnd2024_srd", locale)
        if bundle.manifest.runtime_id != self.runtime_id:
            raise ValueError(
                f"bundle runtime {bundle.manifest.runtime_id} does not match {self.runtime_id}"
            )
        self._bundle_cache[cache_key] = bundle
        return bundle

    def _builder(self, draft: dict[str, Any]) -> Dnd2024CharacterBuilder:
        return Dnd2024CharacterBuilder(self.load_bundle(str(draft.get("locale") or "")))

    @staticmethod
    def _class_uses_spells(bundle: LoadedRulesetBundle, class_ref: str) -> bool:
        class_entity = bundle.get("class", class_ref.removeprefix("class:")) or {}
        return bool(class_entity.get("spellcasting_ability"))

    def _configure_class_spells(
        self, bundle: LoadedRulesetBundle, character: dict[str, Any], choices: Any,
    ) -> dict[str, Any]:
        class_levels = character.get("build", {}).get("class_levels") or []
        class_ref = str(class_levels[0].get("class_ref") or "") if class_levels else ""
        if not self._class_uses_spells(bundle, class_ref):
            return character
        return Dnd2024SpellSelection(bundle).configure(character, choices)

    @staticmethod
    def _sync_class_resources(
        bundle: LoadedRulesetBundle, character: dict[str, Any],
    ) -> dict[str, Any]:
        if (
            bundle.get("progression_catalog", "srd_classes") is None
            or bundle.get("rest_catalog", "srd_recovery") is None
        ):
            return character
        return Dnd2024RestEngine(bundle).sync_resources(character)

    def describe_experience(self, rule: Any, locale: str) -> dict[str, Any]:
        del rule
        bundle = self.load_bundle(locale)
        return {
            "profile": "dnd2024",
            "builder_mode": "professional",
            "modes": ["quick", "guided", "expert"],
            "content_version": bundle.manifest.content_version,
            "locale": bundle.locale,
        }

    def builder_choices(self, rule: Any, draft: dict[str, Any]) -> dict[str, Any]:
        del rule
        choices = self._builder(draft).choices(draft)
        class_ref = str(draft.get("class_ref") or "")
        if class_ref:
            try:
                choices["class_spells"] = Dnd2024SpellSelection(
                    self.load_bundle(str(draft.get("locale") or ""))
                ).options(class_ref, 1)
            except (ProgressionCatalogError, SpellCatalogError):
                choices["class_spells"] = {}
        else:
            choices["class_spells"] = {}
        return choices

    def validate_character(self, rule: Any, draft: dict[str, Any]) -> list[str]:
        del rule
        errors = self._builder(draft).validate(draft)
        if errors:
            return errors
        class_ref = str(draft.get("class_ref") or "")
        bundle = self.load_bundle(str(draft.get("locale") or ""))
        if not self._class_uses_spells(bundle, class_ref):
            return errors
        _parsed, spell_errors = Dnd2024SpellSelection(
            bundle
        ).validate(class_ref, 1, draft.get("class_spell_choices"))
        return [*errors, *spell_errors]

    def derive_character(self, rule: Any, draft: dict[str, Any]) -> dict[str, Any]:
        del rule
        errors = self.validate_character(None, draft)
        if errors:
            raise ValueError("; ".join(errors))
        bundle = self.load_bundle(str(draft.get("locale") or ""))
        character = Dnd2024CharacterBuilder(bundle).derive(draft)
        character = self._configure_class_spells(
            bundle, character, draft.get("class_spell_choices")
        )
        return self._sync_class_resources(bundle, character)

    def finalize_character(self, rule: Any, draft: dict[str, Any]) -> dict[str, Any]:
        del rule
        canonical = self.derive_character(None, draft)
        return {
            **self._builder(draft).project_legacy(canonical),
            "rule_binding": deepcopy(canonical["rule_binding"]),
            "ruleset_character": canonical,
        }

    def normalize_character_submission(
        self, rule: Any, character: dict[str, Any], locale: str = "",
    ) -> dict[str, Any]:
        del rule
        canonical = character.get("ruleset_character")
        canonical_locale = (
            str(canonical.get("locale") or "") if isinstance(canonical, dict) else ""
        )
        bundle = self.load_bundle(canonical_locale or locale)
        builder = Dnd2024CharacterBuilder(bundle)
        if not isinstance(canonical, dict):
            return builder.normalize_submission(character)
        build = canonical.get("build")
        raw_level = build.get("level", 1) if isinstance(build, dict) else 1
        if isinstance(raw_level, bool):
            raise ValueError("professional character level is invalid")
        try:
            level = int(raw_level)
        except (TypeError, ValueError) as exc:
            raise ValueError("professional character level is invalid") from exc
        if level <= 1:
            rebuilt = builder.normalize_submission(character)["ruleset_character"]
            spell_choices = build.get("class_spell_choices") if isinstance(build, dict) else None
            try:
                rebuilt = self._configure_class_spells(bundle, rebuilt, spell_choices)
                rebuilt = self._sync_class_resources(bundle, rebuilt)
            except SpellCatalogError as exc:
                raise ValueError(f"professional character spell choices are invalid: {exc}") from exc
            return {
                **builder.project_legacy(rebuilt),
                "rule_binding": deepcopy(rebuilt["rule_binding"]),
                "ruleset_character": rebuilt,
            }

        progression = canonical.get("progression")
        history = progression.get("history") if isinstance(progression, dict) else None
        if not isinstance(history, list) or len(history) != level - 1:
            raise ValueError("professional character advancement history is incomplete")
        creation_submission = deepcopy(character)
        creation_canonical = creation_submission["ruleset_character"]
        creation_build = creation_canonical.get("build")
        class_levels = creation_build.get("class_levels") if isinstance(creation_build, dict) else None
        if not isinstance(class_levels, list) or len(class_levels) != 1:
            raise ValueError("professional character must contain one class choice")
        creation_build["level"] = 1
        class_levels[0]["level"] = 1
        creation_canonical.pop("progression", None)
        rebuilt = builder.normalize_submission(creation_submission)["ruleset_character"]
        try:
            rebuilt = self._configure_class_spells(
                bundle, rebuilt, creation_build.get("class_spell_choices"),
            )
        except SpellCatalogError as exc:
            raise ValueError(f"professional character spell choices are invalid: {exc}") from exc
        engine = Dnd2024AdvancementEngine(bundle)
        for expected_level, entry in enumerate(history, start=2):
            if not isinstance(entry, dict) or entry.get("to_level") != expected_level:
                raise ValueError("professional character advancement history is not sequential")
            choices = entry.get("choices")
            if not isinstance(choices, dict):
                raise ValueError("professional character advancement choices are invalid")
            try:
                rebuilt = engine.apply_next_level(rebuilt, choices)
            except ProgressionCatalogError as exc:
                raise ValueError(f"professional character advancement is invalid: {exc}") from exc
        rebuilt = self._sync_class_resources(bundle, rebuilt)
        projected = builder.project_legacy(rebuilt)
        return {
            **projected,
            "rule_binding": deepcopy(rebuilt["rule_binding"]),
            "ruleset_character": rebuilt,
        }

    def progression_table(
        self, rule: Any, class_ref: str, start_level: int = 1, end_level: int = 20,
        locale: str = "",
    ) -> list[dict[str, Any]]:
        del rule
        return Dnd2024ProgressionCatalog.from_bundle(
            self.load_bundle(locale)
        ).range(class_ref, start_level, end_level)

    def preview_advancement(
        self, rule: Any, character: dict[str, Any], choices: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del rule
        canonical = character.get("ruleset_character")
        locale = str(canonical.get("locale") or "") if isinstance(canonical, dict) else ""
        return Dnd2024AdvancementEngine(self.load_bundle(locale)).preview_next_level(
            character, choices
        )

    def apply_advancement(
        self, rule: Any, character: dict[str, Any], choices: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del rule
        canonical = character.get("ruleset_character")
        locale = str(canonical.get("locale") or "") if isinstance(canonical, dict) else ""
        bundle = self.load_bundle(locale)
        advanced = Dnd2024AdvancementEngine(bundle).apply_next_level(character, choices)
        advanced = self._sync_class_resources(bundle, advanced)
        builder = Dnd2024CharacterBuilder(bundle)
        return {
            **builder.project_legacy(advanced),
            "rule_binding": deepcopy(advanced["rule_binding"]),
            "ruleset_character": advanced,
        }

    def complete_rest(
        self, rule: Any, character: dict[str, Any], rest: str,
        hit_die_rolls: dict[str, list[int]] | None = None,
    ) -> dict[str, Any]:
        del rule
        canonical = character.get("ruleset_character")
        locale = str(canonical.get("locale") or "") if isinstance(canonical, dict) else ""
        bundle = self.load_bundle(locale)
        engine = Dnd2024RestEngine(bundle)
        if rest == "short":
            result = engine.complete_short_rest(character, hit_die_rolls)
        elif rest == "long":
            if hit_die_rolls:
                raise ValueError("hit_die_rolls are only valid for a short rest")
            result = engine.complete_long_rest(character)
        else:
            raise ValueError("rest must be short or long")
        rebuilt = result["character"]
        builder = Dnd2024CharacterBuilder(bundle)
        result["character"] = {
            **builder.project_legacy(rebuilt),
            "rule_binding": deepcopy(rebuilt["rule_binding"]),
            "ruleset_character": rebuilt,
        }
        return result

    @staticmethod
    def validate_rest_context(instance: Any, actor_id: str, rest: str) -> None:
        del actor_id, rest
        state = getattr(instance, "ruleset_state", {})
        combat = state.get("combat") if isinstance(state, dict) else None
        if isinstance(combat, dict) and combat.get("active"):
            raise ValueError("战斗进行中不能休息；请先在“权威战斗”中结束战斗")

    def available_intents(self, instance: Any, actor_id: str) -> list[dict[str, Any]]:
        locale = str(getattr(instance, "language", "") or "")
        bundle = self.load_bundle(locale)
        return [
            *Dnd2024CampaignEngine(bundle).available_intents(instance, actor_id),
            *Dnd2024CombatEngine(bundle).available_intents(instance, actor_id),
        ]

    def prepare_intent_submission(
        self, intent: dict[str, Any], requester_id: str, requester_is_gm: bool,
    ) -> dict[str, Any]:
        prepared = deepcopy(intent)
        intent_type = str(prepared.get("type") or "")
        if intent_type in {"combat.start", "combat.end", "decision.resolve"}:
            prepared.pop("actor_id", None)
        elif not requester_is_gm:
            prepared["actor_id"] = f"player:{requester_id}"
        return prepared

    @staticmethod
    def memory_deltas_from_event_batch(
        batch: dict[str, Any], instance: Any,
    ) -> list[dict[str, Any]]:
        del instance
        return [
            deepcopy(event["memory"])
            for event in batch.get("events", [])
            if (
                isinstance(event, dict)
                and event.get("type") == "dnd2024.chapter.summarized"
                and isinstance(event.get("memory"), dict)
            )
        ]

    def validate_intent(self, instance: Any, intent: dict[str, Any]) -> dict[str, Any]:
        locale = str(getattr(instance, "language", "") or "")
        bundle = self.load_bundle(locale)
        if str(intent.get("type") or "") in CAMPAIGN_INTENT_TYPES:
            return Dnd2024CampaignEngine(bundle).validate_intent(instance, intent)
        return Dnd2024CombatEngine(bundle).validate_intent(instance, intent)

    def resolve_intent(self, instance: Any, intent: dict[str, Any], rng: Any) -> dict[str, Any]:
        locale = str(getattr(instance, "language", "") or "")
        bundle = self.load_bundle(locale)
        if str(intent.get("type") or "") in CAMPAIGN_INTENT_TYPES:
            return Dnd2024CampaignEngine(bundle).resolve_intent(instance, intent, rng)
        return Dnd2024CombatEngine(bundle).resolve_intent(instance, intent, rng)

    def apply_event_batch(
        self, instance: Any, batch: dict[str, Any],
    ) -> dict[str, Any]:
        locale = str(getattr(instance, "language", "") or "")
        bundle = self.load_bundle(locale)
        before_characters = {
            uid: deepcopy(instance.get_character_sheet(uid).get("ruleset_character"))
            for uid in getattr(instance, "players", {})
        }
        if str(batch.get("intent_type") or "") in CAMPAIGN_INTENT_TYPES:
            result = Dnd2024CampaignEngine(bundle).apply_batch(instance, batch)
        else:
            result = Dnd2024CombatEngine(bundle).apply_batch(instance, batch)
        revisions: dict[str, int] = {}
        if result.get("applied"):
            for uid in getattr(instance, "players", {}):
                sheet = deepcopy(instance.get_character_sheet(uid))
                canonical = sheet.get("ruleset_character")
                if not isinstance(canonical, dict) or canonical == before_characters.get(uid):
                    continue
                revision = int(sheet.get("ruleset_revision", 0) or 0) + 1
                raw_log = sheet.get("ruleset_operation_log")
                operation_log = deepcopy(raw_log) if isinstance(raw_log, list) else []
                operation_log.append({
                    "operation_id": str(batch.get("batch_id") or ""),
                    "kind": "event_batch",
                    "intent_type": str(batch.get("intent_type") or ""),
                    "revision": revision,
                })
                sheet["ruleset_revision"] = revision
                sheet["ruleset_operation_log"] = operation_log[-32:]
                instance.set_character_sheet(uid, sheet)
                revisions[str(uid)] = revision
        result["character_revisions"] = revisions
        return result

    def gameplay_view(
        self, instance: Any, viewer_id: str = "", viewer_is_gm: bool = False,
    ) -> dict[str, Any]:
        locale = str(getattr(instance, "language", "") or "")
        bundle = self.load_bundle(locale)
        view = Dnd2024CombatEngine(bundle).gameplay_view(instance)
        view["campaign"] = Dnd2024CampaignEngine(bundle).gameplay_view(
            instance, viewer_id, viewer_is_gm,
        )
        return view

    def build_llm_view(self, instance: Any) -> dict[str, Any]:
        state = dict(instance.to_llm_view())
        for uid, player in state.get("players", {}).items():
            source = instance.get_character_sheet(uid)
            canonical = source.get("ruleset_character")
            if not isinstance(canonical, dict):
                continue
            sheet = player.get("character_sheet")
            if not isinstance(sheet, dict):
                continue
            resources = canonical.get("resources") or {}
            sheet["hp"] = int(resources.get("hp", 0) or 0)
            sheet["max_hp"] = int(resources.get("max_hp", 0) or 0)
            sheet["conditions"] = deepcopy(canonical.get("conditions") or {})
            sheet["spellcasting"] = deepcopy(canonical.get("spellcasting") or {})
            sheet["derived"] = deepcopy(canonical.get("derived") or {})
        gameplay = self.gameplay_view(
            instance, str(getattr(instance, "gm_uid", "") or ""), True,
        )
        state["ruleset_authority"] = {
            "runtime_id": self.runtime_id,
            "state_version": gameplay["state_version"],
            "combat": gameplay["combat"],
            "campaign": gameplay["campaign"],
            "latest_event_batch": (
                deepcopy(instance.event_ledger[-1]) if instance.event_ledger else None
            ),
            "policy": "Narrate resolved events only; never invent or mutate mechanics.",
        }
        state.pop("combat_enemies", None)
        return state

    def project_legacy_character(self, character: dict[str, Any]) -> dict[str, Any]:
        locale = str(character.get("locale") or "")
        return Dnd2024CharacterBuilder(self.load_bundle(locale)).project_legacy(character)

    def migrate_state(self, payload: dict[str, Any], from_version: int) -> dict[str, Any]:
        if from_version != 1:
            raise ValueError(f"unsupported D&D 2024 state schema version: {from_version}")
        return deepcopy(payload)
