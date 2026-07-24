"""Current work memory and worker scheduling stores."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from negotium.archive._store import read_json_file, write_json_file

WorkStatus = Literal["todo", "in_progress", "blocked", "done", "cancelled"]
WorkPriority = Literal["low", "normal", "high", "urgent"]

# Module-level aliases so annotations resolve the builtin ``list`` even though
# ``WorkScheduleStore`` defines a method named ``list`` that shadows it in class scope.
ScheduleItemRows = list[dict[str, object]]
ScheduleItemList = list["WorkScheduleItem"]


@dataclass(frozen=True)
class WorkMemory:
    goals: str = ""
    active_projects: str = ""
    current_focus: str = ""
    blockers: str = ""
    decisions: str = ""
    risks: str = ""
    next_actions: str = ""
    updated_at: str = ""

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> WorkMemory:
        return cls(
            goals=str(payload.get("goals") or ""),
            active_projects=str(payload.get("active_projects") or ""),
            current_focus=str(payload.get("current_focus") or ""),
            blockers=str(payload.get("blockers") or ""),
            decisions=str(payload.get("decisions") or ""),
            risks=str(payload.get("risks") or ""),
            next_actions=str(payload.get("next_actions") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "goals": self.goals,
            "active_projects": self.active_projects,
            "current_focus": self.current_focus,
            "blockers": self.blockers,
            "decisions": self.decisions,
            "risks": self.risks,
            "next_actions": self.next_actions,
            "updated_at": self.updated_at,
        }

    def to_markdown(self) -> str:
        return "\n".join(
            [
                "## 현재 작업 메모리",
                f"- 목표: {self.goals or '(미설정)'}",
                f"- 진행 프로젝트: {self.active_projects or '(미설정)'}",
                f"- 현재 집중: {self.current_focus or '(미설정)'}",
                f"- 병목/블로커: {self.blockers or '(미설정)'}",
                f"- 결정사항: {self.decisions or '(미설정)'}",
                f"- 리스크: {self.risks or '(미설정)'}",
                f"- 다음 액션: {self.next_actions or '(미설정)'}",
            ]
        )


@dataclass(frozen=True)
class WorkScheduleItem:
    id: str
    title: str
    owner_id: str = ""
    owner_name: str = ""
    status: WorkStatus = "todo"
    priority: WorkPriority = "normal"
    start_date: str = ""
    due_date: str = ""
    dependencies: list[str] = field(default_factory=list)
    notes: str = ""
    source_architecture_id: str = ""
    queue_order: int = 0
    assignee_kind: str = "unassigned"
    signed_off_by: str = ""
    signed_off_at: str = ""
    completion_record: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> WorkScheduleItem:
        now = datetime.now(UTC).isoformat()
        return cls(
            id=str(payload.get("id") or uuid4()),
            title=str(payload.get("title") or "").strip(),
            owner_id=str(payload.get("owner_id") or "").strip(),
            owner_name=str(payload.get("owner_name") or "").strip(),
            status=_status(payload.get("status")),
            priority=_priority(payload.get("priority")),
            start_date=str(payload.get("start_date") or "").strip(),
            due_date=str(payload.get("due_date") or "").strip(),
            dependencies=[
                str(item).strip() for item in payload.get("dependencies", []) if str(item).strip()
            ],
            notes=str(payload.get("notes") or "").strip(),
            source_architecture_id=str(payload.get("source_architecture_id") or "").strip(),
            queue_order=_safe_int(payload.get("queue_order")),
            assignee_kind=_assignee_kind(payload.get("assignee_kind")),
            signed_off_by=str(payload.get("signed_off_by") or "").strip(),
            signed_off_at=str(payload.get("signed_off_at") or "").strip(),
            completion_record=str(payload.get("completion_record") or "").strip(),
            created_at=str(payload.get("created_at") or now),
            updated_at=now,
        )

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> WorkScheduleItem:
        return cls.create(**payload)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "owner_id": self.owner_id,
            "owner_name": self.owner_name,
            "status": self.status,
            "priority": self.priority,
            "start_date": self.start_date,
            "due_date": self.due_date,
            "dependencies": self.dependencies,
            "notes": self.notes,
            "source_architecture_id": self.source_architecture_id,
            "queue_order": self.queue_order,
            "assignee_kind": self.assignee_kind,
            "signed_off_by": self.signed_off_by,
            "signed_off_at": self.signed_off_at,
            "completion_record": self.completion_record,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class WorkMemoryStore:
    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "work_memory.json"

    def read(self) -> WorkMemory:
        payload = read_json_file(self._path, default=dict)
        if not payload:
            return WorkMemory()
        if not isinstance(payload, dict):
            raise ValueError("work memory must be a JSON object")
        return WorkMemory.from_mapping(payload)

    def write(self, memory: WorkMemory) -> WorkMemory:
        updated = WorkMemory(**{**memory.to_dict(), "updated_at": datetime.now(UTC).isoformat()})
        write_json_file(self._path, updated.to_dict())
        return updated


class WorkScheduleStore:
    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "work_schedule.json"

    def list(self) -> ScheduleItemRows:
        items = sorted(self._read_items(), key=lambda item: (item.queue_order, item.created_at))
        return [item.to_dict() for item in items]

    def get(self, item_id: str) -> WorkScheduleItem | None:
        for item in self._read_items():
            if item.id == item_id:
                return item
        return None

    def upsert(self, item: WorkScheduleItem) -> WorkScheduleItem:
        if not item.title:
            raise ValueError("schedule item title is required")
        items = [existing for existing in self._read_items() if existing.id != item.id]
        saved = WorkScheduleItem.create(**item.to_dict())
        items.append(saved)
        self._write_items(items)
        return saved

    def delete(self, item_id: str) -> bool:
        items = self._read_items()
        next_items = [item for item in items if item.id != item_id]
        self._write_items(next_items)
        return len(next_items) != len(items)

    def _read_items(self) -> ScheduleItemList:
        payload = read_json_file(self._path, default=list)
        if not isinstance(payload, list):
            return []
        return [WorkScheduleItem.from_mapping(item) for item in payload if isinstance(item, dict)]

    def _write_items(self, items: ScheduleItemList) -> None:
        write_json_file(self._path, [item.to_dict() for item in items])


def _status(value: object) -> WorkStatus:
    status = str(value or "todo")
    if status in {"todo", "in_progress", "blocked", "done", "cancelled"}:
        return status  # type: ignore[return-value]
    return "todo"


def _assignee_kind(value: object) -> str:
    kind = str(value or "unassigned")
    if kind in {"unassigned", "human", "ai"}:
        return kind
    return "unassigned"


def _priority(value: object) -> WorkPriority:
    priority = str(value or "normal")
    if priority in {"low", "normal", "high", "urgent"}:
        return priority  # type: ignore[return-value]
    return "normal"


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0
