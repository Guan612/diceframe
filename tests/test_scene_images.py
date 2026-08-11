from __future__ import annotations

import base64
import io

from PIL import Image

from src.webui.services import scene_images


def _image_data(size: tuple[int, int] = (640, 360), fmt: str = "PNG") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, (24, 78, 110)).save(output, format=fmt)
    return output.getvalue()


class _Api:
    def __init__(self, tmp_path):
        self._scene_images_dir = tmp_path / "scene-images"
        self.world = None
        self.rule = None

    def _load_world_template(self, _world_id):
        return self.world

    def get_rule_template(self, _rule_id):
        return {"rule": self.rule} if self.rule else {}

    def plugin_asset_path(self, _plugin_id, _relative_path):
        raise KeyError("not installed")


def test_upload_normalizes_and_deduplicates_scene_image(tmp_path):
    api = _Api(tmp_path)
    encoded = base64.b64encode(_image_data()).decode("ascii")

    first = scene_images.save_scene_image_upload(api, encoded, "cover.png")
    second = scene_images.save_scene_image_upload(api, encoded, "cover-copy.png")

    assert first["ok"] is True
    assert first["scene_image"] == second["scene_image"]
    path = scene_images.scene_image_file(api, first["scene_image"]["asset_id"])
    assert path is not None
    with Image.open(path) as image:
        assert image.size == (1600, 900)
        assert image.format == "WEBP"


def test_default_precedence_is_world_then_rule_then_builtin(tmp_path):
    api = _Api(tmp_path)
    api.rule = {"scene_image": {"kind": "builtin", "id": "freeform_coc"}}
    api.world = {
        "default_rule": "freeform_coc",
        "scene_image": {"kind": "builtin", "id": "freeform_wuxia"},
    }

    assert scene_images.resolve_default_scene_image(api, "world", "dnd5e") == {
        "kind": "builtin", "id": "freeform_wuxia",
    }
    api.world.pop("scene_image")
    assert scene_images.resolve_default_scene_image(api, "world", "dnd5e") == {
        "kind": "builtin", "id": "freeform_coc",
    }
    api.world = None
    api.rule = None
    assert scene_images.resolve_default_scene_image(api, "", "dnd5e") == {
        "kind": "builtin", "id": "dnd5e",
    }


def test_package_scene_image_writes_portable_asset_reference(tmp_path):
    api = _Api(tmp_path)
    upload = scene_images.save_scene_image_upload(
        api, base64.b64encode(_image_data()).decode("ascii")
    )["scene_image"]
    files = {}

    packaged = scene_images.package_scene_image(api, upload, files)

    assert packaged and packaged["kind"] == "asset"
    assert packaged["path"].startswith("assets/scenes/")
    assert packaged["path"] in files
