"""Permanent memory source scanner.

Permanent memory is source material that LLMs can reread: patch logs, audit
events, generated documents, promoted memory, and conversation transcripts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import portalocker

SourceKind = Literal[
    "patch_log",
    "audit_log",
    "document",
    "conversation",
    "promoted_memory",
    "patch_record",
    "upload",
    "token_usage",
    "unknown",
]


@dataclass(frozen=True)
class PermanentMemorySource:
    id: str
    kind: SourceKind
    path: str
    title: str
    excerpt: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "path": self.path,
            "title": self.title,
            "excerpt": self.excerpt,
            "updated_at": self.updated_at,
        }


class PermanentMemoryStore:
    def __init__(self, archive_dir: Path) -> None:
        self._archive_dir = archive_dir
        self._promoted_dir = archive_dir / "memory" / "promoted"

    def recent(self, *, limit: int = 50) -> list[dict[str, object]]:
        sources = self._scan_sources()
        sources.sort(key=lambda source: source.updated_at, reverse=True)
        return [source.to_dict() for source in sources[:limit]]

    def search(self, query: str, *, limit: int = 50) -> list[dict[str, object]]:
        tokens = query.strip().lower().split()
        sources = self._scan_sources()
        if tokens:
            sources = [source for source in sources if _matches_tokens(source, tokens)]
        sources.sort(key=lambda source: source.updated_at, reverse=True)
        return [source.to_dict() for source in sources[:limit]]

    def read_source(self, source_id: str, *, max_chars: int = 12_000) -> dict[str, object]:
        """Read one source body by archive-relative id/path."""

        cleaned, path = self._resolve_source_path(source_id)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(cleaned)
        kind = _kind_for(path, self._archive_dir)
        if kind == "unknown":
            raise ValueError("unsupported source kind")
        source = _source_from_path(path, self._archive_dir, kind)
        content = _read_content(path, max_chars=max(1, max_chars))
        return {**source.to_dict(), "content": content}

    def delete_source(self, source_id: str) -> dict[str, object]:
        """Delete an archive-backed source after archive-relative validation."""

        cleaned, path = self._resolve_source_path(source_id)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(cleaned)
        kind = _kind_for(path, self._archive_dir)
        if kind == "unknown":
            raise ValueError("unsupported source kind")
        if kind in {"audit_log", "token_usage"}:
            raise ValueError(f"{kind} sources cannot be deleted from the memory UI")
        source = _source_from_path(path, self._archive_dir, kind).to_dict()
        path.unlink()
        return source

    def resolve_sources(
        self,
        *,
        query: str,
        limit: int,
        source_ids: list[str] | None,
    ) -> list[dict[str, object]]:
        """Return sources for compression/refresh.

        When ``source_ids`` is non-empty, return those sources in request order
        (``id`` equals relative archive path). Otherwise behave like :meth:`search`.
        """
        cap = max(1, min(limit, 50))
        if not source_ids:
            return self.search(query, limit=cap)
        all_sources = self._scan_sources()
        by_id: dict[str, PermanentMemorySource] = {s.id: s for s in all_sources}
        ordered: list[PermanentMemorySource] = []
        seen: set[str] = set()
        for sid in source_ids:
            sid = sid.strip()
            if not sid or sid in seen:
                continue
            src = by_id.get(sid)
            if src is not None:
                ordered.append(src)
                seen.add(sid)
            if len(ordered) >= cap:
                break
        return [s.to_dict() for s in ordered]

    def promote(
        self,
        *,
        title: str,
        content: str,
        source_refs: list[str],
        actor: str,
    ) -> dict[str, object]:
        self._promoted_dir.mkdir(parents=True, exist_ok=True)
        memory_id = str(uuid4())
        safe = _safe_slug(title or "promoted_memory")
        path = self._promoted_dir / f"{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{safe}.md"
        rendered = "\n".join(
            [
                "---",
                f"id: {memory_id}",
                f"created_at: {datetime.now(UTC).isoformat()}",
                f"created_by: {actor}",
                "source_refs:",
                *[f"- {ref}" for ref in source_refs],
                "---",
                "",
                f"# {title or 'Promoted Memory'}",
                "",
                content,
                "",
            ]
        )
        with portalocker.Lock(path, "w", encoding="utf-8", timeout=5) as fh:
            fh.write(rendered)
        return {
            "id": memory_id,
            "kind": "promoted_memory",
            "path": path.relative_to(self._archive_dir).as_posix(),
            "title": title,
            "source_refs": source_refs,
        }

    def _scan_sources(self) -> list[PermanentMemorySource]:
        if not self._archive_dir.exists():
            return []
        tombstoned = self._tombstoned_source_ids()
        sources: list[PermanentMemorySource] = []
        for path in self._archive_dir.rglob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            if _is_operational_internal_file(path, self._archive_dir):
                continue
            kind = _kind_for(path, self._archive_dir)
            if kind == "unknown":
                continue
            source = _source_from_path(path, self._archive_dir, kind)
            if source.id in tombstoned or source.path in tombstoned:
                continue
            sources.append(source)
        return sources

    def _resolve_source_path(self, source_id: str) -> tuple[str, Path]:
        cleaned = source_id.strip().lstrip("/")
        if not cleaned or "\x00" in cleaned:
            raise ValueError("invalid source id")
        path = (self._archive_dir / cleaned).resolve()
        archive_root = self._archive_dir.resolve()
        try:
            path.relative_to(archive_root)
        except ValueError as exc:
            raise ValueError("source path escapes archive") from exc
        return cleaned, path

    def _tombstoned_source_ids(self) -> set[str]:
        path = self._archive_dir / "memory" / "tombstones.jsonl"
        if not path.exists():
            return set()
        tombstoned: set[str] = set()
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return tombstoned
        for line in lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            for key in ("target_id", "source_path"):
                value = str(payload.get(key) or "").strip().lstrip("/")
                if value:
                    tombstoned.add(value)
        return tombstoned


def _matches_tokens(source: PermanentMemorySource, tokens: list[str]) -> bool:
    """Every query token must appear in the title, excerpt, or path.

    Separators are collapsed so e.g. token "patchops" matches path "patch_ops/...".
    """
    haystack = f"{source.title}\n{source.excerpt}\n{source.path}".lower()
    compact = haystack.replace("_", "").replace("-", "")
    return all(
        token in haystack or token.replace("_", "").replace("-", "") in compact for token in tokens
    )


def _kind_for(path: Path, archive_dir: Path) -> SourceKind:
    try:
        rel = path.relative_to(archive_dir)
    except ValueError:
        return "unknown"
    parts = rel.parts
    if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit() and path.suffix == ".md":
        return "patch_log"
    if parts and parts[0] == "conversations" and path.suffix == ".jsonl":
        return "conversation"
    if parts[:2] == ("memory", "promoted") and path.suffix == ".md":
        return "promoted_memory"
    if parts and parts[0] == "patch_records" and path.suffix in {".md", ".jsonl"}:
        return "patch_record"
    if (
        parts
        and parts[0] == "uploads"
        and path.suffix in {".md", ".markdown", ".txt", ".json", ".jsonl", ".yaml", ".yml"}
    ):
        return "upload"
    if parts[:2] == ("patch_ops", "workspaces") and path.suffix in {
        ".md",
        ".patch",
        ".txt",
        ".json",
    }:
        return "document"
    if (
        parts
        and parts[0] in {"documents", "hr", "handover", "work_architecture"}
        and path.suffix in {".md", ".jsonl"}
    ):
        return "document"
    return "unknown"


def _is_operational_internal_file(path: Path, archive_dir: Path) -> bool:
    try:
        rel = path.relative_to(archive_dir)
    except ValueError:
        return True
    parts = rel.parts
    return rel.as_posix() == "audit_log.jsonl" or bool(
        parts and parts[0] in {"token_usage", "context_firewall", "mcp_hub"}
    )


def _source_from_path(path: Path, archive_dir: Path, kind: SourceKind) -> PermanentMemorySource:
    text = _read_excerpt(path)
    title = _title_for(path, text)
    updated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    rel = path.relative_to(archive_dir).as_posix()
    return PermanentMemorySource(
        id=rel,
        kind=kind,
        path=rel,
        title=title,
        excerpt=text[:600],
        updated_at=updated_at,
    )


def _read_excerpt(path: Path) -> str:
    try:
        if path.suffix == ".jsonl":
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-5:]
            rendered: list[str] = []
            for line in lines:
                try:
                    payload = json.loads(line)
                    rendered.append(
                        str(payload.get("content") or payload.get("action") or payload)[:240]
                    )
                except (json.JSONDecodeError, AttributeError):
                    rendered.append(line[:240])
            return "\n".join(rendered)
        return path.read_text(encoding="utf-8", errors="ignore")[:1200]
    except OSError:
        return ""


def _read_content(path: Path, *, max_chars: int) -> str:
    try:
        if path.suffix == ".jsonl":
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            return "\n".join(lines[-80:])[:max_chars]
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except OSError:
        return ""


def _title_for(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return path.stem


def _safe_slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return cleaned.strip("_")[:80] or "memory"
