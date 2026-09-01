"""Generic LLM/presentation projection for a game instance."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.engine.language import normalize_language


CharacterSheetProjector = Callable[[dict[str, Any]], dict[str, Any]]


def _project_generic_character_sheet(character_sheet: dict[str, Any]) -> dict[str, Any]:
    """Copy presentation fields without inventing ruleset mechanics."""
    sheet: dict[str, Any] = {
        "hp": character_sheet.get("hp", 0),
        "max_hp": character_sheet.get("max_hp", 0),
        "class": character_sheet.get("class", ""),
        "race": character_sheet.get("race", ""),
        "level": character_sheet.get("level", 1),
        "xp": character_sheet.get("xp", 0),
        "gold": character_sheet.get("gold", 0),
        "attributes": character_sheet.get("attributes", {}),
        "equipment": character_sheet.get("equipment", []),
        "skills": character_sheet.get("skills", []),
        "inventory": character_sheet.get("inventory", []),
        "key_items": character_sheet.get("key_items", []),
    }
    if character_sheet.get("background"):
        sheet["background"] = character_sheet["background"]
    if character_sheet.get("deceased"):
        sheet["deceased"] = True
    return sheet


class GameContextProjector:
    """Build the compact generic state view consumed by LLM context code."""

    @staticmethod
    def project(
        instance: Any,
        *,
        character_sheet_projector: CharacterSheetProjector | None = None,
    ) -> dict[str, Any]:
        project_sheet = character_sheet_projector or _project_generic_character_sheet
        players_view: dict[str, dict[str, Any]] = {}
        for uid, player_data in instance.players.items():
            character_sheet = player_data.get("character_sheet", {})
            sheet = project_sheet(character_sheet)
            players_view[uid] = {
                "character_name": player_data.get("character_name", ""),
                "attendance": "away" if uid in instance.away_players else "active",
                "character_sheet": sheet,
            }

        away_names = [
            instance.players.get(uid, {}).get("character_name") or uid
            for uid in sorted(instance.away_players)
            if uid in instance.players and instance.is_alive(uid)
        ]
        state: dict[str, Any] = {
            "world_name": instance.world_name,
            "round_number": instance.round_number,
            "scene": instance.scene,
            "game_time": instance.game_time,
            "difficulty": instance.difficulty,
            "language": normalize_language(instance.language),
            "players": players_view,
            "away_players": away_names,
            "npcs": instance.npcs,
            "combat_state": instance.combat_state,
            "combat_enemies": instance.combat_enemies,
            "initiative_order": instance.initiative_order,
            "initiative_current": instance.initiative_current,
            "quick_actions": instance.quick_actions,
        }
        if away_names:
            state["attendance_note"] = (
                "暂离角色默认跟随队伍，不主动做重大决定，不承担关键风险；"
                "除非玩家回来或 GM 明确点名。"
            )
        if instance.combat_state == "active":
            state["combat_active"] = True
        if instance.solo_mode:
            state["solo_mode"] = True
        if instance.puzzle_manager and hasattr(instance.puzzle_manager, "to_active_dict"):
            puzzles = instance.puzzle_manager.to_active_dict()
            if puzzles:
                state["puzzles"] = puzzles
        return state
