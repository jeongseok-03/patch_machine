"""Archive-backed uploaded office documents."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import portalocker


@dataclass(frozen=True)
class UploadRecord:
    id: str
    filename: str
    path: str
    description: str = ""
    tags: str = ""
    work_title: str = ""
    uploaded_at: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "filename": self.filename,
            "path": self.path,
            "description": self.description,
            "tags": self.tags,
            "work_title": self.work_title,
            "uploaded_at": self.uploaded_at,
        }


class UploadStore:
    def __init__(self, archive_dir: Path) -> None:
        self._archive_dir = archive_dir
        self._root = archive_dir / "uploads"
        self._index = self._root / "index.json"

    def list(self) -> list[dict[str, str]]:
        return [record.to_dict() for record in self._read_index()]

    def save(
        self,
        *,
        filename: str,
        source: BinaryIO,
        description: str = "",
        tags: str = "",
        work_title: str = "",
    ) -> UploadRecord:
        created = datetime.now(UTC)
        upload_id = str(uuid4())
        safe = _safe_filename(filename)
        relative = Path("uploads") / created.strftime("%Y/%m/%d") / f"{upload_id}_{safe}"
        target = self._archive_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as fh:
            shutil.copyfileobj(source, fh)
        record = UploadRecord(
            id=upload_id,
            filename=safe,
            path=relative.as_posix(),
            description=description,
            tags=tags,
            work_title=work_title,
            uploaded_at=created.isoformat(),
        )
        records = [existing for existing in self._read_index() if existing.id != upload_id]
        records.insert(0, record)
        self._write_index(records)
        return record

    def delete(self, upload_id: str) -> bool:
        records = self._read_index()
        target = next((record for record in records if record.id == upload_id), None)
        if target is None:
            return False
        path = self._archive_dir / target.path
        if path.exists() and path.is_file():
            path.unlink()
        self._write_index([record for record in records if record.id != upload_id])
        return True

    def _read_index(self) -> list[UploadRecord]:
        if not self._index.exists():
            return []
        raw = json.loads(self._index.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [UploadRecord(**item) for item in raw if isinstance(item, dict)]

    def _write_index(self, records: list[UploadRecord]) -> None:
        self._index.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(self._index, "w", encoding="utf-8", timeout=5) as fh:
            json.dump([record.to_dict() for record in records], fh, ensure_ascii=False, indent=2)
            fh.write("\n")


def _safe_filename(filename: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in filename)
    return cleaned.strip("._")[:120] or "upload.bin"
