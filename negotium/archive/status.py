"""Rolling ``current_status.md`` manager (the "volatile" task buffer)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import portalocker

from negotium.observability import get_logger

_FILE_NAME: Final = "current_status.md"
_HEADER: Final = "# Negotium — current_status\n\n"


class StatusManager:
    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / _FILE_NAME
        self._log = get_logger(component="archive.status")
        if not self._path.exists():
            self._path.write_text(_HEADER, encoding="utf-8")

    @property
    def path(self) -> Path:
        return self._path

    def overwrite(self, summary_md: str) -> None:
        ts = datetime.now(UTC).isoformat()
        body = f"{_HEADER}_업데이트: {ts}_\n\n{summary_md.strip()}\n"
        with portalocker.Lock(self._path, "w", encoding="utf-8", timeout=5) as fh:
            fh.write(body)
        self._log.info("archive.status.overwrite", bytes=len(body))

    def read(self) -> str:
        return self._path.read_text(encoding="utf-8")
