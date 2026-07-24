"""Use-case orchestrator.

Reads a ``DomainEvent`` from the bus, runs the context builder, executes the
LangGraph agent pipeline, persists the MD log and invokes notifiers.
"""

from __future__ import annotations

from dataclasses import dataclass

from negotium.agents.graph import AgentGraph, GraphState
from negotium.app.services.issue_memory_service import capture_issue_event
from negotium.application.event_bus import EventBus
from negotium.archive.issue_memory import IssueMemoryStore
from negotium.archive.operations_memory import OperationsMemoryStore
from negotium.archive.writer import ArchiveWriter
from negotium.context.md_retriever import MarkdownRetriever
from negotium.context.repo_snapshot import RepoSnapshotService
from negotium.domain.entities import IssueEvent
from negotium.domain.ports import Notifier
from negotium.observability import get_logger


@dataclass
class Orchestrator:
    """Composition of the domain pipeline. All collaborators are injected."""

    graph: AgentGraph
    repo_snapshot: RepoSnapshotService
    retriever: MarkdownRetriever
    operations_memory: OperationsMemoryStore
    archive: ArchiveWriter
    issue_memory: IssueMemoryStore
    notifiers: dict[str, Notifier]

    def __post_init__(self) -> None:
        self._log = get_logger(component="orchestrator")

    async def handle(self, event: IssueEvent) -> None:
        log = self._log.bind(event_id=str(event.event_id), source=event.source)
        log.info("orchestrator.start")
        capture = capture_issue_event(self.issue_memory, event)
        log.info(
            "orchestrator.issue_memory_captured",
            cluster_id=capture["cluster"]["id"],
            issue_id=capture["canonical_issue"]["id"],
        )

        snapshot_path = self.repo_snapshot.ensure(event.repo)
        related = self.retriever.find_related(event, limit=5)
        operations_memory_md = self.operations_memory.read().to_markdown()

        state: GraphState = {
            "issue": event,
            "snapshot_path": str(snapshot_path),
            "related_logs": [str(p) for p in related],
            "operations_memory_md": operations_memory_md,
            "workspec_md": "",
            "diff": "",
            "review_verdict": "",
            "review_md": "",
            "iteration": 0,
        }

        result = await self.graph.run(state)

        log_path = self.archive.write_from_state(event=event, state=result)
        log.info("orchestrator.log_written", path=str(log_path))

        notifier = self.notifiers.get(event.source)
        if notifier is None:
            log.warning("orchestrator.no_notifier", source=event.source)
            return

        summary = self._build_summary(result, log_path)
        await notifier.reply(event, summary)
        log.info("orchestrator.done")

    async def run_forever(self, bus: EventBus) -> None:
        async for envelope in bus.consume():
            try:
                await self.handle(envelope.payload)
            except Exception:
                self._log.exception(
                    "orchestrator.error",
                    event_id=str(envelope.payload.event_id),
                    attempt=envelope.attempt,
                )
                await bus.retry(envelope)

    @staticmethod
    def _build_summary(state: GraphState, log_path: object) -> str:
        diff = state.get("diff") or ""
        verdict = state.get("review_verdict") or "unknown"
        header = f"**Negotium 제안** — 검토 결과: `{verdict}`\n\n"
        if diff:
            header += (
                "```diff\n"
                + diff[:4000]
                + ("\n... (truncated)" if len(diff) > 4000 else "")
                + "\n```\n"
            )
        header += f"\n전체 근거: `{log_path}`"
        return header
