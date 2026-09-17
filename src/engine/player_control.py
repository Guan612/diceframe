"""Per-seat player control contract: *who plays* a character, not *who they are*.

A DiceFrame seat (``GameInstance.players[uid]``) already owns the character:
identity, HP, equipment, spell slots, conditions, world position and history all
live there.  What was missing is an explicit answer to "who decides what this
character does right now?" — a human, the server AI, or nobody yet.

This module owns that answer and nothing else:

```text
control.mode = human       a real player is responsible
control.mode = ai          the server produces this character's actions
control.mode = unclaimed   the seat exists but nobody plays it yet
```

Design boundaries:

- **AI is a controller, not a character type.**  There is exactly one character
  record per seat and exactly one combat actor (``player:<uid>``) regardless of
  the mode.  Nothing is copied, moved, or re-keyed when the controller changes.
- **Deterministic only.**  No LLM calls, no network, no threads, no persistence
  side effects, no combat or UI logic.  This module mutates one small record.
- **Single write entry.**  ``set_control`` is the only supported way to change a
  controller; everything else reads through the helpers below.
- **Reads degrade, writes fail closed.**  A corrupted persisted record reads as
  the conservative default (``human``, the pre-contract behaviour) instead of
  inventing an AI controller, while ``set_control`` rejects unknown modes and
  unknown seats outright.
- **Round rollback does not own control.**  The control record sits beside
  ``character_sheet``, and the round/swipe rollback helpers (``_snapshot_players``
  / ``restore_players``) only snapshot and restore character-sheet fields, so
  "AI took over, then the GM rolled the round back" cannot silently re-assign the
  seat.  Control still travels with ordinary save/load.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

# 玩家记录里的控制键；与 ``character_sheet`` 同级，不属于角色状态。
CONTROL_KEY = "control"

# 第一版只允许这三种控制者。gm / remote_bot / script / hybrid / spectator 等
# 不是本轮范围：多一个模式就多一套权限与结算语义。
CONTROL_MODES = ("human", "ai", "unclaimed")

# 旧存档没有任何控制信息，唯一不猜测的答案就是旧版本行为：真人控制。
DEFAULT_CONTROL_MODE = "human"

# temporary=true 表示「真人暂离、AI 临时托管」，恢复目标只能是真人或未认领。
RESUME_MODES = ("human", "unclaimed")

MAX_CONTROL_REVISION = 2**31 - 1


class PlayerControlError(ValueError):
    """An invalid control change: fail closed instead of guessing a controller."""


def default_control() -> dict[str, Any]:
    """The conservative control record of a seat with no stored control."""

    return {
        "mode": DEFAULT_CONTROL_MODE,
        "revision": 0,
        "temporary": False,
        "resume_mode": None,
    }


def normalize_control(raw: Any) -> dict[str, Any]:
    """Return the deterministic control record for one seat.

    Corrupted or unknown input degrades to :func:`default_control` rather than
    inventing an AI controller; only :func:`set_control` rejects input.  The
    result is idempotent, so normalizing a normalized record changes nothing.
    """

    if not isinstance(raw, Mapping):
        return default_control()
    mode = raw.get("mode")
    if mode not in CONTROL_MODES:
        mode = DEFAULT_CONTROL_MODE
    revision = raw.get("revision")
    if (
        isinstance(revision, bool)
        or not isinstance(revision, int)
        or not 0 <= revision <= MAX_CONTROL_REVISION
    ):
        revision = 0
    temporary = bool(raw.get("temporary", False))
    resume_mode = raw.get("resume_mode")
    if resume_mode not in RESUME_MODES:
        resume_mode = None
    # ``temporary`` / ``resume_mode`` 只在「AI 临时托管」时有意义：一个由真人
    # 控制的席位不能同时携带恢复目标，否则读出来就是自相矛盾的状态。
    if mode != "ai" or not temporary:
        temporary = False
        resume_mode = None
    return {
        "mode": str(mode),
        "revision": revision,
        "temporary": temporary,
        "resume_mode": resume_mode,
    }


def get_control(instance: Any, uid: str) -> dict[str, Any]:
    """Read one seat's normalized control record.

    An unknown seat reads as the conservative default instead of raising: reads
    never manufacture an AI controller, and callers asking about a seat that no
    longer exists get "no control evidence" rather than a hard failure.
    """

    player = _player_record(instance, uid)
    if player is None:
        return default_control()
    return normalize_control(player.get(CONTROL_KEY))


def control_mode(instance: Any, uid: str) -> str:
    """The seat's control mode (``human`` / ``ai`` / ``unclaimed``)."""

    return str(get_control(instance, uid)["mode"])


