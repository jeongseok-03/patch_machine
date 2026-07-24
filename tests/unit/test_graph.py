"""End-to-end agent graph state transitions with a scripted LLM."""

from __future__ import annotations

from negotium.adapters.llm.fake_adapter import FakeLlmProvider, ScriptedResponse
from negotium.agents.developer import DeveloperAgent
from negotium.agents.graph import AgentGraph, GraphState
from negotium.agents.pm import PmAgent
from negotium.agents.reviewer import ReviewerAgent
from negotium.domain.entities import IssueEvent, RepoRef

_PM_OUTPUT = """MODULES: refund, webhook
RATIONALE:
환불 API 가 idempotency 키를 재사용합니다.
PLAN:
1. 키 재사용 방지
"""

_DEV_OUTPUT = """THOUGHT:
refund 모듈의 키 생성 로직 교체
DIFF:
--- a/refund.py
+++ b/refund.py
@@
-def refund(tx):
-    key = tx.id
+def refund(tx):
+    key = f"{tx.id}-{uuid4()}"
"""

_REVIEW_APPROVE = """VERDICT: approve
FINDINGS:
문제 없음
SUGGESTED_FIX:
"""


def _make_graph(responses: list[ScriptedResponse]) -> tuple[AgentGraph, FakeLlmProvider]:
    llm = FakeLlmProvider(responses=responses)
    pm = PmAgent(llm)
    dev = DeveloperAgent(llm)
    rev = ReviewerAgent(llm)
    graph = AgentGraph(pm=pm, developer=dev, reviewer=rev, max_iterations=2)
    return graph, llm


def _issue() -> IssueEvent:
    return IssueEvent(
        source="github",
        external_id="42",
        repo=RepoRef(owner="acme", name="payments"),
        title="double refund",
        body="refund duplicated",
        author="alice",
        labels=["bug", "negotium"],
    )


async def test_happy_path_produces_diff_and_approval() -> None:
    graph, llm = _make_graph(
        [
            ScriptedResponse(text=_PM_OUTPUT, tag="pm"),
            ScriptedResponse(text=_DEV_OUTPUT, tag="developer"),
            ScriptedResponse(text=_REVIEW_APPROVE, tag="reviewer"),
        ]
    )
    state: GraphState = {
        "issue": _issue(),
        "ast_summary": "",
        "related_logs": [],
        "operations_memory_md": "## 운영 메모리\n- 회사 이름: Acme Retail",
    }
    result = await graph.run(state)
    assert result["review_verdict"] == "approve"
    assert result["target_modules"] == ["refund", "webhook"]
    assert "refund.py" in result["diff"]
    assert any("Acme Retail" in message.content for call in llm.calls for message in call)


async def test_self_correction_exhausts_then_rejects() -> None:
    needs_fix = """VERDICT: needs_fix
FINDINGS:
테스트 없음
SUGGESTED_FIX:
유닛 테스트 추가
"""
    graph, _ = _make_graph(
        [
            ScriptedResponse(text=_PM_OUTPUT, tag="pm"),
            ScriptedResponse(text=_DEV_OUTPUT, tag="developer"),
            ScriptedResponse(text=needs_fix, tag="reviewer"),
            ScriptedResponse(text=_DEV_OUTPUT, tag="developer"),
            ScriptedResponse(text=needs_fix, tag="reviewer"),
        ]
    )
    state: GraphState = {
        "issue": _issue(),
        "ast_summary": "",
        "related_logs": [],
    }
    result = await graph.run(state)
    assert result["iteration"] == 2
    assert result["review_verdict"] in {"needs_fix", "reject"}
