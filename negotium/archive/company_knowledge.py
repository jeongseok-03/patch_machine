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

    def store_scan_config(self, config: dict[str, Any]) -> None:
        payload = self.read()
        payload["scan_config"] = config
        payload["updated_at"] = datetime.now(UTC).isoformat()
        write_json_file(self._path, payload)

    def scan_config(self) -> dict[str, Any]:
        config = self.read().get("scan_config")
        return config if isinstance(config, dict) else {}

    def store_report(self, report: dict[str, Any]) -> None:
        payload = self.read()
        reports = payload.get("reports")
        if not isinstance(reports, list):
            reports = []
        reports.append(report)
        payload["reports"] = reports[-24:]
        payload["updated_at"] = datetime.now(UTC).isoformat()
        write_json_file(self._path, payload)


    def store_report_schedule(self, schedule: dict[str, Any]) -> None:
        payload = self.read()
        payload["report_schedule"] = schedule
        payload["updated_at"] = datetime.now(UTC).isoformat()
        write_json_file(self._path, payload)

    def report_schedule(self) -> dict[str, Any]:
        schedule = self.read().get("report_schedule")
        return schedule if isinstance(schedule, dict) else {}

    def add_resolved_item(self, text: str, status: str) -> None:
        payload = self.read()
        items = payload.get("resolved_items")
        if not isinstance(items, list):
            items = []
        items = [item for item in items if item.get("text") != text]
        items.append({"text": text, "status": status, "at": datetime.now(UTC).isoformat()})
        payload["resolved_items"] = items[-200:]
        payload["updated_at"] = datetime.now(UTC).isoformat()
        write_json_file(self._path, payload)

    def resolved_item_texts(self) -> list[str]:
        items = self.read().get("resolved_items")
        if not isinstance(items, list):
            return []
        return [str(item.get("text")) for item in items if item.get("text")]

    def latest_report(self) -> dict[str, Any]:
        reports = self.read().get("reports")
        if isinstance(reports, list) and reports and isinstance(reports[-1], dict):
            return reports[-1]
        return {}
