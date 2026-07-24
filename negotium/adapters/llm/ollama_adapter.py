"""Ollama adapter — **Phase 4 stub** (HTTP JSON)."""

from __future__ import annotations

from collections.abc import Sequence

from negotium.domain.entities import LlmRoute
from negotium.domain.ports import LlmMessage, LlmProvider, LlmResponse


class OllamaProvider(LlmProvider):
    def __init__(self, *, base_url: str, model: str = "llama3") -> None:
        self._base_url = base_url
        self._model = model

    async def complete(
        self,
        messages: Sequence[LlmMessage],
        *,
        route: LlmRoute = "local",
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LlmResponse:
        raise NotImplementedError("OllamaProvider is a Phase 4 stub")
