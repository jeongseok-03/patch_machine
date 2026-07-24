"""LLM service entry points for chat and office task completion.

The current router keeps the concrete implementations private while route
extraction continues. These names define the service boundary used by the
split API modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from negotium.app.container import Container
    from negotium.archive.llm_runtime import LlmProviderName
    from negotium.domain.entities import LlmRoute
    from negotium.domain.ports import LlmMessage, LlmResponse


async def complete_office_task(
    container: Container, prompt: str, *, task: str = "document_generation"
) -> str:
    from negotium.app.api import _complete_office_task

    return await _complete_office_task(container, prompt, task=task)


async def complete_with_provider(
    container: Container,
    messages: list[LlmMessage],
    *,
    provider: LlmProviderName,
    route: LlmRoute,
    temperature: float,
    max_tokens: int,
) -> LlmResponse:
    from negotium.app.api import _complete_with_provider

    return await _complete_with_provider(
        container,
        messages,
        provider=provider,
        route=route,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def resolve_runtime_task(container: Container, task: str) -> tuple[LlmProviderName, LlmRoute]:
    from negotium.app.api import _resolve_runtime_task

    return _resolve_runtime_task(container, task)
