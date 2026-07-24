"""Curated public company/reference cases for MCP reuse."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import portalocker


@dataclass(frozen=True)
class PublicReferenceCase:
    id: str
    title: str
    url: str = ""
    industry: str = ""
    department: str = ""
    organization_size: str = ""
    summary: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> PublicReferenceCase:
        return cls(
            id=str(payload.get("id") or uuid4()),
            title=str(payload.get("title") or "공개 사례"),
            url=str(payload.get("url") or ""),
            industry=str(payload.get("industry") or ""),
            department=str(payload.get("department") or ""),
            organization_size=str(payload.get("organization_size") or ""),
            summary=str(payload.get("summary") or ""),
            content=str(payload.get("content") or ""),
            tags=[str(item) for item in payload.get("tags", [])],
            created_at=str(payload.get("created_at") or datetime.now(UTC).isoformat()),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "industry": self.industry,
            "department": self.department,
            "organization_size": self.organization_size,
            "summary": self.summary,
            "content": self.content,
            "tags": self.tags,
            "created_at": self.created_at,
        }


class PublicReferenceStore:
    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "public_references" / "cases.jsonl"

    def capture(self, **payload: Any) -> PublicReferenceCase:
        case = PublicReferenceCase.create(**payload)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(self._path, "a", encoding="utf-8", timeout=5) as fh:
            fh.write(json.dumps(case.to_dict(), ensure_ascii=False, sort_keys=True))
            fh.write("\n")
        return case

    def list(self, *, limit: int = 200) -> list[dict[str, object]]:
        if not self._path.exists():
            return []
        cases: list[PublicReferenceCase] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                cases.append(PublicReferenceCase.create(**payload))
        cases.sort(key=lambda item: item.created_at, reverse=True)
        return [case.to_dict() for case in cases[: max(1, min(limit, 1000))]]

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, object]]:
        terms = {term.lower() for term in query.split() if term.strip()}
        cases = self.list(limit=1000)
        if not terms:
            return cases[:limit]
        results: list[dict[str, object]] = []
        for case in cases:
            haystack = " ".join(
                str(case.get(key) or "")
                for key in ("title", "summary", "content", "industry", "department", "tags")
            ).lower()
            if all(term in haystack for term in terms):
                results.append(case)
        return results[:limit]
