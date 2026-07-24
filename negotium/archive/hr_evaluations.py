"""Append-only HR evaluation records."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import portalocker


@dataclass(frozen=True)
class HrEvaluationRecord:
    id: str
    user_id: str
    period: str
    work_item_ids: list[str]
    draft: str
    final_text: str
    evidence: str
    created_by: str
    created_at: str
    document_path: str = ""
    source_refs: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        period: str,
        work_item_ids: list[str],
        draft: str,
        final_text: str,
        evidence: str,
        created_by: str,
        document_path: str = "",
        source_refs: list[str] | None = None,
    ) -> HrEvaluationRecord:
        return cls(
            id=str(uuid4()),
            user_id=user_id,
            period=period,
            work_item_ids=work_item_ids,
            draft=draft,
            final_text=final_text,
            evidence=evidence,
            created_by=created_by,
            created_at=datetime.now(UTC).isoformat(),
            document_path=document_path,
            source_refs=source_refs or [],
        )

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> HrEvaluationRecord:
        return cls(
            id=str(payload.get("id") or ""),
            user_id=str(payload.get("user_id") or ""),
            period=str(payload.get("period") or ""),
            work_item_ids=[str(item) for item in payload.get("work_item_ids", [])],
            draft=str(payload.get("draft") or ""),
            final_text=str(payload.get("final_text") or ""),
            evidence=str(payload.get("evidence") or ""),
            created_by=str(payload.get("created_by") or ""),
            created_at=str(payload.get("created_at") or ""),
            document_path=str(payload.get("document_path") or ""),
            source_refs=[str(item) for item in payload.get("source_refs", [])],
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "period": self.period,
            "work_item_ids": self.work_item_ids,
            "draft": self.draft,
            "final_text": self.final_text,
            "evidence": self.evidence,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "document_path": self.document_path,
            "source_refs": self.source_refs,
        }


class HrEvaluationStore:
    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "hr" / "evaluations.jsonl"

    def append(self, record: HrEvaluationRecord) -> HrEvaluationRecord:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(self._path, "a", encoding="utf-8", timeout=5) as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True))
            fh.write("\n")
        return record

    def list_recent(self, *, user_id: str = "", limit: int = 100) -> list[dict[str, object]]:
        if not self._path.exists():
            return []
        records: list[HrEvaluationRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            record = HrEvaluationRecord.from_mapping(payload)
            if user_id and record.user_id != user_id:
                continue
            records.append(record)
        records.sort(key=lambda item: item.created_at, reverse=True)
        return [record.to_dict() for record in records[: max(1, min(limit, 500))]]
