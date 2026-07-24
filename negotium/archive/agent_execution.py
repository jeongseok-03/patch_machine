"""Agent work plans and execution approval records."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import portalocker

ExecutionMode = Literal["plan_only", "approved_tasks_only", "scheduled_auto_with_policies"]
PlanStatus = Literal["draft", "approved", "running", "completed", "rejected"]


@dataclass(frozen=True)
class AgentPlan:
    id: str
    title: str
    objective: str
    mode: ExecutionMode
    schedule_refs: list[str] = field(default_factory=list)
    memory_refs: list[str] = field(default_factory=list)
    steps: list[dict[str, object]] = field(default_factory=list)
    status: PlanStatus = "draft"
    created_by: str = ""
    approved_by: str = ""
    plan_markdown_path: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> AgentPlan:
        now = datetime.now(UTC).isoformat()
        return cls(
            id=str(payload.get("id") or uuid4()),
            title=str(payload.get("title") or payload.get("objective") or "Agent Plan"),
            objective=str(payload.get("objective") or ""),
            mode=_mode(payload.get("mode")),
            schedule_refs=[str(item) for item in payload.get("schedule_refs", [])],
            memory_refs=[str(item) for item in payload.get("memory_refs", [])],
            steps=[item for item in payload.get("steps", []) if isinstance(item, dict)],
            status=_status(payload.get("status")),
            created_by=str(payload.get("created_by") or ""),
            approved_by=str(payload.get("approved_by") or ""),
            plan_markdown_path=str(payload.get("plan_markdown_path") or ""),
            created_at=str(payload.get("created_at") or now),
            updated_at=now,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "objective": self.objective,
            "mode": self.mode,
            "schedule_refs": self.schedule_refs,
            "memory_refs": self.memory_refs,
            "steps": self.steps,
            "status": self.status,
            "created_by": self.created_by,
            "approved_by": self.approved_by,
            "plan_markdown_path": self.plan_markdown_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AgentExecutionStore:
    def __init__(self, archive_dir: Path) -> None:
        self._plans = archive_dir / "agent_execution" / "plans"
        self._runs = archive_dir / "agent_execution" / "runs"

    def save_plan(self, plan: AgentPlan) -> AgentPlan:
        self._plans.mkdir(parents=True, exist_ok=True)
        path = self._plans / f"{plan.id}.json"
        with portalocker.Lock(path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump(plan.to_dict(), fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return plan

    def list_plans(self) -> list[dict[str, object]]:
        plans: list[AgentPlan] = []
        for path in sorted(self._plans.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                plans.append(AgentPlan.create(**payload))
        plans.sort(key=lambda plan: plan.updated_at, reverse=True)
        return [plan.to_dict() for plan in plans]

    def read_plan(self, plan_id: str) -> AgentPlan:
        path = self._plans / f"{plan_id}.json"
        if not path.exists():
            raise ValueError("agent plan not found")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("agent plan is invalid")
        return AgentPlan.create(**payload)

    def approve_plan(self, plan_id: str, *, actor: str) -> AgentPlan:
        plan = self.read_plan(plan_id)
        approved = AgentPlan.create(
            **{**plan.to_dict(), "status": "approved", "approved_by": actor}
        )
        return self.save_plan(approved)

    def append_run(
        self, plan_id: str, *, actor: str, event: str, details: dict[str, object] | None = None
    ) -> dict[str, object]:
        self._runs.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {
            "id": str(uuid4()),
            "plan_id": plan_id,
            "actor": actor,
            "event": event,
            "details": details or {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        path = self._runs / f"{plan_id}.jsonl"
        with portalocker.Lock(path, "a", encoding="utf-8", timeout=5) as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            fh.write("\n")
        return payload


def _mode(value: object) -> ExecutionMode:
    if value in {"plan_only", "approved_tasks_only", "scheduled_auto_with_policies"}:
        return value  # type: ignore[return-value]
    return "plan_only"


def _status(value: object) -> PlanStatus:
    if value in {"draft", "approved", "running", "completed", "rejected"}:
        return value  # type: ignore[return-value]
    return "draft"
