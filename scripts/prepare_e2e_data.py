"""Create the deterministic save used by clean-data browser tests."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.engine.game_instance import GameInstance, GameState
from src.rulesets.dnd2024.runtime import Dnd2024Runtime
from src.webui.services.legal import bundled_documents


E2E_GAME_KEY = ("web", "e2e-room", "web_bot")
E2E_DND_GAME_KEY = ("web", "e2e-dnd2024", "web_bot")


def _write_save(data_dir: Path, instance: GameInstance) -> Path:
    save_file = data_dir / "saves" / "#".join(instance.game_key) / "state.json"
    save_file.parent.mkdir(parents=True, exist_ok=True)
    save_file.write_text(
        json.dumps(instance.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return save_file


def prepare_e2e_data(data_dir: Path) -> Path:
    data_dir = data_dir.resolve()
    documents = bundled_documents()
    config_file = data_dir / "config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        json.dumps(
            {
                "ai_providers": [{
                    "id": "e2e-provider",
                    "name": "E2E Provider",
                    "base_url": "http://127.0.0.1:9/v1",
                    "api_format": "openai",
                    "models": ["e2e-chat", "e2e-embedding"],
                }],
                "llm_provider_ref": "e2e-provider",
                "model": "e2e-chat",
                "hub_telemetry_enabled": False,
                "hub_telemetry_choice_made": True,
                "legal_terms_accepted_updated_at": documents["terms"]["updated_at"],
                "legal_privacy_accepted_updated_at": documents["privacy"]["updated_at"],
                "legal_accepted_at": "2026-08-11T00:00:00+00:00",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (data_dir / "secrets.json").write_text(
        json.dumps(
            {"ai_provider_key_e2e-provider": secrets.token_urlsafe(24)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    instance = GameInstance(
        game_key=E2E_GAME_KEY,
        world_id="default_fantasy",
        world_name="E2E Adventure",
        group_name="Browser Tests",
        state=GameState.ACTIVE_ACTION,
        round_number=2,
        solo_mode=False,
        gm_uid="e2e-gm",
        scene="Town Gate",
    )
    instance.players = {
        "e2e-gm": {
            "character_name": "E2E GM",
            "character_sheet": {
                "character_name": "E2E GM",
                "attributes": {"str": 12, "dex": 10},
                "skills": [],
                "hp": 10,
                "max_hp": 10,
                "portrait": {"kind": "builtin", "id": "warrior"},
                "equipment": [
                    {"name": "Longsword", "type": "weapon", "damage": "1d8", "slot": "main_hand"},
                    {"name": "Shield", "type": "armor", "slot": "off_hand"},
                ],
                "inventory": [{"name": "Healing Potion", "quantity": 2, "effect": "Restore health"}],
                "key_items": [{"name": "Town Gate Seal", "description": "Proof of passage"}],
            },
        },
        "e2e-player": {
            "character_name": "E2E Player",
            "character_sheet": {
                "character_name": "E2E Player",
                "attributes": {"str": 9, "dex": 13},
                "skills": [],
                "hp": 9,
                "max_hp": 9,
                "portrait": {"kind": "builtin", "id": "ranger"},
                "equipment": [{"name": "Shortbow", "type": "weapon", "damage": "1d6"}],
                "inventory": [{"name": "Rope", "quantity": 1}],
                "key_items": [],
            },
        },
    }
    instance.log = [{
        "round": 1,
        "actions": [
            {"user_id": "e2e-gm", "text": "Inspect the gate."},
            {"user_id": "e2e-player", "text": "Watch the road."},
        ],
        "gm_response": "The road is quiet.",
    }]
    save_file = _write_save(data_dir, instance)

    runtime = Dnd2024Runtime()
    choices = runtime.builder_choices(None, {"locale": "zh-CN"})
    preset = next(item for item in choices["quick_presets"] if item["id"] == "stalwart_guardian")
    dnd_character = runtime.finalize_character(
        None, {**preset["draft"], "locale": "zh-CN", "name": "新手守护者"},
    )
    dnd_instance = GameInstance(
        game_key=E2E_DND_GAME_KEY,
        world_id="default_fantasy",
        world_name="D&D 2024 新手桌",
        group_name="Professional Ruleset Browser Tests",
        state=GameState.ACTIVE_ACTION,
        solo_mode=False,
        gm_uid="e2e-gm",
        scene="灰沼村议事厅",
        rule_id="dnd2024_srd",
        language="zh-CN",
    )
    dnd_instance.players = {
        "e2e-gm": {
            "character_name": "新手守护者",
            "character_sheet": dnd_character,
        },
    }
    if not dnd_instance.bind_ruleset_runtime(dnd_character["rule_binding"]):
        raise RuntimeError("failed to bind D&D 2024 runtime in E2E fixture")
    _write_save(data_dir, dnd_instance)
    return save_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=None)
    args = parser.parse_args()
    environment_dir = os.getenv("DICEFRAME_E2E_DATA_DIR")
    raw_data_dir = args.data_dir or (Path(environment_dir) if environment_dir else None)
    if raw_data_dir is None:
        parser.error("--data-dir or DICEFRAME_E2E_DATA_DIR is required")
    print(prepare_e2e_data(raw_data_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
