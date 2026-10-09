"""Room access settings and credentials, retained across game resets.

Per-seat share credentials live here too.  Only a SHA-256 digest of each seat
token is stored; the plaintext is returned once by ``issue_seat_token`` and
never persisted, exported or projected.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Any

from src.engine.module_state import (
    ModuleStateError, ModuleStateSpec, get_module_state, register_module_state,
)

MODULE_NAME = "room_access"
SCHEMA_VERSION = 2
SEAT_TOKEN_BYTES = 24


def fresh() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "max_players": 6,
        "player_access_open": True,
        "bot_bind_token": "",
        "room_password": "",
        "room_token": "",
        "seat_credentials": {},
    }


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    # The old codec used data.get(key, default): only missing keys default.
    # Preserve present values, including None and unconventional types.
    for key, default in fresh().items():
        raw.setdefault(key, default)
    if not isinstance(raw.get("seat_credentials"), dict):
        raw["seat_credentials"] = {}
    return raw


def require_writable(instance: Any) -> None:
    """Read-only transaction preflight; never repair or materialize a slot."""
    modules = getattr(instance, "modules", None)
    if not isinstance(modules, dict):
        raise ModuleStateError("instance has no module state container")
    slot = modules.get(MODULE_NAME)
    if not isinstance(slot, dict):
        return  # Missing/corrupt slots have the documented fresh default.
    if slot.get("schema_version") != SCHEMA_VERSION:
        raise ModuleStateError(f"unsupported room_access module schema: {slot.get('schema_version')!r}")


def max_players(instance: Any) -> int:
    return get_module_state(instance, MODULE_NAME)["max_players"]


def replace_max_players(instance: Any, value: int) -> None:
    get_module_state(instance, MODULE_NAME)["max_players"] = value


def player_access_open(instance: Any) -> bool:
    return get_module_state(instance, MODULE_NAME)["player_access_open"]


def replace_player_access_open(instance: Any, value: bool) -> None:
    get_module_state(instance, MODULE_NAME)["player_access_open"] = value


def bot_bind_token(instance: Any) -> str:
    return get_module_state(instance, MODULE_NAME)["bot_bind_token"]


def replace_bot_bind_token(instance: Any, value: str) -> None:
    get_module_state(instance, MODULE_NAME)["bot_bind_token"] = value


def room_password(instance: Any) -> str:
    return get_module_state(instance, MODULE_NAME)["room_password"]


def replace_room_password(instance: Any, value: str) -> None:
    get_module_state(instance, MODULE_NAME)["room_password"] = value


def room_token(instance: Any) -> str:
    return get_module_state(instance, MODULE_NAME)["room_token"]


def replace_room_token(instance: Any, value: str) -> None:
    get_module_state(instance, MODULE_NAME)["room_token"] = value


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_seat_token(instance: Any, uid: str) -> str:
    """Issue a new share credential for ``uid`` and return its plaintext once.

    Any previous credential for the seat is replaced, so older links stop
    working.  Only the digest is stored.
    """
    uid = str(uid or "")
    if not uid:
        raise ValueError("seat uid is required")
    require_writable(instance)
    credentials = get_module_state(instance, MODULE_NAME)["seat_credentials"]
    previous = credentials.get(uid)
    epoch = int(previous.get("epoch", 0)) + 1 if isinstance(previous, dict) else 1
    token = secrets.token_urlsafe(SEAT_TOKEN_BYTES)
    credentials[uid] = {
        "hash": _token_digest(token),
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "epoch": epoch,
    }
    return token


def verify_seat_token(instance: Any, token: str) -> str | None:
    """Return the seat uid a token belongs to, or ``None``.

    Compares against every stored digest in constant time and never stops
    early, so timing does not reveal which seat (if any) matched.
    """
    if not isinstance(token, str) or not token:
        return None
    digest = _token_digest(token)
    matched: str | None = None
    credentials = get_module_state(instance, MODULE_NAME)["seat_credentials"]
    for uid, record in credentials.items():
        stored = record.get("hash") if isinstance(record, dict) else None
        if isinstance(stored, str) and hmac.compare_digest(stored, digest):
            matched = str(uid)
    return matched


def revoke_seat_token(instance: Any, uid: str) -> bool:
    """Drop a seat's credential. Returns whether one existed."""
    require_writable(instance)
    credentials = get_module_state(instance, MODULE_NAME)["seat_credentials"]
    return credentials.pop(str(uid or ""), None) is not None


def has_seat_token(instance: Any, uid: str) -> bool:
    return str(uid or "") in get_module_state(instance, MODULE_NAME)["seat_credentials"]


def copy_seat_credentials(target: Any, source: Any) -> None:
    """Carry seat credentials into a new run that keeps the same seats."""
    require_writable(target)
    get_module_state(target, MODULE_NAME)["seat_credentials"] = copy.deepcopy(
        get_module_state(source, MODULE_NAME)["seat_credentials"]
    )


def scrub_seat_credentials(payload: Any) -> None:
    """Remove stored seat digests from a raw save payload (export/import).

    Credentials never travel with a save: an imported game issues new ones.
    """
    modules = payload.get("modules") if isinstance(payload, dict) else None
    slot = modules.get(MODULE_NAME) if isinstance(modules, dict) else None
    if isinstance(slot, dict) and "seat_credentials" in slot:
        slot["seat_credentials"] = {}


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)
