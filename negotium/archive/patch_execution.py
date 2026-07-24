"""File-backed PatchOps execution attempts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import portalocker


@dataclass(frozen=True)
class PatchExecutionAttempt:
    id: str
    patch_run_id: str
    branch_name: str = ""
    diff_hash: str = ""
    status: str = "created"
    applied_files: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    command_results: list[dict[str, Any]] = field(default_factory=list)
    pr_draft: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> PatchExecutionAttempt:
        now = datetime.now(UTC).isoformat()
        return cls(
            id=str(payload.get("id") or uuid4()),
            patch_run_id=str(payload.get("patch_run_id") or ""),
            branch_name=str(payload.get("branch_name") or ""),
            diff_hash=str(payload.get("diff_hash") or ""),
            status=str(payload.get("status") or "created"),
            applied_files=[str(item) for item in payload.get("applied_files", [])],
            blocked_reasons=[str(item) for item in payload.get("blocked_reasons", [])],
            command_results=[
                item for item in payload.get("command_results", []) if isinstance(item, dict)
            ],
            pr_draft=dict(payload.get("pr_draft") or {}),
            created_at=str(payload.get("created_at") or now),
            updated_at=now,
        )

    def with_updates(self, **updates: Any) -> PatchExecutionAttempt:
        return PatchExecutionAttempt.create(**{**self.to_dict(), **updates})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "patch_run_id": self.patch_run_id,
            "branch_name": self.branch_name,
            "diff_hash": self.diff_hash,
            "status": self.status,
            "applied_files": self.applied_files,
            "blocked_reasons": self.blocked_reasons,
            "command_results": self.command_results,
            "pr_draft": self.pr_draft,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class PatchExecutionStore:
    def __init__(self, archive_dir: Path) -> None:
        self._attempts = archive_dir / "patch_ops" / "execution_attempts"

    def save(self, attempt: PatchExecutionAttempt) -> PatchExecutionAttempt:
        self._attempts.mkdir(parents=True, exist_ok=True)
        path = self._attempts / f"{attempt.id}.json"
        with portalocker.Lock(path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump(attempt.to_dict(), fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return attempt

    def create(self, **payload: Any) -> PatchExecutionAttempt:
        return self.save(PatchExecutionAttempt.create(**payload))

    def read(self, attempt_id: str) -> PatchExecutionAttempt:
        path = self._attempts / f"{attempt_id}.json"
        if not path.exists():
            raise ValueError("patch execution attempt not found")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("patch execution attempt is invalid")
        return PatchExecutionAttempt.create(**payload)

    def list(self, *, patch_run_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        attempts: list[PatchExecutionAttempt] = []
        for path in sorted(self._attempts.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            attempt = PatchExecutionAttempt.create(**payload)
            if patch_run_id and attempt.patch_run_id != patch_run_id:
                continue
            attempts.append(attempt)
        attempts.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_dict() for item in attempts[: max(1, min(limit, 500))]]
