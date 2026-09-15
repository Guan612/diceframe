"""Generated-image application services with explicit dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from src.imagegen import (
    ImageGenerationError,
    ImageGenerationRequest,
    ImageGenerationResult,
    game_image_owner_id,
    infer_scene_panels,
    normalize_scene_panels,
    public_character_appearances,
    storyboard_layout,
)
from src.imagegen.contracts import ImageReference


class ImageAssetBackend(Protocol):
    def file(self, asset_id: str) -> Path | None: ...

    def list_records(self, **filters: str) -> list[dict[str, Any]]: ...


class ImageGenerationBackend(Protocol):
    assets: ImageAssetBackend

    def public_config(self) -> dict[str, Any]: ...

    async def generate(
        self, request: ImageGenerationRequest,
    ) -> ImageGenerationResult: ...


@dataclass(frozen=True)
class GeneratedImageDependencies:
    imagegen: ImageGenerationBackend | None
    get_instance: Callable[[str], Any | None]
    update_map_background: Callable[
        [str, dict[str, str]], Awaitable[dict[str, Any]]
    ]
    save_instance: Callable[[Any], Awaitable[None]] | None = None
    avatar_file: Callable[[str], Path | None] | None = None
    llm_client: Any | None = None


class GeneratedImageService:
    """Generate and authorize image assets without using WebAPI as a locator."""

    def __init__(self, dependencies: GeneratedImageDependencies) -> None:
        self._dependencies = dependencies

    def public_config(self) -> dict[str, Any]:
        backend = self._dependencies.imagegen
        if backend is not None:
            return backend.public_config()
        return {
            "enabled": False,
            "available": False,
            "provider": "",
            "model": "",
            "auto_scene": False,
        }

    def image_file(self, asset_id: str) -> Path | None:
        backend = self._dependencies.imagegen
        return backend.assets.file(asset_id) if backend is not None else None

    async def generate_image(
        self,
        *,
        prompt: str,
        purpose: str,
        owner_type: str,
        owner_id: str,
        aspect_ratio: str = "",
        style: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        backend = self._dependencies.imagegen
        if backend is None:
            raise ImageGenerationError("系统图像生成尚未配置或启用")
        result = await backend.generate(ImageGenerationRequest(
            prompt=prompt,
            purpose=purpose,
            owner_type=owner_type,
            owner_id=owner_id,
            aspect_ratio=aspect_ratio,
            style=style,
            context=dict(context or {}),
        ))
        return {
            "ok": True,
            **result.public_dict(),
            "reference": {"kind": "generated", "asset_id": result.asset_id},
        }

    def list_game_images(
        self,
        game_key: str,
        user_id: str,
        *,
        purpose: str = "",
    ) -> list[dict[str, Any]]:
        instance = self._dependencies.get_instance(game_key)
        if instance is None:
            raise KeyError("游戏不存在")
        if not user_id or (
            user_id != instance.gm_uid and user_id not in instance.players
        ):
            raise PermissionError("当前身份不属于本局游戏")
        backend = self._dependencies.imagegen
        if backend is None:
            return []
        records = backend.assets.list_records(
            owner_type="game",
            owner_id=game_image_owner_id(instance.game_key),
            purpose=purpose,
        )
        for record in records:
            context = (
                record.get("context")
                if isinstance(record.get("context"), dict)
                else {}
            )
            if context.get("round") is not None:
                record["round"] = int(context.get("round") or 0)
        return records

    async def use_as_map_background(
        self,
        game_key: str,
        user_id: str,
        asset_id: str,
    ) -> dict[str, Any]:
        instance = self._dependencies.get_instance(game_key)
        if instance is None:
            return {"ok": False, "error": "游戏不存在"}
        if not user_id or user_id != instance.gm_uid:
            return {"ok": False, "error": "仅 GM 可修改地图背景"}
        if self.image_file(asset_id) is None:
            return {"ok": False, "error": "生成图片不存在"}
        return await self._dependencies.update_map_background(
            game_key,
            {"kind": "generated", "asset_id": asset_id},
        )

    async def generate_current_round(
        self, game_key: str, user_id: str, prompt: str, round_number: int,
        panels: Any = None, use_avatar_references: bool = False,
    ) -> dict[str, Any]:
        instance = self._dependencies.get_instance(game_key)
        if instance is None:
            return {"ok": False, "error": "游戏不存在"}
        if not user_id or user_id != instance.gm_uid:
            return {"ok": False, "error": "仅 GM 可生成当前轮场景图"}
        try:
            requested_round = int(round_number) if round_number is not None else int(getattr(instance, "round_number", 0) or 0)
        except (TypeError, ValueError):
            requested_round = int(getattr(instance, "round_number", 0) or 0)
        prompt = str(prompt or "").strip()
        if not prompt:
            return {"ok": False, "error": "请填写画面描述"}
        backend = self._dependencies.imagegen
        if backend is None:
            return {"ok": False, "error": "系统图像生成尚未配置或启用"}
        if not bool(getattr(backend, "manual_scene", True)):
            return {"ok": False, "error": "手动场景图功能尚未启用"}
        entries = [item for item in reversed(instance.log) if str(item.get("gm_response") or "").strip()]
        entry = next((item for item in entries if int(item.get("round") or 0) == requested_round), entries[0] if entries else None)
        if entry is None:
            return {"ok": False, "error": "当前游戏还没有可附加的 GM 叙事记录"}
        target_round = int(entry.get("round") or 0)
        expected_run_id = str(getattr(instance, "run_id", "") or "")
        requested_panels, _ = normalize_scene_panels(panels)
        declared_panels = requested_panels or entry.get("scene_panels") or []
        normalized_panels, compressed_count = await infer_scene_panels(
            self._dependencies.llm_client,
            narration=str(entry.get("gm_response") or ""),
            actions=entry.get("actions") or [],
            current_scene=str(getattr(instance, "scene", "") or ""),
            players=getattr(instance, "players", {}),
            global_prompt=prompt,
            declared_panels=declared_panels,
        )
        appearances = public_character_appearances(getattr(instance, "players", {}))
        context: dict[str, Any] = {"round": target_round, "requested_round": requested_round, "run_id": expected_run_id, "target": "current-round", "manual": True, "scene": str(getattr(instance, "scene", "") or ""), "narration": str(entry.get("gm_response") or "")[:1600], "actions": str(entry.get("actions") or "")[:1200], "panels": normalized_panels}
        if normalized_panels:
            context["storyboard"] = {"panels": normalized_panels, "compressed_count": compressed_count}
            if appearances:
                context["storyboard"]["character_appearances"] = dict(appearances)
        refs: tuple[ImageReference, ...] = ()
        if use_avatar_references:
            refs = self._avatar_references(instance, normalized_panels)
            if not refs:
                return {"ok": False, "error": "当前分镜没有可用的上传头像，请先为参与角色上传头像"}
        try:
            result = await backend.generate(ImageGenerationRequest(
                prompt=prompt, purpose="scene", owner_type="game", owner_id=game_image_owner_id(instance.game_key),
                aspect_ratio="16:9", context=context, reference_images=refs,
            ))
        except ImageGenerationError as exc:
            return {"ok": False, "error": str(exc)}
        current = self._dependencies.get_instance(game_key)
        if current is None or str(getattr(current, "run_id", "") or "") != expected_run_id:
            return {"ok": False, "error": "本局已重开或重置，生成图片未写入新存档"}
        entry = next((item for item in reversed(current.log) if int(item.get("round") or 0) == target_round and str(item.get("gm_response") or "").strip()), None)
        if entry is None:
            return {"ok": False, "error": "目标 GM 叙事已被回滚，生成图片未写入存档"}
        reference = {"kind": "generated", "asset_id": result.asset_id}
        old_entry = deepcopy(entry.get("scene_image")); old_top = deepcopy(current.scene_image)
        entry["scene_image"] = {"reference": reference, "generation_id": result.generation_id, "prompt": prompt, "revised_prompt": result.revised_prompt, "status": "ready", "swipe_index": int(entry.get("current_swipe") or 0)}
        if refs:
            entry["scene_image"].update({"reference_character_ids": list(context.get("reference_character_ids", [])), "reference_count": int(context.get("reference_count") or 0)})
        if normalized_panels:
            entry["scene_image"].update({"layout": storyboard_layout(len(normalized_panels)), "panels": normalized_panels, "compressed_count": compressed_count})
        current.set_scene_image(reference)
        try:
            if self._dependencies.save_instance is None:
                raise RuntimeError("save callback unavailable")
            await self._dependencies.save_instance(current)
        except Exception:
            if old_entry is None: entry.pop("scene_image", None)
            else: entry["scene_image"] = old_entry
            current.scene_image = old_top
            return {"ok": False, "error": "图片生成成功，但存档保存失败，未写入图片引用"}
        return {"ok": True, **result.public_dict(), "reference": reference, "requested_round": requested_round, "target_round": target_round, **({"reference_character_ids": context.get("reference_character_ids", []), "reference_count": int(context.get("reference_count") or 0)} if refs else {}), **({"layout": storyboard_layout(len(normalized_panels)), "panels": normalized_panels, "compressed_count": compressed_count} if normalized_panels else {})}

    def _avatar_references(self, instance: Any, panels: list[dict[str, Any]]) -> tuple[ImageReference, ...]:
        avatar_file = self._dependencies.avatar_file
        players = getattr(instance, "players", {})
        if not callable(avatar_file) or not isinstance(players, dict):
            return ()
        references: list[ImageReference] = []
        seen_assets: set[str] = set()
        for panel in panels:
            participants = panel.get("participants") if isinstance(panel, dict) else []
            if not isinstance(participants, list):
                continue
            for uid_value in participants:
                uid = str(uid_value or "").strip()
                if not uid or uid not in players:
                    continue
                player = players.get(uid)
                if not isinstance(player, dict):
                    continue
                sheet = player.get("character_sheet") if isinstance(player.get("character_sheet"), dict) else player
                portrait = sheet.get("portrait")
                if not isinstance(portrait, dict) or str(portrait.get("kind") or "") != "upload":
                    continue
                asset_id = str(portrait.get("asset_id") or "").strip()
                if not asset_id or asset_id in seen_assets:
                    continue
                path = avatar_file(asset_id)
                if path is None or not path.is_file():
                    continue
                try: content = path.read_bytes()
                except OSError: continue
                if not content: continue
                seen_assets.add(asset_id)
                references.append(ImageReference(character_id=uid, content=content, content_type="image/webp", file_name=f"{uid[:48] or 'character'}.webp"))
        return tuple(references)
