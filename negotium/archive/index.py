"""Index-MD manager.

The retriever uses index files as a fast first-pass filter. We store them as
plain MD so non-technical operators can read, audit or even hand-edit them.

Format (stable, append-only entries per key):

```
# by_keyword.md
- auth: [2026/04/12_github_42_proposed.md, 2026/03/28_discord_18_merged.md]
```

Each write acquires an exclusive lock via ``portalocker`` so concurrent
orchestrator tasks cannot corrupt the file. The update strategy is read-merge-
write to keep the file deterministic and human-diffable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Final

import portalocker

from negotium.observability import get_logger

_LINE_RE = re.compile(r"^-\s+(?P<key>[^:]+?):\s*\[(?P<items>.*)\]\s*$", re.MULTILINE)
_BY_KEYWORD: Final = "by_keyword.md"
_BY_MODULE: Final = "by_module.md"
_BY_AUTHOR: Final = "by_author.md"


class IndexManager:
    def __init__(self, index_dir: Path, *, archive_root: Path | None = None) -> None:
        self._dir = index_dir
        self._archive_root = archive_root or index_dir.parent
        self._dir.mkdir(parents=True, exist_ok=True)
        self._log = get_logger(component="archive.index")
        for name in (_BY_KEYWORD, _BY_MODULE, _BY_AUTHOR):
            path = self._dir / name
            if not path.exists():
                path.write_text(f"# {name}\n", encoding="utf-8")

    def update(
        self,
        *,
        log_path: Path,
        keywords: Iterable[str],
        modules: Iterable[str],
        author: str,
    ) -> None:
        relative = self._relative_log_path(log_path)
        self._append_to(_BY_KEYWORD, keys=keywords, value=relative)
        self._append_to(_BY_MODULE, keys=modules, value=relative)
        self._append_to(_BY_AUTHOR, keys=[author], value=relative)

    def lookup(self, file_name: str, key: str) -> list[str]:
        """Return log paths indexed under ``key`` in the given index file."""
        path = self._dir / file_name
        if not path.exists():
            return []
        content = path.read_text(encoding="utf-8")
        for match in _LINE_RE.finditer(content):
            if match.group("key").strip() == key.strip():
                raw = match.group("items").strip()
                if not raw:
                    return []
                return [item.strip() for item in raw.split(",") if item.strip()]
        return []

    def lookup_many(self, file_name: str, keys: Iterable[str]) -> list[str]:
        seen: dict[str, None] = {}
        for key in keys:
            for entry in self.lookup(file_name, key):
                seen.setdefault(entry, None)
        return list(seen.keys())

    @property
    def by_keyword(self) -> Path:
        return self._dir / _BY_KEYWORD

    @property
    def by_module(self) -> Path:
        return self._dir / _BY_MODULE

    @property
    def by_author(self) -> Path:
        return self._dir / _BY_AUTHOR

    def _append_to(self, file_name: str, *, keys: Iterable[str], value: str) -> None:
        keys = [k.strip().lower() for k in keys if k and k.strip()]
        if not keys:
            return
        path = self._dir / file_name
        with portalocker.Lock(path, "r+", encoding="utf-8", timeout=5) as fh:
            content = fh.read()
            updated = self._merge(content, keys=keys, value=value, file_name=file_name)
            fh.seek(0)
            fh.truncate()
            fh.write(updated)
        self._log.info(
            "archive.index.update",
            file=file_name,
            keys=keys,
            value=value,
        )

    @staticmethod
    def _merge(content: str, *, keys: list[str], value: str, file_name: str) -> str:
        lines = content.splitlines()
        header: list[str] = []
        entries: dict[str, list[str]] = {}
        for line in lines:
            match = _LINE_RE.match(line)
            if match:
                key = match.group("key").strip().lower()
                items_raw = match.group("items").strip()
                items = [item.strip() for item in items_raw.split(",") if item.strip()]
                entries[key] = items
            elif line.strip():
                header.append(line)
        if not header:
            header = [f"# {file_name}"]
        for key in keys:
            bucket = entries.setdefault(key, [])
            if value not in bucket:
                bucket.append(value)
        rebuilt = (
            list(header)
            + [""]
            + [f"- {key}: [{', '.join(items)}]" for key, items in sorted(entries.items())]
        )
        return "\n".join(rebuilt) + "\n"

    def _relative_log_path(self, log_path: Path) -> str:
        try:
            return log_path.resolve().relative_to(self._archive_root.resolve()).as_posix()
        except ValueError:
            parts = list(log_path.parts)
            for anchor in ("archive", "logs"):
                if anchor in parts:
                    idx = parts.index(anchor)
                    return "/".join(parts[idx + 1 :])
            return log_path.name
