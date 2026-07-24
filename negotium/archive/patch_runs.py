"""File-backed PatchOps run state and event records."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import portalocker

PatchRunStatus = Literal[
    "CREATED",
    "REPO_SCANNING",
    "CONTEXT_BUILT",
    "QUESTIONS_GENERATED",
    "PLAN_CREATED",
    "WAITING_APPROVAL",
    "DIFF_DRAFTED",
    "PATCHING",
    "PATCH_APPLIED",
    "TESTING",
    "TESTS_FAILED",
    "TESTS_PASSED",
    "PR_DRAFTED",
    "VERIFICATION_PLANNED",
    "MEMORY_WRITTEN",
    "COMPLETED",
    "BLOCKED_NEEDS_USER_INPUT",
    "BLOCKED_POLICY_VIOLATION",
    "FAILED_PATCH_DRAFT",
    "FAILED_PATCH_APPLY",
    "CANCELLED",
]
AutonomyLevel = Literal["L0", "L1", "L2", "L3", "L4", "L5"]
PrivacyMode = Literal["local_only", "hybrid_redacted", "frontier_assisted"]
RiskLevel = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class PatchRun:
    id: str
    repo_id: str
    request: str
    autonomy_level: AutonomyLevel = "L1"
    privacy_mode: PrivacyMode = "hybrid_redacted"
    target_branch: str = "main"
    status: PatchRunStatus = "CREATED"
    risk_level: RiskLevel = "medium"
    created_by: str = ""
    approved_by: str = ""
    plan: dict[str, Any] = field(default_factory=dict)
    questions: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> PatchRun:
        now = datetime.now(UTC).isoformat()
        return cls(
            id=str(payload.get("id") or uuid4()),
            repo_id=str(payload.get("repo_id") or "local"),
            request=str(payload.get("request") or ""),
            autonomy_level=_autonomy(payload.get("autonomy_level")),
            privacy_mode=_privacy(payload.get("privacy_mode")),
            target_branch=str(payload.get("target_branch") or "main"),
            status=_status(payload.get("status")),
            risk_level=_risk(payload.get("risk_level")),
            created_by=str(payload.get("created_by") or ""),
            approved_by=str(payload.get("approved_by") or ""),
            plan=dict(payload.get("plan") or {}),
            questions=[item for item in payload.get("questions", []) if isinstance(item, dict)],
            artifacts=dict(payload.get("artifacts") or {}),
            context=dict(payload.get("context") or {}),
            constraints=dict(payload.get("constraints") or {}),
            created_at=str(payload.get("created_at") or now),
            updated_at=now,
        )

    def with_updates(self, **updates: Any) -> PatchRun:
        return PatchRun.create(**{**self.to_dict(), **updates})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "repo_id": self.repo_id,
            "request": self.request,
            "autonomy_level": self.autonomy_level,
            "privacy_mode": self.privacy_mode,
            "target_branch": self.target_branch,
            "status": self.status,
            "risk_level": self.risk_level,
            "created_by": self.created_by,
            "approved_by": self.approved_by,
            "plan": self.plan,
            "questions": self.questions,
            "artifacts": self.artifacts,
            "context": self.context,
            "constraints": self.constraints,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class PatchRunStore:
    def __init__(self, archive_dir: Path) -> None:
        self._archive_dir = archive_dir
        self._runs = archive_dir / "patch_ops" / "runs"
        self._events = archive_dir / "patch_ops" / "events"
        self._workspaces = archive_dir / "patch_ops" / "workspaces"

    def create(self, run: PatchRun) -> PatchRun:
        return self.save(run)

    def save(self, run: PatchRun) -> PatchRun:
        self._runs.mkdir(parents=True, exist_ok=True)
        path = self._runs / f"{run.id}.json"
        with portalocker.Lock(path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump(run.to_dict(), fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return run

    def list(self) -> list[dict[str, Any]]:
        runs: list[PatchRun] = []
        for path in sorted(self._runs.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                runs.append(PatchRun.create(**payload))
        runs.sort(key=lambda run: run.updated_at, reverse=True)
        return [run.to_dict() for run in runs]

    def read(self, run_id: str) -> PatchRun:
        path = self._runs / f"{run_id}.json"
        if not path.exists():
            raise ValueError("patch run not found")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("patch run is invalid")
        return PatchRun.create(**payload)

    def update(self, run_id: str, **updates: Any) -> PatchRun:
        return self.save(self.read(run_id).with_updates(**updates))

    def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        summary: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._events.mkdir(parents=True, exist_ok=True)
        event = {
            "id": str(uuid4()),
            "patch_run_id": run_id,
            "type": event_type,
            "summary": summary,
            "payload": payload or {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        path = self._events / f"{run_id}.jsonl"
        with portalocker.Lock(path, "a", encoding="utf-8", timeout=5) as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            fh.write("\n")
        return event

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        path = self._events / f"{run_id}.jsonl"
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    def write_artifact(self, run_id: str, relative_path: str, content: str) -> dict[str, Any]:
        path = self._artifact_path(run_id, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(path, "w", encoding="utf-8", timeout=5) as fh:
            fh.write(content.rstrip())
            fh.write("\n")
        return self._artifact_payload(path)

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        root = self._workspace_root(run_id)
        if not root.exists():
            return []
        files = [
            path for path in root.rglob("*") if path.is_file() and not path.name.startswith(".")
        ]
        files.sort(key=lambda item: (item.parent.as_posix(), item.name))
        return [self._artifact_payload(path) for path in files]

    def read_artifact(
        self, run_id: str, relative_path: str, *, max_chars: int = 200_000
    ) -> dict[str, Any]:
        path = self._artifact_path(run_id, relative_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(relative_path)
        payload = self._artifact_payload(path)
        payload["content"] = path.read_text(encoding="utf-8", errors="replace")[:max_chars]
        return payload

    def _workspace_root(self, run_id: str) -> Path:
        safe_id = _safe_segment(run_id)
        return (self._workspaces / safe_id).resolve()

    def _artifact_path(self, run_id: str, relative_path: str) -> Path:
        root = self._workspace_root(run_id)
        cleaned = relative_path.strip().lstrip("/")
        if not cleaned or "\x00" in cleaned:
            raise ValueError("invalid artifact path")
        path = (root / cleaned).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("artifact path escapes patch workspace") from exc
        if any(part in {"", ".", ".."} for part in Path(cleaned).parts):
            raise ValueError("invalid artifact path")
        return path

    def _artifact_payload(self, path: Path) -> dict[str, Any]:
        rel = path.relative_to(self._archive_dir).as_posix()
        name = path.name
        return {
            "path": rel,
            "name": name,
            "kind": _artifact_kind(name),
            "title": _artifact_title(name),
            "bytes": path.stat().st_size,
            "updated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
        }


def _status(value: object) -> PatchRunStatus:
    allowed = set(PatchRunStatus.__args__)  # type: ignore[attr-defined]
    return value if value in allowed else "CREATED"  # type: ignore[return-value]


def _autonomy(value: object) -> AutonomyLevel:
    return value if value in {"L0", "L1", "L2", "L3", "L4", "L5"} else "L1"  # type: ignore[return-value]


def _privacy(value: object) -> PrivacyMode:
    if value in {"local_only", "hybrid_redacted", "frontier_assisted"}:
        return value  # type: ignore[return-value]
    return "hybrid_redacted"


def _risk(value: object) -> RiskLevel:
    return value if value in {"low", "medium", "high", "critical"} else "medium"  # type: ignore[return-value]


def _safe_segment(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value).strip("_")
    if not cleaned:
        raise ValueError("invalid patch run id")
    return cleaned[:120]


def _artifact_kind(name: str) -> str:
    if name.endswith(".patch"):
        return "diff"
    if name.endswith(".md"):
        return "markdown"
    if name.endswith(".json"):
        return "json"
    return "text"


def _artifact_title(name: str) -> str:
    titles = {
        "plan.md": "코딩 에이전트 계획서",
    }
    return titles.get(name, name)
