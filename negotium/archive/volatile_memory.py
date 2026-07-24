"""Volatile, derived memory caches for global/user/session scopes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import portalocker

MemoryScope = Literal["global", "user", "session"]


@dataclass(frozen=True)
class VolatileMemory:
    scope: MemoryScope
    key: str
    summary: str = ""
    current_intent: str = ""
    active_context: str = ""
    preferences: str = ""
    open_questions: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    relevant_sources: list[str] = field(default_factory=list)
    expires_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> VolatileMemory:
        return cls(
            scope=_scope(payload.get("scope")),
            key=str(payload.get("key") or "default"),
            summary=str(payload.get("summary") or ""),
            current_intent=str(payload.get("current_intent") or ""),
            active_context=str(payload.get("active_context") or ""),
            preferences=str(payload.get("preferences") or ""),
            open_questions=[str(item) for item in payload.get("open_questions", [])],
            next_actions=[str(item) for item in payload.get("next_actions", [])],
            relevant_sources=[str(item) for item in payload.get("relevant_sources", [])],
            expires_at=str(payload.get("expires_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "key": self.key,
            "summary": self.summary,
            "current_intent": self.current_intent,
            "active_context": self.active_context,
            "preferences": self.preferences,
            "open_questions": self.open_questions,
            "next_actions": self.next_actions,
            "relevant_sources": self.relevant_sources,
            "expires_at": self.expires_at,
            "updated_at": self.updated_at,
        }

    def to_markdown(self) -> str:
        return "\n".join(
            [
                f"## 휘발성 메모리 ({self.scope}:{self.key})",
                f"- 요약: {self.summary or '(없음)'}",
                f"- 현재 의도: {self.current_intent or '(없음)'}",
                f"- 활성 컨텍스트: {self.active_context or '(없음)'}",
                f"- 선호/패턴: {self.preferences or '(없음)'}",
                f"- 열린 질문: {', '.join(self.open_questions) or '(없음)'}",
                f"- 다음 액션: {', '.join(self.next_actions) or '(없음)'}",
                f"- 원천 참조: {', '.join(self.relevant_sources) or '(없음)'}",
            ]
        )


class VolatileMemoryStore:
    def __init__(self, archive_dir: Path) -> None:
        self._root = archive_dir / "volatile_memory"
        self._legacy = archive_dir / "work_memory.json"

    def read(self, *, scope: MemoryScope = "global", key: str = "default") -> VolatileMemory:
        path = self._path(scope=scope, key=key)
        if not path.exists() and scope == "global" and self._legacy.exists():
            return self._from_legacy()
        if not path.exists():
            return VolatileMemory(scope=scope, key=key)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return VolatileMemory(scope=scope, key=key)
        return VolatileMemory.from_mapping(payload)

    def write(self, memory: VolatileMemory) -> VolatileMemory:
        updated = VolatileMemory.from_mapping(
            {**memory.to_dict(), "updated_at": datetime.now(UTC).isoformat()}
        )
        path = self._path(scope=updated.scope, key=updated.key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump(updated.to_dict(), fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return updated

    def delete(self, *, scope: MemoryScope, key: str) -> bool:
        path = self._path(scope=scope, key=key)
        if not path.exists():
            return False
        path.unlink()
        return True

    def list(self, *, scope: MemoryScope | None = None) -> list[dict[str, object]]:
        paths = (
            sorted(self._root.rglob("*.json"))
            if scope is None
            else sorted(self._scope_root(scope).glob("*.json"))
        )
        memories = []
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                memories.append(VolatileMemory.from_mapping(payload).to_dict())
        return memories

    def _path(self, *, scope: MemoryScope, key: str) -> Path:
        return self._scope_root(scope) / f"{_safe_key(key)}.json"

    def _scope_root(self, scope: MemoryScope) -> Path:
        if scope == "global":
            return self._root
        return self._root / f"{scope}s"

    def _from_legacy(self) -> VolatileMemory:
        try:
            payload = json.loads(self._legacy.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return VolatileMemory(scope="global", key="default")
        summary_parts = [
            str(payload.get("goals") or ""),
            str(payload.get("active_projects") or ""),
            str(payload.get("current_focus") or ""),
        ]
        return VolatileMemory(
            scope="global",
            key="default",
            summary="\n".join(part for part in summary_parts if part),
            active_context=str(payload.get("decisions") or ""),
            next_actions=[str(payload.get("next_actions") or "")]
            if payload.get("next_actions")
            else [],
            updated_at=str(payload.get("updated_at") or ""),
        )


def _scope(value: object) -> MemoryScope:
    if value in {"global", "user", "session"}:
        return value  # type: ignore[return-value]
    return "global"


def _safe_key(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)
    return cleaned.strip("._")[:120] or "default"
