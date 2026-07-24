"""Persistent process plans grouping ordered work-schedule steps."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import portalocker

ProcessPlanStatus = Literal["draft", "approved", "running", "paused", "completed", "cancelled"]
ProcessPlanMode = Literal["manual", "auto"]

_STATUSES = {"draft", "approved", "running", "paused", "completed", "cancelled"}
_MODES = {"manual", "auto"}

ProcessPlanList = list["ProcessPlan"]


@dataclass(frozen=True)
class ProcessPlan:
    id: str
    objective: str = ""
    architecture_path: str = ""
    status: ProcessPlanStatus = "draft"
    mode: ProcessPlanMode = "manual"
    step_ids: list[str] = field(default_factory=list)
    approved_by: str = ""
    approved_at: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> ProcessPlan:
        now = datetime.now(UTC).isoformat()
        return cls(
            id=str(payload.get("id") or uuid4()),
            objective=str(payload.get("objective") or "").strip(),
            architecture_path=str(payload.get("architecture_path") or "").strip(),
            status=_status(payload.get("status")),
            mode=_mode(payload.get("mode")),
            step_ids=[
                str(item).strip() for item in payload.get("step_ids", []) if str(item).strip()
            ],
            approved_by=str(payload.get("approved_by") or "").strip(),
            approved_at=str(payload.get("approved_at") or "").strip(),
            created_at=str(payload.get("created_at") or now),
            updated_at=now,
        )

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> ProcessPlan:
        return cls.create(**payload)

    def with_status(self, status: str, *, approved_by: str = "") -> ProcessPlan:
        approved_at = self.approved_at
        actor = self.approved_by
        if status == "approved" and not self.approved_at:
            approved_at = datetime.now(UTC).isoformat()
            actor = approved_by or self.approved_by
        return replace(
            self,
            status=_status(status),
            approved_by=actor,
            approved_at=approved_at,
            updated_at=datetime.now(UTC).isoformat(),
        )

    def with_mode(self, mode: str) -> ProcessPlan:
        return replace(self, mode=_mode(mode), updated_at=datetime.now(UTC).isoformat())

    def with_steps(self, step_ids: list[str]) -> ProcessPlan:
        cleaned = [str(item).strip() for item in step_ids if str(item).strip()]
        return replace(self, step_ids=cleaned, updated_at=datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "objective": self.objective,
            "architecture_path": self.architecture_path,
            "status": self.status,
            "mode": self.mode,
            "step_ids": list(self.step_ids),
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ProcessPlanStore:
    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "process_plans.json"

    def list(self) -> list[dict[str, object]]:
        items = sorted(self._read_items(), key=lambda item: item.created_at, reverse=True)
        return [item.to_dict() for item in items]

    def get(self, plan_id: str) -> ProcessPlan | None:
        for item in self._read_items():
            if item.id == plan_id:
                return item
        return None

    def find_by_architecture(self, architecture_path: str) -> ProcessPlan | None:
        for item in self._read_items():
            if item.architecture_path == architecture_path:
                return item
        return None

    def upsert(self, plan: ProcessPlan) -> ProcessPlan:
        items = [existing for existing in self._read_items() if existing.id != plan.id]
        items.append(plan)
        self._write_items(items)
        return plan

    def delete(self, plan_id: str) -> bool:
        items = self._read_items()
        next_items = [item for item in items if item.id != plan_id]
        self._write_items(next_items)
        return len(next_items) != len(items)

    def _read_items(self) -> ProcessPlanList:
        if not self._path.exists():
            return []
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return []
        payload = json.loads(raw)
        if not isinstance(payload, list):
            return []
        return [ProcessPlan.from_mapping(item) for item in payload if isinstance(item, dict)]

    def _write_items(self, items: ProcessPlanList) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(self._path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump([item.to_dict() for item in items], fh, ensure_ascii=False, indent=2)
            fh.write("\n")


def _status(value: object) -> ProcessPlanStatus:
    status = str(value or "draft")
    if status in _STATUSES:
        return status  # type: ignore[return-value]
    return "draft"


def _mode(value: object) -> ProcessPlanMode:
    mode = str(value or "manual")
    if mode in _MODES:
        return mode  # type: ignore[return-value]
    return "manual"
