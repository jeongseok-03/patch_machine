"""Deletion approval workflow for sensitive memory records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import portalocker

DeletionStatus = Literal["pending", "approved", "rejected", "tombstoned"]


@dataclass(frozen=True)
class DeletionRequest:
    id: str
    requester: str
    target_type: str
    target_id: str
    summary: str
    source_path: str
    sensitivity: str
    reason: str
    status: DeletionStatus
    created_at: str
    approved_by: str = ""
    decided_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> DeletionRequest:
        return cls(
            id=str(payload.get("id") or uuid4()),
            requester=str(payload.get("requester") or ""),
            target_type=str(payload.get("target_type") or ""),
            target_id=str(payload.get("target_id") or ""),
            summary=str(payload.get("summary") or ""),
            source_path=str(payload.get("source_path") or ""),
            sensitivity=str(payload.get("sensitivity") or "internal"),
            reason=str(payload.get("reason") or ""),
            status=_status(payload.get("status")),
            created_at=str(payload.get("created_at") or datetime.now(UTC).isoformat()),
            approved_by=str(payload.get("approved_by") or ""),
            decided_at=str(payload.get("decided_at") or ""),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "requester": self.requester,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "summary": self.summary,
            "source_path": self.source_path,
            "sensitivity": self.sensitivity,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at,
            "approved_by": self.approved_by,
            "decided_at": self.decided_at,
        }


class DeletionRequestStore:
    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "memory" / "deletion_requests.json"
        self._tombstones = archive_dir / "memory" / "tombstones.jsonl"

    def create(self, request: DeletionRequest) -> DeletionRequest:
        requests = self._read()
        requests.append(request)
        self._write(requests)
        return request

    def list(self) -> list[dict[str, object]]:
        return [request.to_dict() for request in self._read()]

    def get(self, request_id: str) -> DeletionRequest | None:
        return next((request for request in self._read() if request.id == request_id), None)

    def decide(self, request_id: str, *, actor: str, approved: bool) -> DeletionRequest:
        requests = self._read()
        target = next((request for request in requests if request.id == request_id), None)
        if target is None:
            raise ValueError("deletion request not found")
        decided = DeletionRequest.create(
            **{
                **target.to_dict(),
                "status": "approved" if approved else "rejected",
                "approved_by": actor,
                "decided_at": datetime.now(UTC).isoformat(),
            }
        )
        requests = [decided if request.id == request_id else request for request in requests]
        self._write(requests)
        if approved:
            self._append_tombstone(decided)
        return decided

    def _append_tombstone(self, request: DeletionRequest) -> None:
        self._tombstones.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            **request.to_dict(),
            "status": "tombstoned",
            "tombstoned_at": datetime.now(UTC).isoformat(),
        }
        with portalocker.Lock(self._tombstones, "a", encoding="utf-8", timeout=5) as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            fh.write("\n")

    def _read(self) -> list[DeletionRequest]:
        if not self._path.exists():
            return []
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        return (
            [DeletionRequest.create(**item) for item in payload if isinstance(item, dict)]
            if isinstance(payload, list)
            else []
        )

    def _write(self, requests: list[DeletionRequest]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(self._path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump([request.to_dict() for request in requests], fh, ensure_ascii=False, indent=2)
            fh.write("\n")


def _status(value: object) -> DeletionStatus:
    if value in {"pending", "approved", "rejected", "tombstoned"}:
        return value  # type: ignore[return-value]
    return "pending"
