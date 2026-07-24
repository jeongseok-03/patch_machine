"""Utilities for resetting local Negotium state."""

from __future__ import annotations

import shutil
from pathlib import Path

from negotium.archive.audit_log import AuditLogStore


def reset_system_state(
    *,
    archive_dir: Path,
    workspace_dir: Path,
    actor: str = "cli",
    include_workspaces: bool = True,
) -> dict[str, object]:
    """Clear persisted local state and leave a reset audit marker.

    This intentionally does not touch source code, `.env`, Docker volumes outside
    the configured paths, or provider-side model caches.
    """

    archive_dir = archive_dir.resolve()
    workspace_dir = workspace_dir.resolve()
    _ensure_safe_path(archive_dir)
    if include_workspaces:
        _ensure_safe_path(workspace_dir)

    removed = _clear_directory(archive_dir)
    workspace_removed: list[str] = []
    if include_workspaces:
        workspace_removed = _clear_directory(workspace_dir)

    audit = AuditLogStore(archive_dir)
    audit.record(
        actor=actor,
        action="system.reset",
        target="system_state",
        details={
            "archive_dir": str(archive_dir),
            "workspace_dir": str(workspace_dir),
            "include_workspaces": include_workspaces,
            "removed": removed,
            "workspace_removed": workspace_removed,
        },
    )
    return {
        "archive_dir": str(archive_dir),
        "workspace_dir": str(workspace_dir),
        "include_workspaces": include_workspaces,
        "removed": removed,
        "workspace_removed": workspace_removed,
        "audit_log": str(audit.path),
    }


def _clear_directory(path: Path) -> list[str]:
    path.mkdir(parents=True, exist_ok=True)
    removed: list[str] = []
    for child in path.iterdir():
        removed.append(child.name)
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    return removed


def _ensure_safe_path(path: Path) -> None:
    if path in {Path("/"), Path.home()}:
        raise ValueError(f"refusing to reset unsafe path: {path}")
    if len(path.parts) < 3:
        raise ValueError(f"refusing to reset broad path: {path}")
