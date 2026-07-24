"""Company announcements (공지) — file-backed store."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from negotium.archive._store import read_json_file, write_json_file


class AnnouncementStore:
    """Pinned-first list of company announcements."""

    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "announcements.json"

    @property
    def path(self) -> Path:
        return self._path

    def list(self) -> list[dict[str, Any]]:
        payload = read_json_file(self._path, default=list)
        items = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
        newest_first = sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return sorted(newest_first, key=lambda item: not item.get("pinned"))

    def create(
        self, *, title: str, body: str, author_id: str, author_name: str, pinned: bool = False
    ) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex[:12],
            "title": title,
            "body": body,
            "author_id": author_id,
            "author_name": author_name,
            "pinned": pinned,
            "created_at": datetime.now(UTC).isoformat(),
        }
        payload = read_json_file(self._path, default=list)
        items = payload if isinstance(payload, list) else []
        items.append(record)
        write_json_file(self._path, items[-500:])
        return record

    def delete(self, announcement_id: str) -> bool:
        payload = read_json_file(self._path, default=list)
        items = payload if isinstance(payload, list) else []
        remaining = [item for item in items if item.get("id") != announcement_id]
        if len(remaining) == len(items):
            return False
        write_json_file(self._path, remaining)
        return True
