"""Context Firewall audit records.

The firewall audit intentionally stores counts, hashes, and policy decisions
only. Raw source text must not be persisted here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import portalocker


@dataclass(frozen=True)
class ContextFirewallAuditRecord:
    id: str
    actor: str = ""
    agent_run_id: str = ""
    destination: str = "local"
    task_type: str = ""
    decision: str = "local_only"
    highest_sensitivity: str = "S3"
    detectors_triggered: list[str] = field(default_factory=list)
    removed_counts: dict[str, int] = field(default_factory=dict)
    blocked_items: list[str] = field(default_factory=list)
    raw_content_stored: bool = False
    redacted_context_hash: str = ""
    created_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> ContextFirewallAuditRecord:
        removed = payload.get("removed_counts")
        return cls(
            id=str(payload.get("id") or uuid4()),
            actor=str(payload.get("actor") or ""),
            agent_run_id=str(payload.get("agent_run_id") or ""),
            destination=str(payload.get("destination") or "local"),
            task_type=str(payload.get("task_type") or ""),
            decision=str(payload.get("decision") or "local_only"),
            highest_sensitivity=str(payload.get("highest_sensitivity") or "S3"),
            detectors_triggered=[str(item) for item in payload.get("detectors_triggered", [])],
            removed_counts={
                str(key): int(value)
                for key, value in (removed.items() if isinstance(removed, dict) else [])
            },
            blocked_items=[str(item) for item in payload.get("blocked_items", [])],
            raw_content_stored=bool(payload.get("raw_content_stored", False)),
            redacted_context_hash=str(payload.get("redacted_context_hash") or ""),
            created_at=str(payload.get("created_at") or datetime.now(UTC).isoformat()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "actor": self.actor,
            "agent_run_id": self.agent_run_id,
            "destination": self.destination,
            "task_type": self.task_type,
            "decision": self.decision,
            "highest_sensitivity": self.highest_sensitivity,
            "detectors_triggered": self.detectors_triggered,
            "removed_counts": self.removed_counts,
            "blocked_items": self.blocked_items,
            "raw_content_stored": self.raw_content_stored,
            "redacted_context_hash": self.redacted_context_hash,
            "created_at": self.created_at,
        }


class ContextFirewallStore:
    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "context_firewall" / "audit.jsonl"

    def record(self, **payload: Any) -> dict[str, Any]:
        record = ContextFirewallAuditRecord.create(**payload)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(self._path, "a", encoding="utf-8", timeout=5) as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True))
            fh.write("\n")
        return record.to_dict()

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(ContextFirewallAuditRecord.create(**payload).to_dict())
        records.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return records[: max(1, min(limit, 500))]
