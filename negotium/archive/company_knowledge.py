"""Cached per-file summaries and the synthesized company profile.

The initial company scan is expensive (hundreds of documents), so each file's
summary is cached with its mtime/size fingerprint. Rescans only re-summarize
files that changed, which also makes periodic progress reports cheap.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from negotium.archive._store import read_json_file, write_json_file


class CompanyKnowledgeStore:
    """File-backed cache: per-file summaries plus the synthesized profile."""

    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "company_knowledge.json"

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> dict[str, Any]:
        payload = read_json_file(self._path, default=dict)
        if not isinstance(payload, dict):
            return {}
        return payload

    def file_summaries(self) -> dict[str, dict[str, Any]]:
        summaries = self.read().get("file_summaries")
        return summaries if isinstance(summaries, dict) else {}

    def cached_summary(self, path: str, *, mtime: float, size: int) -> str | None:
        entry = self.file_summaries().get(path)
        if not isinstance(entry, dict):
            return None
        if entry.get("mtime") == mtime and entry.get("size") == size:
            summary = entry.get("summary")
            return str(summary) if summary else None
        return None

    def store_summaries(self, entries: dict[str, dict[str, Any]]) -> None:
        payload = self.read()
        summaries = payload.get("file_summaries")
        if not isinstance(summaries, dict):
            summaries = {}
        summaries.update(entries)
        payload["file_summaries"] = summaries
        payload["updated_at"] = datetime.now(UTC).isoformat()
        write_json_file(self._path, payload)

    def store_profile(self, profile: dict[str, Any]) -> None:
        payload = self.read()
        payload["company_profile"] = profile
        payload["updated_at"] = datetime.now(UTC).isoformat()
        write_json_file(self._path, payload)

    def company_profile(self) -> dict[str, Any]:
        profile = self.read().get("company_profile")
        return profile if isinstance(profile, dict) else {}
