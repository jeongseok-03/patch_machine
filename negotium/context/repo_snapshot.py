"""Shallow clone + fast-forward pull for the repository snapshot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from negotium.domain.entities import RepoRef
from negotium.observability import get_logger


class RepoSnapshotService:
    """Keeps a working copy of every allowed repository under ``root``.

    For Phase 1 we do a shallow clone (``depth=1``) and pull the default
    branch. Authentication is handled via the ambient git config / HTTPS
    PAT, which makes this trivially swappable with SSH or GitHub App tokens.
    """

    def __init__(self, root: Path, *, git: Any | None = None) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._log = get_logger(component="context.repo_snapshot")
        self._git = git

    def ensure(self, repo: RepoRef) -> Path:
        target = self._root / f"{repo.owner}__{repo.name}"
        if target.exists():
            self._pull(target, repo)
        else:
            self._clone(target, repo)
        return target

    def _clone(self, target: Path, repo: RepoRef) -> None:
        self._log.info("repo_snapshot.clone", repo=repo.full_name, target=str(target))
        git_module = self._resolve_git()
        if git_module is None:  # test / offline path
            target.mkdir(parents=True, exist_ok=True)
            return
        git_module.Repo.clone_from(
            f"https://github.com/{repo.full_name}.git",
            target,
            depth=1,
            branch=repo.default_branch,
        )

    def _pull(self, target: Path, repo: RepoRef) -> None:
        git_module = self._resolve_git()
        if git_module is None:
            return
        try:
            repo_obj = git_module.Repo(target)
            repo_obj.remotes.origin.fetch(depth=1)
            repo_obj.git.reset("--hard", f"origin/{repo.default_branch}")
            self._log.info("repo_snapshot.pull", repo=repo.full_name)
        except Exception:
            self._log.exception("repo_snapshot.pull.failed", repo=repo.full_name)

    def _resolve_git(self) -> Any | None:
        if self._git is not None:
            return self._git
        try:
            import git
        except Exception:  # pragma: no cover - import-time guard
            self._log.warning("repo_snapshot.git_unavailable")
            return None
        return git
