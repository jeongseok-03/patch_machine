"""File-backed MCP runtime session metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import portalocker


@dataclass(frozen=True)
class McpSession:
    id: str
    client_name: str = ""
    protocol_version: str = "2025-03-26"
    status: str = "initialized"
    capabilities: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> McpSession:
        now = datetime.now(UTC).isoformat()
        return cls(
            id=str(payload.get("id") or uuid4()),
            client_name=str(payload.get("client_name") or ""),
            protocol_version=str(payload.get("protocol_version") or "2025-03-26"),
            status=str(payload.get("status") or "initialized"),
            capabilities=dict(payload.get("capabilities") or {}),
            created_at=str(payload.get("created_at") or now),
            updated_at=now,
        )

    def with_updates(self, **updates: Any) -> McpSession:
        return McpSession.create(
            **{
                **self.to_dict(),
                **updates,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "client_name": self.client_name,
            "protocol_version": self.protocol_version,
            "status": self.status,
            "capabilities": self.capabilities,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class McpSessionStore:
    def __init__(self, archive_dir: Path) -> None:
        self._sessions = archive_dir / "mcp_hub" / "sessions"

    def create(self, **payload: Any) -> McpSession:
        session = McpSession.create(**payload)
        return self.save(session)

    def save(self, session: McpSession) -> McpSession:
        self._sessions.mkdir(parents=True, exist_ok=True)
        path = self._sessions / f"{session.id}.json"
        with portalocker.Lock(path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump(session.to_dict(), fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return session

    def read(self, session_id: str) -> McpSession:
        path = self._sessions / f"{session_id}.json"
        if not path.exists():
            raise ValueError("MCP session not found")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("MCP session is invalid")
        return McpSession.create(**payload)

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        records: list[McpSession] = []
        for path in sorted(self._sessions.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                records.append(McpSession.create(**payload))
        records.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_dict() for item in records[: max(1, min(limit, 500))]]
