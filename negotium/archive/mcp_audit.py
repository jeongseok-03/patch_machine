"""MCP tool audit log store."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import portalocker


@dataclass(frozen=True)
class McpToolAuditRecord:
    id: str
    actor: str
    mcp_server: str
    tool_name: str
    arguments_redacted: dict[str, Any] = field(default_factory=dict)
    result_summary: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"
    policy: dict[str, Any] = field(default_factory=dict)
    guard_findings: list[str] = field(default_factory=list)
    approved_by: str = ""
    created_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> McpToolAuditRecord:
        return cls(
            id=str(payload.get("id") or uuid4()),
            actor=str(payload.get("actor") or ""),
            mcp_server=str(payload.get("mcp_server") or "patchnote-mcp-hub"),
            tool_name=str(payload.get("tool_name") or ""),
            arguments_redacted=dict(payload.get("arguments_redacted") or {}),
            result_summary=dict(payload.get("result_summary") or {}),
            risk_level=str(payload.get("risk_level") or "low"),
            policy=dict(payload.get("policy") or {}),
            guard_findings=[str(item) for item in payload.get("guard_findings", [])],
            approved_by=str(payload.get("approved_by") or ""),
            created_at=str(payload.get("created_at") or datetime.now(UTC).isoformat()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "actor": self.actor,
            "mcp_server": self.mcp_server,
            "tool_name": self.tool_name,
            "arguments_redacted": self.arguments_redacted,
            "result_summary": self.result_summary,
            "risk_level": self.risk_level,
            "policy": self.policy,
            "guard_findings": self.guard_findings,
            "approved_by": self.approved_by,
            "created_at": self.created_at,
        }


class McpAuditStore:
    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "mcp_hub" / "audit" / "tool_calls.jsonl"

    def record(self, **payload: Any) -> dict[str, Any]:
        record = McpToolAuditRecord.create(**payload)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(self._path, "a", encoding="utf-8", timeout=5) as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
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
                records.append(McpToolAuditRecord.create(**payload).to_dict())
        records.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return records[: max(1, min(limit, 500))]
