"""Append-only LLM/user conversation transcripts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import portalocker


@dataclass(frozen=True)
class ConversationRecord:
    id: str
    user_id: str
    role: str
    content: str
    provider: str
    model: str
    route: str
    created_at: str
    derived_from: list[str]
    metadata: dict[str, object]

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        role: str,
        content: str,
        provider: str = "",
        model: str = "",
        route: str = "",
        derived_from: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ConversationRecord:
        return cls(
            id=str(uuid4()),
            user_id=user_id,
            role=role,
            content=content,
            provider=provider,
            model=model,
            route=route,
            created_at=datetime.now(UTC).isoformat(),
            derived_from=derived_from or [],
            metadata=metadata or {},
        )

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> ConversationRecord:
        return cls(
            id=str(payload.get("id") or ""),
            user_id=str(payload.get("user_id") or ""),
            role=str(payload.get("role") or ""),
            content=str(payload.get("content") or ""),
            provider=str(payload.get("provider") or ""),
            model=str(payload.get("model") or ""),
            route=str(payload.get("route") or ""),
            created_at=str(payload.get("created_at") or ""),
            derived_from=[str(item) for item in payload.get("derived_from", [])],
            metadata={str(key): value for key, value in (payload.get("metadata") or {}).items()},
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "role": self.role,
            "content": self.content,
            "provider": self.provider,
            "model": self.model,
            "route": self.route,
            "created_at": self.created_at,
            "derived_from": self.derived_from,
            "metadata": self.metadata,
        }


class ConversationStore:
    def __init__(self, archive_dir: Path) -> None:
        self._root = archive_dir / "conversations"

    def append(self, record: ConversationRecord) -> None:
        path = self._path_for(record.user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(path, "a", encoding="utf-8", timeout=5) as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True))
            fh.write("\n")

    def append_pair(
        self,
        *,
        user_id: str,
        user_message: str,
        assistant_message: str,
        provider: str,
        model: str,
        route: str,
        source_refs: list[str] | None = None,
    ) -> None:
        self.append(
            ConversationRecord.create(
                user_id=user_id,
                role="user",
                content=user_message,
                provider=provider,
                model=model,
                route=route,
                derived_from=source_refs,
            )
        )
        self.append(
            ConversationRecord.create(
                user_id=user_id,
                role="assistant",
                content=assistant_message,
                provider=provider,
                model=model,
                route=route,
                derived_from=source_refs,
            )
        )

    def list_recent(
        self, *, user_id: str | None = None, limit: int = 100
    ) -> list[dict[str, object]]:
        paths = [self._path_for(user_id)] if user_id else sorted(self._root.glob("*.jsonl"))
        records: list[ConversationRecord] = []
        for path in paths:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    records.append(ConversationRecord.from_mapping(payload))
        return [record.to_dict() for record in records[-limit:]][::-1]

    def _path_for(self, user_id: str | None) -> Path:
        safe = "".join(
            ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in (user_id or "unknown")
        )
        return self._root / f"{datetime.now(UTC).strftime('%Y-%m-%d')}_{safe or 'unknown'}.jsonl"
