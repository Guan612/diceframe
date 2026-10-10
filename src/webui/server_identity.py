"""Stable identity of one DiceFrame server installation.

Clients that sync content with several servers need to tell those servers
apart. A base URL is not an identity: a LAN address or a tunnel host changes
while the server (its data directory) stays the same. The instance id is a
random value generated once and stored in the data directory, so it follows
the data rather than the host, and it reveals nothing about the machine.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path

from aiohttp import web

logger = logging.getLogger("trpg")

SERVER_IDENTITY_FILE = "server_identity.json"
_INSTANCE_ID_PATTERN = re.compile(r"^srv-[0-9a-f]{32}$")


class ServerIdentityError(RuntimeError):
    """The stored identity exists but cannot be trusted: fail closed."""


class ServerIdentityStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / SERVER_IDENTITY_FILE
        self._instance_id: str | None = None

    def instance_id(self) -> str:
        """Return the persisted id, generating it on first use.

        A present but unreadable or malformed file is never replaced: a fresh
        id would silently make every client treat this server as a new one.
        """

        if self._instance_id is not None:
            return self._instance_id
        if self.path.exists():
            self._instance_id = self._read()
            return self._instance_id
        instance_id = f"srv-{uuid.uuid4().hex}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"version": 1, "instance_id": instance_id}), encoding="utf-8",
        )
        temporary.replace(self.path)
        self._instance_id = instance_id
        return instance_id

    def _read(self) -> str:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ServerIdentityError("server identity file is unreadable") from exc
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ServerIdentityError("server identity file has an unknown shape")
        instance_id = payload.get("instance_id")
        if not isinstance(instance_id, str) or not _INSTANCE_ID_PATTERN.fullmatch(instance_id):
            raise ServerIdentityError("server identity file holds an invalid id")
        return instance_id


SERVER_IDENTITY_KEY = web.AppKey("server_identity", ServerIdentityStore)


def server_instance_id(app: web.Application) -> str | None:
    """The instance id for responses; ``None`` (and a log) if it is unusable."""

    store = app.get(SERVER_IDENTITY_KEY)
    if store is None:
        return None
    try:
        return store.instance_id()
    except (ServerIdentityError, OSError):
        logger.error("服务器实例标识不可用，已从响应中省略", exc_info=True)
        return None
