"""LangGraph StateGraph wiring for PM → Developer → Reviewer with self-correction.

The graph is intentionally thin: each node delegates to an Agent class. When
``langgraph`` is unavailable (e.g. minimal test env) we fall back to a manual
async loop that replicates the semantics so unit tests still run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from negotium.agents.developer import DeveloperAgent
from negotium.agents.pm import PmAgent
from negotium.agents.reviewer import ReviewerAgent
from negotium.domain.entities import IssueEvent
from negotium.observability import get_logger


class GraphState(TypedDict, total=False):
    """Mutable state threaded through the agent graph."""

    issue: IssueEvent
    snapshot_path: str
    related_logs: list[str]
    operations_memory_md: str
    ast_summary: str
    context_md: str
    workspec_md: str
    target_modules: list[str]
    developer_md: str
    diff: str
    review_md: str
    review_verdict: str
    suggested_fix_md: str
    iteration: int
    llm_route: str


@dataclass
class AgentGraph:
    pm: PmAgent
    developer: DeveloperAgent
    reviewer: ReviewerAgent
    max_iterations: int = 2

    def __post_init__(self) -> None:
        self._log = get_logger(component="agents.graph")
        self._compiled = self._try_compile_langgraph()

    async def run(self, state: GraphState) -> GraphState:
        if self._compiled is not None:
            return await self._run_langgraph(state)
        return await self._run_manual(state)

    async def _run_langgraph(self, state: GraphState) -> GraphState:
        assert self._compiled is not None  # guarded by caller
        result: GraphState = await self._compiled.ainvoke(state)
        return result

    async def _run_manual(self, state: GraphState) -> GraphState:
        state = await self._node_pm(state)
        while True:
            state = await self._node_developer(state)
            state = await self._node_reviewer(state)
            if state.get("review_verdict") != "needs_fix":
                break
            if int(state.get("iteration", 0)) >= self.max_iterations:
                state["review_verdict"] = "reject"
                self._log.warning(
                    "graph.exhausted",
                    iterations=state.get("iteration"),
                )
                break
        return state

    async def _node_pm(self, state: GraphState) -> GraphState:
        issue = state["issue"]
        pm_output = await self.pm.run(
            issue=issue,
            ast_summary=state.get("ast_summary", ""),
            related_logs=list(state.get("related_logs", [])),
            operations_memory_md=state.get("operations_memory_md", ""),
        )
        state["target_modules"] = pm_output.modules
        state["workspec_md"] = pm_output.rationale_md
        state["iteration"] = 0
        return state

    async def _node_developer(self, state: GraphState) -> GraphState:
        dev_output = await self.developer.run(
            workspec_md=state.get("workspec_md", ""),
            ast_summary=state.get("ast_summary", ""),
            operations_memory_md=state.get("operations_memory_md", ""),
            previous_review=state.get("suggested_fix_md") or None,
        )
        state["developer_md"] = dev_output.thought_md
        state["diff"] = dev_output.unified_diff
        state["iteration"] = int(state.get("iteration", 0)) + 1
        return state

    async def _node_reviewer(self, state: GraphState) -> GraphState:
        rv = await self.reviewer.run(
            workspec_md=state.get("workspec_md", ""),
            operations_memory_md=state.get("operations_memory_md", ""),
            diff=state.get("diff", ""),
        )
        state["review_verdict"] = rv.verdict
        state["review_md"] = rv.findings_md
        state["suggested_fix_md"] = rv.suggested_fix_md
        return state

    def _try_compile_langgraph(self) -> Any | None:
        try:
            from langgraph.graph import END, StateGraph
        except Exception:
            self._log.info("graph.langgraph_unavailable", fallback="manual")
            return None
        builder: Any = StateGraph(GraphState)
        builder.add_node("pm", self._node_pm)
        builder.add_node("developer", self._node_developer)
        builder.add_node("reviewer", self._node_reviewer)
        builder.set_entry_point("pm")
        builder.add_edge("pm", "developer")
        builder.add_edge("developer", "reviewer")

        def _route(state: GraphState) -> str:
            verdict = state.get("review_verdict")
            if verdict == "needs_fix" and int(state.get("iteration", 0)) < self.max_iterations:
                return "developer"
            return END

        builder.add_conditional_edges("reviewer", _route, {"developer": "developer", END: END})
        return builder.compile()
