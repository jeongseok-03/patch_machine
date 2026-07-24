"""Archive writer: persists the per-event MD log and updates indexes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import portalocker

from negotium.archive.index import IndexManager
from negotium.archive.schema import LogFrontMatter, render_log_markdown
from negotium.archive.status import StatusManager
from negotium.domain.entities import IssueEvent
from negotium.observability import get_logger


class ArchiveWriter:
    """Coordinates log file, indexes and rolling status updates.

    The writer is the **single consumer** of the archive filesystem so we can
    rely on portalocker + serial writes rather than a full database.
    """

    def __init__(self, archive_dir: Path) -> None:
        self._dir = archive_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index = IndexManager(self._dir / "index", archive_root=self._dir)
        self._status = StatusManager(self._dir)
        self._log = get_logger(component="archive.writer")

    @property
    def index(self) -> IndexManager:
        return self._index

    @property
    def status(self) -> StatusManager:
        return self._status

    def write_log(
        self,
        *,
        issue: IssueEvent,
        status: str,
        iteration: int,
        llm_route: str,
        modules: list[str],
        keywords: list[str],
        context_md: str,
        retrieved_md: str,
        thought_process_md: str,
        patch_diff: str,
    ) -> Path:
        created = datetime.now(UTC)
        fm = LogFrontMatter(
            event_id=str(issue.event_id),
            source=issue.source,
            external_id=str(issue.external_id),
            repo=issue.repo.full_name,
            status=status,
            modules=modules,
            keywords=keywords,
            iteration=iteration,
            created=created,
            llm_route=llm_route,
        )
        rendered = render_log_markdown(
            front_matter=fm,
            context_md=context_md,
            retrieved_md=retrieved_md,
            thought_process_md=thought_process_md,
            patch_diff=patch_diff,
        )
        relative_path = self._build_log_path(created=created, issue=issue, status=status)
        log_path = self._dir / relative_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(log_path, "w", encoding="utf-8", timeout=5) as fh:
            fh.write(rendered)
        self._index.update(
            log_path=log_path,
            keywords=keywords,
            modules=modules,
            author=issue.author,
        )
        self._log.info("archive.writer.log", path=str(log_path), status=status)
        return log_path

    def write_from_state(
        self,
        *,
        event: IssueEvent,
        state: Mapping[str, Any],
    ) -> Path:
        """Convenience method consumed by the orchestrator.

        Extracts the canonical fields from an agent ``GraphState`` dict.
        """
        modules: list[str] = list(state.get("target_modules", []))
        keywords = self._extract_keywords(event, modules)
        status = self._map_verdict_to_status(str(state.get("review_verdict", "")))
        thought = _format_thought_process(
            workspec_md=str(state.get("workspec_md", "")),
            developer_md=str(state.get("developer_md", "")),
            reviewer_md=str(state.get("review_md", "")),
        )
        context_md = str(state.get("context_md", "")).strip()
        retrieved_md = _format_related_logs(state.get("related_logs", []))
        return self.write_log(
            issue=event,
            status=status,
            iteration=int(state.get("iteration", 1) or 1),
            llm_route=str(state.get("llm_route", "cloud")),
            modules=modules,
            keywords=keywords,
            context_md=context_md,
            retrieved_md=retrieved_md,
            thought_process_md=thought,
            patch_diff=str(state.get("diff", "")),
        )

    def refresh_status(self, *, recent_limit: int = 5) -> None:
        recent_paths = self._collect_recent_logs(recent_limit)
        lines = ["## 최근 처리 이슈"]
        if not recent_paths:
            lines.append("- (아직 처리된 이슈가 없습니다)")
        else:
            for path in recent_paths:
                lines.append(f"- `{path.as_posix()}`")
        self._status.overwrite("\n".join(lines))

    def _collect_recent_logs(self, limit: int) -> list[Path]:
        candidates = [p for p in self._dir.rglob("*.md") if self._is_log(p)]
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[:limit]

    def _is_log(self, path: Path) -> bool:
        try:
            parts = path.relative_to(self._dir).parts
        except ValueError:
            return False
        if len(parts) < 3:
            return False
        if parts[0] in {"index", "knowledge_base"}:
            return False
        return parts[0].isdigit() and parts[1].isdigit()

    @staticmethod
    def _build_log_path(*, created: datetime, issue: IssueEvent, status: str) -> Path:
        return (
            Path(f"{created.year:04d}")
            / f"{created.month:02d}"
            / f"{created.day:02d}_{issue.source}_{issue.external_id}_{status}.md"
        )

    @staticmethod
    def _map_verdict_to_status(verdict: str) -> str:
        mapping = {
            "approve": "proposed",
            "needs_fix": "exhausted",
            "reject": "rejected",
            "": "proposed",
        }
        return mapping.get(verdict, verdict or "proposed")

    @staticmethod
    def _extract_keywords(event: IssueEvent, modules: Iterable[str]) -> list[str]:
        """Very small keyword extractor — lowercase labels + module names + first CAPS words."""
        seen: dict[str, None] = {}
        for raw in list(event.labels) + list(modules):
            if raw:
                seen.setdefault(raw.strip().lower(), None)
        for token in event.title.split():
            cleaned = token.strip(".,;:!?\"'`()[]{}<>").lower()
            if cleaned.isalpha() and len(cleaned) > 3:
                seen.setdefault(cleaned, None)
            if len(seen) >= 10:
                break
        return list(seen.keys())


def _format_related_logs(entries: Any) -> str:
    if not entries:
        return "- (유사 과거 로그 없음)"
    lines: list[str] = []
    for entry in entries:
        lines.append(f"- `{entry}`")
    return "\n".join(lines)


def _format_thought_process(
    *,
    workspec_md: str,
    developer_md: str,
    reviewer_md: str,
) -> str:
    sections = [
        ("### PM", workspec_md),
        ("### Developer", developer_md),
        ("### Reviewer", reviewer_md),
    ]
    return "\n\n".join(f"{header}\n{body.strip() or '_(내용 없음)_'}" for header, body in sections)


def write_through_lock(path: Path, content: str) -> None:
    """Exposed helper in case other modules need a synchronized overwrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with portalocker.Lock(path, "w", encoding="utf-8", timeout=5) as fh:
        fh.write(content)
