"""Small, explicit import receipts for legacy package materialization.

Receipts are bookkeeping for package-owned objects, not a second content
authority.  Canonical stores remain authoritative; uninstall uses a receipt
only to select objects and still re-checks ownership before deleting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _safe_component(value: Any) -> str:
    text = str(value or "").strip()
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in text)[:120] or "unknown"


def _record_key(item: dict[str, str]) -> tuple[str, str]:
    return (str(item.get("type") or ""), str(item.get("id") or ""))


@dataclass
class ImportReceipt:
    source_kind: str
    source_id: str
    source_version: str = ""
    source_digest: str = ""
    created_objects: list[dict[str, str]] = field(default_factory=list)
    updated_objects: list[dict[str, str]] = field(default_factory=list)
    user_detached_objects: list[dict[str, str]] = field(default_factory=list)

    def add(
        self,
        object_type: str,
        object_id: str,
        *,
        updated: bool = False,
        fingerprint: str = "",
    ) -> None:
        """Record one package-written object.

        ``fingerprint`` is the content the package last wrote.  A re-import
        refreshes it everywhere the object is listed, so uninstall compares
        the live object against what the package itself left behind.
        """
        key = (str(object_type), str(object_id))
        target = self.updated_objects if updated else self.created_objects
        record = next((item for item in target if _record_key(item) == key), None)
        if record is None:
            record = {"type": key[0], "id": key[1]}
            target.append(record)
        if fingerprint:
            for listed in (*self.created_objects, *self.updated_objects):
                if _record_key(listed) == key:
                    listed["fingerprint"] = str(fingerprint)

    def fingerprint(self, object_type: str, object_id: str) -> str:
        key = (str(object_type), str(object_id))
        for item in self.created_objects:
            if _record_key(item) == key:
                return str(item.get("fingerprint") or "")
        return ""

    def detach(self, object_type: str, object_id: str) -> None:
        """Mark an object as user-owned: uninstall must keep it."""
        record = {"type": str(object_type), "id": str(object_id)}
        if record not in self.user_detached_objects:
            self.user_detached_objects.append(record)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "source_digest": self.source_digest,
            "created_objects": list(self.created_objects),
            "updated_objects": list(self.updated_objects),
            "user_detached_objects": list(self.user_detached_objects),
        }


class ImportReceiptStore:
    """JSON sidecar store scoped to the host data directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, source_id: str) -> Path:
        return self.root / "content-receipts" / f"{_safe_component(source_id)}.json"

    def load(self, source_id: str) -> ImportReceipt | None:
        path = self._path(source_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError:
            raise
        except (ValueError, TypeError) as exc:
            raise ValueError("content import receipt is invalid") from exc
        if not isinstance(payload, dict):
            raise ValueError("content import receipt must be an object")
        return ImportReceipt(
            source_kind=str(payload.get("source_kind") or "module"),
            source_id=str(payload.get("source_id") or source_id),
            source_version=str(payload.get("source_version") or ""),
            source_digest=str(payload.get("source_digest") or ""),
            created_objects=[dict(item) for item in payload.get("created_objects", []) if isinstance(item, dict)],
            updated_objects=[dict(item) for item in payload.get("updated_objects", []) if isinstance(item, dict)],
            user_detached_objects=[dict(item) for item in payload.get("user_detached_objects", []) if isinstance(item, dict)],
        )

    def save(self, receipt: ImportReceipt) -> None:
        path = self._path(receipt.source_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(receipt.as_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

    def record(
        self,
        source_id: str,
        *,
        source_version: str = "",
        source_digest: str = "",
        object_type: str,
        object_id: str,
        updated: bool = False,
        fingerprint: str = "",
    ) -> None:
        receipt = self.load(source_id) or ImportReceipt(
            source_kind="module",
            source_id=str(source_id),
            source_version=str(source_version or ""),
            source_digest=str(source_digest or ""),
        )
        receipt.add(object_type, object_id, updated=updated, fingerprint=fingerprint)
        self.save(receipt)

    def discard(self, source_id: str) -> None:
        self._path(source_id).unlink(missing_ok=True)


__all__ = ["ImportReceipt", "ImportReceiptStore"]
