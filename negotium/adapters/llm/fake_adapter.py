"""In-memory scripted LLM used in tests and offline rehearsals."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from negotium.domain.entities import LlmRoute
from negotium.domain.ports import (
    LlmMessage,
    LlmProvider,
    LlmResponse,
    flatten_message_text,
)


@dataclass
class ScriptedResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tag: str | None = None


@dataclass
class FakeLlmProvider(LlmProvider):
    """Play a pre-recorded sequence of responses or resolve by prompt tag.

    Agents pass a ``tag`` via the trailing system message ``[agent: pm]`` etc.
    The fake picks the first ScriptedResponse whose tag matches, falling back
    to FIFO when no tags are present.
    """

    responses: list[ScriptedResponse] = field(default_factory=list)
    calls: list[list[LlmMessage]] = field(default_factory=list)

    async def complete(
        self,
        messages: Sequence[LlmMessage],
        *,
        route: LlmRoute = "cloud",
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LlmResponse:
        self.calls.append(list(messages))
        tag = self._infer_tag(messages)
        chosen: ScriptedResponse | None = None
        for candidate in self.responses:
            if candidate.tag and candidate.tag == tag:
                chosen = candidate
                self.responses.remove(candidate)
                break
        if chosen is None and self.responses:
            chosen = self.responses.pop(0)
        if chosen is None:
            chosen = ScriptedResponse(text="")
        return LlmResponse(
            text=chosen.text,
            prompt_tokens=chosen.prompt_tokens,
            completion_tokens=chosen.completion_tokens,
            route=route,
            model="fake",
        )

    @staticmethod
    def _infer_tag(messages: Sequence[LlmMessage]) -> str | None:
        for message in reversed(messages):
            content = flatten_message_text(message.content)
            if message.role == "system" and "[agent:" in content:
                start = content.find("[agent:")
                end = content.find("]", start)
                if end > start:
                    return content[start + len("[agent:") : end].strip()
        return None
