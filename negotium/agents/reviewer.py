"""Reviewer agent: approves, requests a fix, or rejects the diff."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from negotium.domain.entities import ReviewOutcome
from negotium.domain.ports import LlmMessage, LlmProvider
from negotium.observability import AgentMetrics, get_logger
from negotium.prompts import render


@dataclass
class ReviewerOutput:
    verdict: ReviewOutcome
    findings_md: str
    suggested_fix_md: str


_VERDICT_RE = re.compile(
    r"^VERDICT:\s*(?P<value>approve|needs_fix|reject)", re.MULTILINE | re.IGNORECASE
)
_FINDINGS_RE = re.compile(
    r"^FINDINGS:\s*(?P<value>.*?)(?=^SUGGESTED_FIX:|\Z)", re.MULTILINE | re.DOTALL
)
_FIX_RE = re.compile(r"^SUGGESTED_FIX:\s*(?P<value>.*)$", re.MULTILINE | re.DOTALL)


class ReviewerAgent:
    name = "reviewer"

    def __init__(
        self,
        llm: LlmProvider,
        *,
        metrics: AgentMetrics | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._llm = llm
        self._metrics = metrics
        self._log = get_logger(component="agents.reviewer")
        self._system_prompt = (
            system_prompt
            or "당신은 보수적인 시니어 리뷰어입니다. 버그/보안/호환성 관점에서 diff 를 검토합니다."
        )

    async def run(
        self,
        *,
        workspec_md: str,
        operations_memory_md: str = "",
        diff: str,
    ) -> ReviewerOutput:
        prompt = render(
            "reviewer.md",
            workspec_md=workspec_md,
            operations_memory_md=operations_memory_md or "_(운영 메모리 없음)_",
            diff=diff,
        )
        messages = [
            LlmMessage("system", self._system_prompt),
            LlmMessage("user", prompt),
        ]
        started = time.perf_counter()
        response = await self._llm.complete(messages, temperature=0.0)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if self._metrics is not None:
            self._metrics.record(
                agent=self.name,
                route=response.route,
                tokens_in=response.prompt_tokens,
                tokens_out=response.completion_tokens,
                latency_ms=latency_ms,
            )
        output = self._parse(response.text)
        self._log.info("reviewer.done", verdict=output.verdict, latency_ms=latency_ms)
        return output

    @staticmethod
    def _parse(text: str) -> ReviewerOutput:
        verdict_match = _VERDICT_RE.search(text)
        verdict: ReviewOutcome = "reject"
        if verdict_match:
            raw = verdict_match.group("value").lower()
            if raw in ("approve", "needs_fix", "reject"):
                verdict = raw  # type: ignore[assignment]
        findings_match = _FINDINGS_RE.search(text)
        fix_match = _FIX_RE.search(text)
        findings = findings_match.group("value").strip() if findings_match else ""
        fix = fix_match.group("value").strip() if fix_match else ""
        return ReviewerOutput(verdict=verdict, findings_md=findings, suggested_fix_md=fix)
