"""Developer agent: turns a work spec into a unified diff."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from negotium.domain.ports import LlmMessage, LlmProvider
from negotium.observability import AgentMetrics, get_logger
from negotium.prompts import render


@dataclass
class DeveloperOutput:
    thought_md: str
    unified_diff: str


_THOUGHT_RE = re.compile(r"^THOUGHT:\s*(?P<value>.*?)(?=^DIFF:)", re.MULTILINE | re.DOTALL)
_DIFF_RE = re.compile(r"^DIFF:\s*(?P<value>.*)$", re.MULTILINE | re.DOTALL)


class DeveloperAgent:
    name = "developer"

    def __init__(
        self,
        llm: LlmProvider,
        *,
        metrics: AgentMetrics | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._llm = llm
        self._metrics = metrics
        self._log = get_logger(component="agents.developer")
        self._system_prompt = (
            system_prompt
            or "당신은 숙련된 시니어 개발자입니다. 최소 변경으로 버그를 고치는 unified diff 만 작성합니다."
        )

    async def run(
        self,
        *,
        workspec_md: str,
        ast_summary: str,
        operations_memory_md: str = "",
        previous_review: str | None = None,
    ) -> DeveloperOutput:
        prompt = render(
            "developer.md",
            workspec_md=workspec_md,
            ast_summary=ast_summary or "_(summary unavailable)_",
            operations_memory_md=operations_memory_md or "_(운영 메모리 없음)_",
            previous_review=previous_review or "",
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
        self._log.info(
            "developer.done",
            latency_ms=latency_ms,
            diff_size=len(output.unified_diff),
        )
        return output

    @staticmethod
    def _parse(text: str) -> DeveloperOutput:
        thought_match = _THOUGHT_RE.search(text)
        diff_match = _DIFF_RE.search(text)
        thought = thought_match.group("value").strip() if thought_match else ""
        diff = diff_match.group("value").strip() if diff_match else text.strip()
        diff = _strip_code_fence(diff)
        return DeveloperOutput(thought_md=thought, unified_diff=diff)


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped
