"""Markdown patch records readable by coding agents (Cursor / Claude Code / Codex)."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import portalocker


@dataclass(frozen=True)
class PatchRecord:
    record_id: str
    title: str
    summary: str
    request: str = ""
    plan: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    follow_ups: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    actor: str = ""
    agent: str = ""
    created_at: str = ""
    relative_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "title": self.title,
            "summary": self.summary,
            "request": self.request,
            "plan": list(self.plan),
            "changed_files": list(self.changed_files),
            "verification": list(self.verification),
            "follow_ups": list(self.follow_ups),
            "tags": list(self.tags),
            "actor": self.actor,
            "agent": self.agent,
            "created_at": self.created_at,
            "relative_path": self.relative_path,
        }


_INDEX_NAME = "index.jsonl"


class PatchRecordStore:
    """Append-only collection of patch records.

    Each record is written as a Markdown file plus a JSONL index entry so that
    coding agents can scan the index and open individual notes.
    """

    def __init__(self, archive_dir: Path) -> None:
        self._root = archive_dir / "patch_records"
        self._index_path = self._root / _INDEX_NAME

    @property
    def root(self) -> Path:
        return self._root

    @property
    def index_path(self) -> Path:
        return self._index_path

    def list(self, *, limit: int = 50) -> list[PatchRecord]:
        if not self._index_path.exists():
            return []
        entries: list[PatchRecord] = []
        for line in self._index_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            entries.append(_record_from_payload(payload))
        entries.sort(key=lambda item: item.created_at, reverse=True)
        return entries[:limit]

    def get(self, record_id: str) -> PatchRecord | None:
        for record in self.list(limit=10_000):
            if record.record_id == record_id:
                return record
        return None

    def read_markdown(self, record_id: str) -> str | None:
        record = self.get(record_id)
        if record is None:
            return None
        path = self._root / record.relative_path
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def append(
        self,
        *,
        title: str,
        summary: str,
        request: str = "",
        plan: list[str] | None = None,
        changed_files: list[str] | None = None,
        verification: list[str] | None = None,
        follow_ups: list[str] | None = None,
        tags: list[str] | None = None,
        actor: str = "",
        agent: str = "",
        now: datetime | None = None,
    ) -> PatchRecord:
        moment = now or datetime.now(UTC)
        timestamp = moment.strftime("%Y%m%d_%H%M%S")
        slug = _slugify(title) or "patch-record"
        record_id = f"{timestamp}_{slug}"
        rel_path = f"{moment.strftime('%Y/%m')}/{record_id}.md"
        target = self._root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        record = PatchRecord(
            record_id=record_id,
            title=title.strip() or "Untitled patch record",
            summary=summary.strip(),
            request=request.strip(),
            plan=_normalize_lines(plan),
            changed_files=_normalize_lines(changed_files),
            verification=_normalize_lines(verification),
            follow_ups=_normalize_lines(follow_ups),
            tags=_normalize_lines(tags),
            actor=actor.strip(),
            agent=agent.strip(),
            created_at=moment.isoformat(),
            relative_path=rel_path,
        )
        target.write_text(_render_markdown(record), encoding="utf-8")
        self._root.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(self._index_path, "a", encoding="utf-8", timeout=5) as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True))
            fh.write("\n")
        return record


def _record_from_payload(payload: dict[str, Any]) -> PatchRecord:
    return PatchRecord(
        record_id=str(payload.get("record_id") or ""),
        title=str(payload.get("title") or ""),
        summary=str(payload.get("summary") or ""),
        request=str(payload.get("request") or ""),
        plan=_normalize_lines(payload.get("plan")),
        changed_files=_normalize_lines(payload.get("changed_files")),
        verification=_normalize_lines(payload.get("verification")),
        follow_ups=_normalize_lines(payload.get("follow_ups")),
        tags=_normalize_lines(payload.get("tags")),
        actor=str(payload.get("actor") or ""),
        agent=str(payload.get("agent") or ""),
        created_at=str(payload.get("created_at") or ""),
        relative_path=str(payload.get("relative_path") or ""),
    )


def _normalize_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [line.strip() for line in value.splitlines()]
    elif isinstance(value, (list, tuple)):
        items = []
        for entry in value:
            for line in str(entry).splitlines():
                items.append(line.strip())
    else:
        items = [str(value).strip()]
    return [item for item in items if item]


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = re.sub(r"[\s/]+", "-", normalized)
    normalized = re.sub(r"[^0-9A-Za-z\-_가-힣]", "", normalized)
    return normalized.lower()[:60]


def _render_markdown(record: PatchRecord) -> str:
    lines: list[str] = []
    lines.append(f"# {record.title}")
    lines.append("")
    lines.append(f"- ID: `{record.record_id}`")
    if record.created_at:
        lines.append(f"- Created: `{record.created_at}`")
    if record.actor:
        lines.append(f"- Actor: `{record.actor}`")
    if record.agent:
        lines.append(f"- Coding agent: `{record.agent}`")
    if record.tags:
        lines.append(f"- Tags: {', '.join(f'`{tag}`' for tag in record.tags)}")
    lines.append("")
    if record.summary:
        lines.append("## Summary")
        lines.append("")
        lines.append(record.summary)
        lines.append("")
    if record.request:
        lines.append("## Request")
        lines.append("")
        lines.append(record.request)
        lines.append("")
    if record.plan:
        lines.append("## Plan")
        lines.append("")
        for item in record.plan:
            lines.append(f"- {item}")
        lines.append("")
    if record.changed_files:
        lines.append("## Changed files")
        lines.append("")
        for item in record.changed_files:
            lines.append(f"- `{item}`")
        lines.append("")
    if record.verification:
        lines.append("## Verification")
        lines.append("")
        for item in record.verification:
            lines.append(f"- {item}")
        lines.append("")
    if record.follow_ups:
        lines.append("## Follow-ups")
        lines.append("")
        for item in record.follow_ups:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
