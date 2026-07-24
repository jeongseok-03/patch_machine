"""Context compression cache derived from permanent memory sources."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import portalocker

from negotium.archive.volatile_memory import MemoryScope


@dataclass(frozen=True)
class CompressedContext:
    scope: MemoryScope
    key: str
    summary: str = ""
    facts: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    open_threads: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    token_budget: int = 4000
    updated_at: str = ""

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> CompressedContext:
        return cls(
            scope=str(payload.get("scope") or "global"),  # type: ignore[arg-type]
            key=str(payload.get("key") or "default"),
            summary=str(payload.get("summary") or ""),
            facts=[str(item) for item in payload.get("facts", [])],
            decisions=[str(item) for item in payload.get("decisions", [])],
            constraints=[str(item) for item in payload.get("constraints", [])],
            open_threads=[str(item) for item in payload.get("open_threads", [])],
            source_refs=[str(item) for item in payload.get("source_refs", [])],
            token_budget=int(payload.get("token_budget") or 4000),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "key": self.key,
            "summary": self.summary,
            "facts": self.facts,
            "decisions": self.decisions,
            "constraints": self.constraints,
            "open_threads": self.open_threads,
            "source_refs": self.source_refs,
            "token_budget": self.token_budget,
            "updated_at": self.updated_at,
        }

    def to_markdown(self) -> str:
        return "\n".join(
            [
                f"## 압축 컨텍스트 ({self.scope}:{self.key})",
                self.summary or "(없음)",
                "",
                "### Facts",
                *[f"- {item}" for item in self.facts],
                "### Decisions",
                *[f"- {item}" for item in self.decisions],
                "### Constraints",
                *[f"- {item}" for item in self.constraints],
                "### Open Threads",
                *[f"- {item}" for item in self.open_threads],
                "### Source Refs",
                *[f"- {item}" for item in self.source_refs],
            ]
        )


class CompressedContextStore:
    def __init__(self, archive_dir: Path) -> None:
        self._root = archive_dir / "volatile_memory" / "compressed"

    def read(self, *, scope: MemoryScope = "global", key: str = "default") -> CompressedContext:
        path = self._path(scope=scope, key=key)
        if not path.exists():
            return CompressedContext(scope=scope, key=key)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return CompressedContext(scope=scope, key=key)
        return CompressedContext.from_mapping(payload)

    def write(self, context: CompressedContext) -> CompressedContext:
        updated = CompressedContext.from_mapping(
            {**context.to_dict(), "updated_at": datetime.now(UTC).isoformat()}
        )
        path = self._path(scope=updated.scope, key=updated.key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump(updated.to_dict(), fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return updated

    def _path(self, *, scope: MemoryScope, key: str) -> Path:
        if scope == "global":
            return self._root / f"{_safe(key)}.json"
        return self._root / f"{scope}s" / f"{_safe(key)}.json"


def _safe(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)
    return cleaned.strip("._")[:120] or "default"
