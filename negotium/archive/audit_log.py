"""Append-only audit log for administrative and state-changing actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from negotium.archive._store import append_jsonl_line, iter_jsonl_records


@dataclass(frozen=True)
class AuditRecord:
    id: str
    actor: str
    action: str
    target: str
    target_id: str
    timestamp: str
    details: dict[str, object]

    @classmethod
    def create(
        cls,
        *,
        actor: str,
        action: str,
        target: str,
        target_id: str = "",
        details: dict[str, object] | None = None,
    ) -> AuditRecord:
        return cls(
            id=str(uuid4()),
            actor=actor or "anonymous",
            action=action,
            target=target,
            target_id=target_id,
            timestamp=datetime.now(UTC).isoformat(),
            details=details or {},
        )

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> AuditRecord:
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        return cls(
            id=str(payload.get("id") or ""),
            actor=str(payload.get("actor") or "anonymous"),
            action=str(payload.get("action") or ""),
            target=str(payload.get("target") or ""),
            target_id=str(payload.get("target_id") or ""),
            timestamp=str(payload.get("timestamp") or ""),
            details={str(key): value for key, value in details.items()},
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "target_id": self.target_id,
            "timestamp": self.timestamp,
            "details": self.details,
        }


class AuditLogStore:
    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "audit_log.jsonl"

    @property
    def path(self) -> Path:
        return self._path

    def record(
        self,
        *,
        actor: str,
        action: str,
        target: str,
        target_id: str = "",
        details: dict[str, object] | None = None,
    ) -> AuditRecord:
        record = AuditRecord.create(
            actor=actor,
            action=action,
            target=target,
            target_id=target_id,
            details=details,
        )
        append_jsonl_line(self._path, record.to_dict(), sort_keys=True)
        return record

    def list_recent(self, *, limit: int = 100) -> list[dict[str, object]]:
        records = [AuditRecord.from_mapping(payload) for payload in iter_jsonl_records(self._path)]
        return [record.to_dict() for record in records[-limit:]][::-1]
