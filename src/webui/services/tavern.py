"""酒馆角色卡导入服务。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.engine.character_utils import parse_tavern_card

logger = logging.getLogger("trpg")
GameKey = tuple[str, ...]


@dataclass(frozen=True)
class TavernImportDependencies:
    lorebook: Any | None
    get_instance: Callable[[GameKey], Any | None]
    parse_game_key: Callable[[str], GameKey]
    rebuild_lorebook_index: Callable[[str], None]


async def import_tavern_card(dependencies: TavernImportDependencies, file_path: str = "", file_data: str = "",
                             file_name: str = "card.png", game_key: str = "") -> dict[str, Any]:
    """导入酒馆角色卡为 NPC 或玩家角色。

    支持两种模式：
    - file_path: 服务器上的文件路径
    - file_data + file_name: 客户端上传的 base64 数据
    """
    import base64
    import tempfile

    if file_data:
        if len(file_data) > 40_000_000:
            return {"ok": False, "error": "文件过大（上限 30MB）"}
        raw_bytes = base64.b64decode(file_data)
        safe_name = Path(file_name).name or "card.png"
        tmp_path = Path(tempfile.gettempdir()) / f"trpg_import_{safe_name}"
        tmp_path.write_bytes(raw_bytes)
        card = parse_tavern_card(str(tmp_path))
        try:
            tmp_path.unlink()
        except OSError:
            pass
    elif file_path:
        return {"ok": False, "error": "已禁用 file_path 模式（安全风险），请改用 file_data 上传"}
    else:
        return {"ok": False, "error": "未提供文件"}

    if "error" in card:
        return {"ok": False, "error": card["error"]}

    npc_info = {
        "name": card["name"],
        "type": "npc",
        "keywords": [card["name"]] + card.get("tags", []),
        "content": (
            f"描述: {card['description']}\n"
            f"性格: {card['personality']}\n"
            f"背景: {card['scenario']}\n"
            f"初次见面: {card['first_mes']}"
        ).strip(),
        "tier": "core",
    }

    lorebook = dependencies.lorebook
    if game_key and lorebook:
        inst = dependencies.get_instance(dependencies.parse_game_key(game_key))
        if inst and inst.world_id:
            entry_id = f"npc_tavern_{card['name'].replace(' ', '_')}"
            existing = lorebook.get_entry(entry_id)
            npc_info["id"] = entry_id
            npc_info["world_id"] = inst.world_id
            if existing:
                lorebook.update_entry(entry_id, npc_info)
            else:
                lorebook.add_entry(npc_info)
            dependencies.rebuild_lorebook_index(inst.world_id)
            logger.info("酒馆角色卡已导入: %s -> world=%s", card["name"], inst.world_id)

    if card.get("character_book"):
        book_entries = card["character_book"]
        npc_info["lorebook_entries"] = len(book_entries)

    return {"ok": True, "card": card, "npc": npc_info}


class TavernImportService:
    """Tavern-card import with explicit game and lorebook boundaries."""

    def __init__(self, dependencies: TavernImportDependencies) -> None:
        self._dependencies = dependencies

    async def import_card(
        self,
        file_path: str = "",
        file_data: str = "",
        file_name: str = "card.png",
        game_key: str = "",
    ) -> dict[str, Any]:
        return await import_tavern_card(
            self._dependencies, file_path, file_data, file_name, game_key,
        )
