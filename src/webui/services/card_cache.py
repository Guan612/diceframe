"""QQ / NapCat 群聊卡片 PNG 缓存清理工具（主程序侧独立实现，不依赖插件代码）。"""

from __future__ import annotations

import time
from pathlib import Path


def cleanup_card_cache(
    out_dir: Path,
    *,
    max_age_hours: float = 24,
    max_files: int = 200,
    delete_all: bool = False,
) -> dict[str, int]:
    """清理 QQ 卡片 PNG 缓存。

    只处理当前卡片目录下的 ``card_*.png``，不递归，不碰用户上传或其他资源。
    ``max_age_hours <= 0`` 表示不按时间清理；``max_files <= 0`` 表示不按数量清理。
    """
    out_dir = Path(out_dir)
    if not out_dir.exists():
        return {"scanned": 0, "deleted": 0, "kept": 0, "bytes_deleted": 0}

    files = [path for path in out_dir.glob("card_*.png") if path.is_file()]
    scanned = len(files)
    deleted = 0
    bytes_deleted = 0
    now = time.time()
    cutoff = now - max_age_hours * 3600 if max_age_hours > 0 else None
    by_mtime_desc = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    keep_by_count = set(by_mtime_desc[:max_files]) if max_files > 0 else set(files)

    for path in files:
        should_delete = delete_all
        if not should_delete and cutoff is not None:
            try:
                should_delete = path.stat().st_mtime < cutoff
            except FileNotFoundError:
                continue
        if not should_delete and max_files > 0:
            should_delete = path not in keep_by_count
        if not should_delete:
            continue
        try:
            size = path.stat().st_size
            path.unlink()
            deleted += 1
            bytes_deleted += size
        except FileNotFoundError:
            continue

    return {
        "scanned": scanned,
        "deleted": deleted,
        "kept": max(0, scanned - deleted),
        "bytes_deleted": bytes_deleted,
    }
