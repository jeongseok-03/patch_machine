"""Thin ``CodeRepository`` implementation on top of :class:`RepoSnapshotService`."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from negotium.context.repo_snapshot import RepoSnapshotService
from negotium.domain.entities import RepoRef


class GitPythonRepository:
    def __init__(self, snapshot_service: RepoSnapshotService) -> None:
        self._snapshots = snapshot_service

    def snapshot(self, repo: RepoRef) -> Path:
        return self._snapshots.ensure(repo)

    def read_file(self, repo: RepoRef, relative_path: str) -> str:
        root = self.snapshot(repo)
        path = root / relative_path
        return path.read_text(encoding="utf-8")

    def list_paths(
        self,
        repo: RepoRef,
        *,
        globs: Sequence[str] | None = None,
    ) -> list[Path]:
        root = self.snapshot(repo)
        if not globs:
            return [p for p in root.rglob("*") if p.is_file()]
        result: list[Path] = []
        for pattern in globs:
            result.extend(p for p in root.rglob(pattern) if p.is_file())
        return result
