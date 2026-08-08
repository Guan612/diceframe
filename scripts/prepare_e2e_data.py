"""Create the deterministic save used by clean-data browser tests."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.engine.game_instance import GameInstance, GameState


E2E_GAME_KEY = ("web", "e2e-room", "web_bot")


def prepare_e2e_data(data_dir: Path) -> Path:
    data_dir = data_dir.resolve()
    save_file = data_dir / "saves" / "#".join(E2E_GAME_KEY) / "state.json"
    save_file.parent.mkdir(parents=True, exist_ok=True)
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
    save_file.write_text(json.dumps(instance.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
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