def set_control(
    instance: Any,
    uid: str,
    mode: str,
    *,
    temporary: bool = False,
    resume_mode: str | None = None,
) -> dict[str, Any]:
    """Set one seat's controller.  The only supported write entry point.

    Raises :class:`PlayerControlError` for an unknown seat, an unsupported mode,
    or a temporary AI hosting request without a valid resume target.  ``revision``
    increases only when the stored record actually changes, so a repeated request
    is not mistaken for a control handover.
    """

    player = _player_record(instance, uid)
    if player is None:
        raise PlayerControlError(f"unknown player seat: {uid!r}")
    if mode not in CONTROL_MODES:
        raise PlayerControlError(f"unsupported control mode: {mode!r}")
    if mode == "ai":
        if temporary:
            if resume_mode not in RESUME_MODES:
                raise PlayerControlError(
                    f"temporary AI hosting needs a resume mode: {resume_mode!r}"
                )
        else:
            resume_mode = None
    else:
        temporary = False
        resume_mode = None

    current = normalize_control(player.get(CONTROL_KEY))
    requested = normalize_control({
        "mode": mode,
        "revision": current["revision"],
        "temporary": temporary,
        "resume_mode": resume_mode,
    })
    if requested == current:
        # 没有实际变化：不提升 revision，避免把 no-op 当成一次控制权交接。
        player[CONTROL_KEY] = current
        return dict(current)
    if current["revision"] >= MAX_CONTROL_REVISION:
        raise PlayerControlError("control revision is exhausted")
    requested["revision"] = int(current["revision"]) + 1
    player[CONTROL_KEY] = requested
    return dict(requested)


def is_human_controlled(instance: Any, uid: str) -> bool:
    return control_mode(instance, uid) == "human"


def is_ai_controlled(instance: Any, uid: str) -> bool:
    return control_mode(instance, uid) == "ai"


def is_unclaimed(instance: Any, uid: str) -> bool:
    return control_mode(instance, uid) == "unclaimed"


def human_controlled_players(instance: Any) -> list[str]:
    return _players_by_mode(instance, "human")


def ai_controlled_players(instance: Any) -> list[str]:
    return _players_by_mode(instance, "ai")


def unclaimed_players(instance: Any) -> list[str]:
    return _players_by_mode(instance, "unclaimed")


def ensure_control(player: Any) -> bool:
    """Materialize or repair one seat record in place.

    Returns ``True`` when the record was written.  Idempotent: a record that
    already normalizes to itself is left untouched.
    """

    if not isinstance(player, MutableMapping):
        return False
    stored = player.get(CONTROL_KEY)
    record = normalize_control(stored)
    if stored == record:
        return False
    player[CONTROL_KEY] = record
    return True


def ensure_controls(instance: Any) -> list[str]:
    """Materialize and repair the control record of every seat.

    Idempotent: a seat whose stored record already normalizes to itself is left
    untouched.  Used by the aggregate so a seat written by any path (or edited by
    hand) always exposes an explicit controller.
    """

    players = getattr(instance, "players", None)
    if not isinstance(players, Mapping):
        return []
    repaired: list[str] = []
    for uid, player in players.items():
        if ensure_control(player):
            repaired.append(str(uid))
    return sorted(repaired)


def release_temporary_controls(instance: Any) -> list[str]:
    """Return temporarily AI-hosted seats to their resume mode.

    Temporary hosting means "the real player stepped away for a moment" and must
    never survive as a permanent assignment.  Restart / new-run flows that keep
    the roster call this so a seat cannot stay AI-controlled across a restart.
    """

    released: list[str] = []
    for uid in _player_uids(instance):
        record = get_control(instance, uid)
        if record["mode"] != "ai" or not record["temporary"]:
            continue
        set_control(instance, uid, str(record["resume_mode"] or DEFAULT_CONTROL_MODE))
        released.append(uid)
    return sorted(released)


def _player_uids(instance: Any) -> list[str]:
    players = getattr(instance, "players", None)
    if not isinstance(players, Mapping):
        return []
    return [str(uid) for uid in players]


def _players_by_mode(instance: Any, mode: str) -> list[str]:
    return sorted(
        uid for uid in _player_uids(instance) if control_mode(instance, uid) == mode
    )


def _player_record(instance: Any, uid: str) -> MutableMapping[str, Any] | None:
    players = getattr(instance, "players", None)
    if not isinstance(players, Mapping):
        return None
    player = players.get(uid)
    if not isinstance(player, MutableMapping):
        return None
    return player


__all__ = [
    "CONTROL_KEY",
    "CONTROL_MODES",
    "DEFAULT_CONTROL_MODE",
    "MAX_CONTROL_REVISION",
    "PlayerControlError",
    "RESUME_MODES",
    "ai_controlled_players",
    "control_mode",
    "default_control",
    "ensure_control",
    "ensure_controls",
    "get_control",
    "human_controlled_players",
    "is_ai_controlled",
    "is_human_controlled",
    "is_unclaimed",
    "normalize_control",
    "release_temporary_controls",
    "set_control",
    "unclaimed_players",
]
