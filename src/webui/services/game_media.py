"""World binding and scene media transactions for existing games."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from src.webui.services._common import _is_safe_world_id

GameKey = tuple[str, ...]


@dataclass(frozen=True)
class GameMediaDependencies:
    parse_game_key: Callable[[str], GameKey]
    get_instance: Callable[[GameKey], Any | None]
    save_instance: Callable[[Any], Awaitable[None]]
    load_world_template: Callable[[str], dict[str, Any] | None] | None
    get_lore_world: Callable[[str], dict[str, Any] | None] | None
    refresh_lorebook_index: Callable[[str], None] | None
    resolve_rule_id: Callable[[Any], str]
    resolve_default_scene_image: Callable[[str, str], dict[str, str]]
    materialize_scene_image: Callable[[Any], dict[str, str]]


class GameMediaService:
    """World and scene changes with explicit template, lore, and save boundaries."""

    def __init__(self, dependencies: GameMediaDependencies) -> None:
        self._dependencies = dependencies

    def _instance(self, game_key: str) -> Any | None:
        return self._dependencies.get_instance(
            self._dependencies.parse_game_key(game_key)
        )

    async def switch_world(
        self, game_key: str, world_id: str,
    ) -> dict[str, Any]:
        """Switch the associated world book while retaining characters and progress."""

        instance = self._instance(game_key)
        if not instance:
            return {"ok": False, "error": "游戏不存在"}
        if not _is_safe_world_id(world_id):
            return {"ok": False, "error": "未指定或非法 world_id"}
        binding = dict(getattr(instance, "adventure_binding", {}) or {})
        if binding and str(binding.get("world_id") or "") != world_id:
            return {
                "ok": False,
                "error_code": "ADVENTURE_WORLD_LOCKED",
                "error": "当前存档绑定了固定世界冒险；请新建沙盒对局后再切换世界书。",
            }
        world_name = world_id
        if self._dependencies.load_world_template is not None:
            try:
                world_data = self._dependencies.load_world_template(world_id)
            except Exception as exc:
                return {"ok": False, "error": f"加载世界失败: {exc}"}
            if world_data:
                world_name = world_data.get("world_name", world_id)
            elif self._dependencies.get_lore_world is not None:
                world = self._dependencies.get_lore_world(world_id)
                if not world:
                    return {"ok": False, "error": f"世界 {world_id} 不存在"}
                world_name = world.get("name", world_id)
            else:
                return {"ok": False, "error": f"世界 {world_id} 不存在"}
        instance.set_world(world_id, world_name)
        if self._dependencies.refresh_lorebook_index is not None:
            self._dependencies.refresh_lorebook_index(world_id)
        await self._dependencies.save_instance(instance)
        return {
            "ok": True,
            "world_id": instance.world_id,
            "world_name": instance.world_name,
        }

    async def update_scene_image(
        self,
        game_key: str,
        reference: dict[str, Any] | None = None,
        *,
        use_default: bool = False,
    ) -> dict[str, Any]:
        instance = self._instance(game_key)
        if not instance:
            return {"ok": False, "error": "游戏不存在"}
        try:
            if use_default:
                rule_id = self._dependencies.resolve_rule_id(instance)
                instance.rule_id = rule_id
                selected = self._dependencies.resolve_default_scene_image(
                    str(instance.world_id or ""), rule_id,
                )
            else:
                selected = reference
            if not selected:
                return {
                    "ok": False,
                    "error": "请选择冒险头图或恢复内容默认",
                }
            materialized = self._dependencies.materialize_scene_image(selected)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        instance.set_scene_image(materialized)
        await self._dependencies.save_instance(instance)
        return {"ok": True, "scene_image": materialized}
