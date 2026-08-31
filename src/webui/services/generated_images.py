"""Generated-image application services with explicit dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from src.imagegen import (
    ImageGenerationError,
    ImageGenerationRequest,
    ImageGenerationResult,
    game_image_owner_id,
)


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
