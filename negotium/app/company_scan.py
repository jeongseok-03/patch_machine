"""Company filesystem scan for auto-discovery onboarding.

The setup wizard lets an admin point Negotium at company folders, mark paths
that must never be read, and have the LLM infer the company profile from what
remains. The scan is whitelist-first: only well-known document extensions are
parsed, and everything else is inventoried as skipped with a reason. The user
blocklist narrows the scan further; it never widens it.

Nothing in this module calls an LLM — it only builds a bounded, auditable
inventory plus parsed text blocks for the existing analyze → review → apply
pipeline in the setup API.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from negotium.app.initial_setup import ParsedSetupFile, parse_setup_file

SCAN_ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".md", ".txt", ".csv", ".tsv", ".xlsx", ".json"}
)

DEFAULT_EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    name.lower()
    for name in (
        ".git",
        ".svn",
        ".hg",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".idea",
        ".vscode",
        ".ssh",
        ".aws",
        ".gnupg",
        ".docker",
        "appdata",
        "$recycle.bin",
        "system volume information",
        "windows",
        "program files",
        "program files (x86)",
        "programdata",
    )
)

DEFAULT_EXCLUDED_FILE_GLOBS: tuple[str, ...] = (
    ".env*",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "*.crt",
    "id_rsa*",
    "id_ed25519*",
    "*.kdbx",
    "*password*",
    "*passwd*",
    "*secret*",
    "credentials*",
    "*.token",
)

DEFAULT_MAX_FILE_BYTES = 2_000_000
DEFAULT_MAX_FILES = 400
DEFAULT_MAX_TOTAL_BYTES = 40_000_000
DEFAULT_MAX_DEPTH = 12
MAX_INVENTORY_ENTRIES = 2_000

_PRIORITY_NAME_KEYWORDS = (
    "readme",
    "소개",
    "회사",
    "조직",
    "규정",
    "정책",
    "업무",
    "매뉴얼",
    "manual",
    "onboarding",
    "인수인계",
    "overview",
    "company",
    "org",
    "process",
    "가이드",
    "guide",
)


@dataclass(frozen=True)
class ScanConfig:
    """User-supplied scan request plus safety caps."""

    root_paths: list[str]
    excluded_paths: list[str] = field(default_factory=list)
    max_files: int = DEFAULT_MAX_FILES
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    max_depth: int = DEFAULT_MAX_DEPTH


@dataclass(frozen=True)
class ScannedFile:
    path: str
    size: int
    extension: str
    included: bool
    skip_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "size": self.size,
            "extension": self.extension,
            "included": self.included,
            "skip_reason": self.skip_reason,
        }


@dataclass(frozen=True)
class ScanReport:
    roots: list[str]
    missing_roots: list[str]
    files: list[ScannedFile]
    included_count: int
    skipped_counts: dict[str, int]
    total_bytes: int
    truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "roots": self.roots,
            "missing_roots": self.missing_roots,
            "files": [item.to_dict() for item in self.files],
            "included_count": self.included_count,
            "skipped_counts": self.skipped_counts,
            "total_bytes": self.total_bytes,
            "truncated": self.truncated,
        }


def normalize_scan_path(raw: str) -> str:
    """Accept Windows-style paths (``C:\\Users\\...``) on a WSL/Linux backend."""

    text = raw.strip().strip('"')
    if not text:
        return ""
    if len(text) >= 3 and text[1] == ":" and text[2] in {"\\", "/"} and text[0].isalpha():
        drive = text[0].lower()
        rest = text[3:].replace("\\", "/")
        candidate = f"/mnt/{drive}/{rest}".rstrip("/")
        if Path(candidate).exists() or not Path(text).exists():
            return candidate
    return text.replace("\\", "/")


def scan_company_paths(config: ScanConfig) -> ScanReport:
    """Walk the requested roots and build a bounded inventory.

    Symlinks are never followed, default-sensitive directories/files are always
    skipped, and only whitelisted document extensions count as included.
    """

    roots: list[str] = []
    missing: list[str] = []
    for raw in config.root_paths:
        normalized = normalize_scan_path(raw)
        if not normalized:
            continue
        path = Path(normalized)
        if path.exists():
            roots.append(str(path))
        else:
            missing.append(raw)

    user_excludes = [normalize_scan_path(item) for item in config.excluded_paths]
    user_excludes = [item for item in user_excludes if item]

    files: list[ScannedFile] = []
    skipped_counts: dict[str, int] = {}
    included_count = 0
    total_bytes = 0
    truncated = False

    def note_skip(path: str, size: int, extension: str, reason: str) -> None:
        skipped_counts[reason] = skipped_counts.get(reason, 0) + 1
        if len(files) < MAX_INVENTORY_ENTRIES:
            files.append(
                ScannedFile(
                    path=path, size=size, extension=extension, included=False, skip_reason=reason
                )
            )

    for root in roots:
        root_path = Path(root)
        if root_path.is_file():
            candidates: list[tuple[Path, int]] = [(root_path, 0)]
        else:
            candidates = []
            base_depth = len(root_path.parts)
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                current = Path(dirpath)
                depth = len(current.parts) - base_depth
                if depth >= config.max_depth:
                    dirnames[:] = []
                    continue
                dirnames[:] = sorted(
                    name
                    for name in dirnames
                    if name.lower() not in DEFAULT_EXCLUDED_DIR_NAMES
                    and not name.startswith(".")
                    and not _matches_user_exclude(str(current / name), name, user_excludes)
                    and not (current / name).is_symlink()
                )
                for filename in sorted(filenames):
                    candidates.append((current / filename, depth))

        for file_path, _depth in candidates:
            if truncated:
                break
            posix = str(file_path)
            name = file_path.name
            extension = file_path.suffix.lower()
            if file_path.is_symlink():
                note_skip(posix, 0, extension, "symlink")
                continue
            if _matches_user_exclude(posix, name, user_excludes):
                note_skip(posix, 0, extension, "user_excluded")
                continue
            if _matches_default_file_glob(name):
                note_skip(posix, 0, extension, "sensitive_name")
                continue
            if extension not in SCAN_ALLOWED_EXTENSIONS:
                note_skip(posix, 0, extension, "extension_not_allowed")
                continue
            try:
                size = file_path.stat().st_size
            except OSError:
                note_skip(posix, 0, extension, "unreadable")
                continue
            if size > config.max_file_bytes:
                note_skip(posix, size, extension, "too_large")
                continue
            if included_count >= config.max_files or total_bytes + size > config.max_total_bytes:
                truncated = True
                break
            included_count += 1
            total_bytes += size
            if len(files) < MAX_INVENTORY_ENTRIES:
                files.append(ScannedFile(path=posix, size=size, extension=extension, included=True))

    return ScanReport(
        roots=roots,
        missing_roots=missing,
        files=files,
        included_count=included_count,
        skipped_counts=skipped_counts,
        total_bytes=total_bytes,
        truncated=truncated,
    )


def parse_scanned_files(
    report: ScanReport,
    *,
    max_files: int = 40,
    max_total_chars: int = 48_000,
) -> list[ParsedSetupFile]:
    """Parse the most representative included files within an LLM-sized budget.

    Files whose names look like company-level documentation rank first; shallow
    paths beat deep ones so the digest describes the company, not one project.
    """

    included = [item for item in report.files if item.included]
    ranked = sorted(included, key=_selection_rank)
    parsed: list[ParsedSetupFile] = []
    used_chars = 0
    for item in ranked:
        if len(parsed) >= max_files or used_chars >= max_total_chars:
            break
        path = Path(item.path)
        if not path.is_file():
            continue
        try:
            entry = parse_setup_file(path)
        except (OSError, ValueError, RuntimeError):
            continue
        remaining = max_total_chars - used_chars
        if len(entry.text) > remaining:
            entry = replace(entry, text=entry.text[:remaining])
        used_chars += len(entry.text)
        parsed.append(entry)
    return parsed


def _selection_rank(item: ScannedFile) -> tuple[int, int, int]:
    name = Path(item.path).name.lower()
    priority = 0 if any(keyword in name for keyword in _PRIORITY_NAME_KEYWORDS) else 1
    depth = len(Path(item.path).parts)
    return (priority, depth, -item.size)


def _matches_user_exclude(posix_path: str, name: str, patterns: list[str]) -> bool:
    lowered = posix_path.lower().rstrip("/")
    for pattern in patterns:
        candidate = pattern.lower().rstrip("/")
        if not candidate:
            continue
        if lowered == candidate or lowered.startswith(candidate + "/"):
            return True
        if fnmatch.fnmatch(lowered, candidate) or fnmatch.fnmatch(name.lower(), candidate):
            return True
    return False


def _matches_default_file_glob(name: str) -> bool:
    lowered = name.lower()
    return any(fnmatch.fnmatch(lowered, pattern) for pattern in DEFAULT_EXCLUDED_FILE_GLOBS)
