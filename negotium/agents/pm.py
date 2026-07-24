"""PM agent: parses an issue into a work specification."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from negotium.domain.ports import LlmMessage, LlmProvider
from negotium.observability import AgentMetrics, get_logger
from negotium.prompts import render


@dataclass
class PmOutput:
    modules: list[str]
    rationale_md: str


_MODULE_RE = re.compile(r"^MODULES:\s*(?P<value>.+)$", re.MULTILINE)
_RATIONALE_RE = re.compile(r"^RATIONALE:\s*(?P<value>.*?)(?=^\w+:|\Z)", re.MULTILINE | re.DOTALL)


class PmAgent:
    name = "pm"

    def __init__(
        self,
        llm: LlmProvider,
        *,
        metrics: AgentMetrics | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._llm = llm
        self._metrics = metrics
        self._log = get_logger(component="agents.pm")
        self._system_prompt = (
            system_prompt
            or "당신은 IT 기업의 기술 PM입니다. 간결하고 실행 가능한 작업 명세를 작성합니다."
        )

    async def run(
        self,
        *,
        issue: object,
        ast_summary: str,
        related_logs: list[str],
        operations_memory_md: str = "",
    ) -> PmOutput:
        prompt = render(
            "pm.md",
            issue=issue,
            ast_summary=ast_summary or "_(summary unavailable)_",
            related_logs=related_logs,
            operations_memory_md=operations_memory_md or "_(운영 메모리 없음)_",
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
        self._log.info("pm.done", modules=output.modules, latency_ms=latency_ms)
        return output

    @staticmethod
    def _parse(text: str) -> PmOutput:
        modules: list[str] = []
        module_match = _MODULE_RE.search(text)
        if module_match:
            modules = [m.strip() for m in module_match.group("value").split(",") if m.strip()]
        rationale_match = _RATIONALE_RE.search(text)
        rationale = rationale_match.group("value").strip() if rationale_match else text.strip()
        return PmOutput(modules=modules, rationale_md=rationale)
