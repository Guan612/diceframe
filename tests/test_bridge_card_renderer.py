from __future__ import annotations

import os
import time

from PIL import Image, ImageDraw

from src.bots.bridge_core import card_renderer
from src.bots.bridge_core.card_renderer import (
    _fit_by_pixel,
    _load_font,
    _text_width,
    _wrap_by_pixel,
    cleanup_card_cache,
)


def test_wrapping_accounts_for_first_line_indent():
    font = _load_font(21)
    image = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(image)
    content_width = 600
    indent_px = _text_width(draw, "　　", font)
    text = "尤洛沿着白马寺藏经阁外墙一路疾行，银针上残留的冷光忽明忽暗，像是在催促她立刻做出决定。"

    lines = _wrap_by_pixel(draw, text, font, content_width, first_line_max_width=content_width - indent_px)

    assert lines
    assert _text_width(draw, lines[0], font) + indent_px <= content_width
    for line in lines[1:]:
        assert _text_width(draw, line, font) <= content_width


def test_fit_by_pixel_adds_ellipsis_within_width(monkeypatch):
    monkeypatch.setattr(card_renderer, "_font_paths", lambda: [])
    font = _load_font(19)
    image = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(image)

    fitted = _fit_by_pixel(draw, "这是一个很长很长很长的卡片副标题", font, 120)

    assert fitted.endswith("…")
    assert _text_width(draw, fitted, font) <= 120


def test_cleanup_card_cache_deletes_old_and_excess_files(tmp_path):
    card_dir = tmp_path / "cards"
    card_dir.mkdir()
    old = card_dir / "card_old.png"
    keep = card_dir / "card_keep.png"
    extra = card_dir / "card_extra.png"
    other = card_dir / "avatar.png"
    for path in (old, keep, extra, other):
        path.write_bytes(b"png")
    now = time.time()
    os.utime(old, (now - 48 * 3600, now - 48 * 3600))
    os.utime(keep, (now, now))
    os.utime(extra, (now - 60, now - 60))

    result = cleanup_card_cache(card_dir, max_age_hours=24, max_files=1)

    assert result["deleted"] == 2
    assert not old.exists()
    assert keep.exists()
    assert not extra.exists()
    assert other.exists()


def test_cleanup_card_cache_delete_all_only_removes_generated_cards(tmp_path):
    card_dir = tmp_path / "cards"
    card_dir.mkdir()
    generated = card_dir / "card_abc.png"
    unrelated = card_dir / "manual.png"
    generated.write_bytes(b"png")
    unrelated.write_bytes(b"do not touch")

    result = cleanup_card_cache(card_dir, delete_all=True)

    assert result["deleted"] == 1
    assert not generated.exists()
    assert unrelated.exists()
