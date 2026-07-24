"""Persistent AI job status records for UI feedback."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import portalocker

AiJobStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass(frozen=True)
class AiJobRecord:
    job_id: str
    task: str
    status: AiJobStatus = "queued"
    actor: str = ""
    input_summary: str = ""
    used_sources: list[str] | None = None
    result_path: str = ""
    error: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(
        cls,
        *,
        task: str,
        actor: str,
        input_summary: str = "",
        used_sources: list[str] | None = None,
    ) -> AiJobRecord:
        now = datetime.now(UTC).isoformat()
        return cls(
            job_id=str(uuid4()),
            task=task.strip() or "ai_task",
            status="queued",
            actor=actor.strip(),
            input_summary=input_summary.strip()[:800],
            used_sources=used_sources or [],
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> AiJobRecord:
        status = str(payload.get("status") or "queued")
        if status not in {"queued", "running", "succeeded", "failed"}:
            status = "queued"
        return cls(
            job_id=str(payload.get("job_id") or ""),
            task=str(payload.get("task") or ""),
            status=status,  # type: ignore[arg-type]
            actor=str(payload.get("actor") or ""),
            input_summary=str(payload.get("input_summary") or ""),
            used_sources=[str(item) for item in payload.get("used_sources", [])],
            result_path=str(payload.get("result_path") or ""),
            error=str(payload.get("error") or ""),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def with_status(
        self,
        status: AiJobStatus,
        *,
        result_path: str = "",
        error: str = "",
        used_sources: list[str] | None = None,
    ) -> AiJobRecord:
        return replace(
            self,
            status=status,
            result_path=result_path or self.result_path,
            error=error,
            used_sources=used_sources if used_sources is not None else self.used_sources,
            updated_at=datetime.now(UTC).isoformat(),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "task": self.task,
            "status": self.status,
            "actor": self.actor,
            "input_summary": self.input_summary,
            "used_sources": list(self.used_sources or []),
            "result_path": self.result_path,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AiJobStore:
    def __init__(self, archive_dir: Path) -> None:
        self._root = archive_dir / "ai_jobs"

    def create(
        self,
        *,
        task: str,
        actor: str,
        input_summary: str = "",
        used_sources: list[str] | None = None,
    ) -> AiJobRecord:
        record = AiJobRecord.create(
            task=task,
            actor=actor,
            input_summary=input_summary,
            used_sources=used_sources,
        )
        self._append(record)
        return record

    def update(self, record: AiJobRecord) -> AiJobRecord:
        self._append(record)
        return record

    def get(self, job_id: str) -> AiJobRecord | None:
        for record in self.recent(limit=10_000):
            if record.job_id == job_id:
                return record
        return None

    def recent(self, *, limit: int = 50) -> list[AiJobRecord]:
        if not self._root.exists():
            return []
        records_by_id: dict[str, AiJobRecord] = {}
        for path in sorted(self._root.glob("*.jsonl")):
            for record in self._read_jsonl(path):
                records_by_id[record.job_id] = record
        records = list(records_by_id.values())
        records.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
        return records[: max(1, limit)]

    def _path_for_today(self) -> Path:
        return self._root / f"{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"

    def _append(self, record: AiJobRecord) -> None:
        path = self._path_for_today()
        path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(path, "a", encoding="utf-8", timeout=5) as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True))
            fh.write("\n")

    def _read_jsonl(self, path: Path) -> list[AiJobRecord]:
        records: list[AiJobRecord] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return records
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(AiJobRecord.from_mapping(payload))
        return records
