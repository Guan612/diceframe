"""Unified migrations for persisted game-instance projections.

Domain adapters stay in ``src.compat``; services call this module instead of
knowing which compatibility steps are needed for a loaded instance.
"""

from __future__ import annotations

import logging
from typing import Any

from src.compat.dnd2024_adventure_bindings import apply_unreleased_adventure_binding_migration


logger = logging.getLogger("trpg")


def _referenced_player_ids(log: list[Any]) -> set[str]:
    referenced: set[str] = set()
    for entry in log or []:
        for action in entry.get("actions", []) or []:
            uid = action.get("user_id")
            if uid and uid != "system":
                referenced.add(uid)
        snapshot = entry.get("pre_state_snapshot", {})
        if isinstance(snapshot, dict):
            referenced.update(uid for uid in snapshot if uid and uid != "system")
    return referenced


def normalize_loaded_instance(instance: Any) -> None:
    """Normalize known legacy persisted shapes after reconstruction.

    Ghost-player cleanup intentionally requires historical evidence. Waiting
    rooms and unplayed multiplayer sessions therefore keep every participant.
    """
    if len(instance.players) <= 1 or not instance.log:
        return
    referenced = _referenced_player_ids(instance.log)
    if not referenced:
        return
    ghost_ids = sorted(uid for uid in instance.players if uid not in referenced)
    if not ghost_ids:
        return
    for uid in ghost_ids:
        instance.players.pop(uid, None)
        instance.ready_players.discard(uid)
        instance.away_players.discard(uid)
    instance.action_queue = [
        action
        for action in instance.action_queue
        if action.get("user_id") not in ghost_ids
    ]
    instance.pending_actions = [
        action
        for action in instance.pending_actions
        if action.get("user_id") not in ghost_ids
    ]
    logger.warning(
        "加载存档时移除幽灵玩家: game_key=%s, players=%s",
        instance.game_key,
        ghost_ids,
    )


def migrate_instance(instance: Any, *, adventure_expected: dict[str, Any] | None = None) -> bool | None:
    """Apply registered instance migrations, failing closed on incompatibility."""
    if adventure_expected is None or not dict(getattr(instance, "adventure_binding", {}) or {}):
        return False
    return apply_unreleased_adventure_binding_migration(instance, adventure_expected)
