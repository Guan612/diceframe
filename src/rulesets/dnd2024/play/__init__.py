"""Explicit campaign-to-combat integration boundary for D&D 2024."""

from .contracts import (
    EncounterAccess,
    resolve_story_encounter_access,
    story_encounter_instance_id,
)

__all__ = [
    "EncounterAccess",
    "resolve_story_encounter_access",
    "story_encounter_instance_id",
]
