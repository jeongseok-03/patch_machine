"""Shared locked-file persistence helpers for archive stores.

Every file-backed store in ``negotium/archive/`` reads and writes through these
helpers instead of hand-rolling portalocker + json. JSON files hold a single
document; JSONL files are append-only record streams.

Note: this module was missing from the published repository even though five
stores import it; it is reconstructed here from the documented contract in
CLAUDE.md and the call sites in the archive stores.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import portalocker

_LOCK_TIMEOUT_SECONDS = 5


def read_json_file(path: Path, *, default: Callable[[], Any] | None = None) -> Any:
    """Read a JSON document, returning ``default()`` (or ``None``) when absent."""

    if not path.exists():
        return default() if default is not None else None
    with portalocker.Lock(str(path), "r", encoding="utf-8", timeout=_LOCK_TIMEOUT_SECONDS) as fh:
        content = fh.read()
    if not content.strip():
        return default() if default is not None else None
    return json.loads(content)


def write_json_file(path: Path, payload: Any) -> None:
    """Write a JSON document under an exclusive lock, creating parent dirs."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with portalocker.Lock(str(path), "w", encoding="utf-8", timeout=_LOCK_TIMEOUT_SECONDS) as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def append_jsonl_line(path: Path, record: dict[str, Any], *, sort_keys: bool = False) -> None:
    """Append one JSON record as a line to an append-only JSONL file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=sort_keys)
    with portalocker.Lock(str(path), "a", encoding="utf-8", timeout=_LOCK_TIMEOUT_SECONDS) as fh:
        fh.write(line + "\n")


def iter_jsonl_records(path: Path) -> Iterator[dict[str, Any]]:
    """Yield JSONL records in file order, skipping blank or corrupt lines."""

    if not path.exists():
        return
    with portalocker.Lock(str(path), "r", encoding="utf-8", timeout=_LOCK_TIMEOUT_SECONDS) as fh:
        lines = fh.readlines()
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            yield payload
