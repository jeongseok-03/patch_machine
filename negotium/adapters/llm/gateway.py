"""Routing gateway that picks cloud vs local providers per request.

Phase 1 only wires ``cloud`` to the OpenAI adapter. ``local`` raises
``NotImplementedError`` via the stub adapters to make the safety boundary
explicit rather than silently falling back to cloud.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from negotium.archive.llm_runtime import LlmProviderName
from negotium.domain.entities import LlmRoute
from negotium.domain.ports import (
    LlmMessage,
    LlmProvider,
    LlmResponse,
    flatten_message_text,
)
from negotium.observability import get_logger

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)


@dataclass
class LlmGateway(LlmProvider):
    cloud: LlmProvider
    local: LlmProvider | None = None
    default_route: LlmRoute = "cloud"
    cloud_providers: dict[str, LlmProvider] | None = None
    local_providers: dict[str, LlmProvider] | None = None

    def __post_init__(self) -> None:
        self._log = get_logger(component="llm.gateway", default_route=self.default_route)

    async def complete(
        self,
        messages: Sequence[LlmMessage],
        *,
        route: LlmRoute = "cloud",
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LlmResponse:
        effective: LlmRoute = route if route else self.default_route
        if self._needs_local(messages) and effective == "cloud":
            self._log.warning("llm.gateway.force_local", reason="secret_pattern")
            effective = "local"
        provider = self._resolve_provider(effective)
        return await provider.complete(
            messages,
            route=effective,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def complete_with_provider(
        self,
        messages: Sequence[LlmMessage],
        *,
        provider_name: LlmProviderName,
        route: LlmRoute,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LlmResponse:
        provider = self._resolve_named_provider(provider_name=provider_name, route=route)
        return await provider.complete(
            messages,
            route=route,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _resolve_provider(self, route: LlmRoute) -> LlmProvider:
        if route == "cloud":
            return self.cloud
        if self.local is None:
            raise RuntimeError(
                "local LLM route requested but no local provider is configured. "
                "Configure NG_LLM_PROVIDER=ollama|vllm in Phase 4.",
            )
        return self.local

    def _resolve_named_provider(
        self,
        *,
        provider_name: LlmProviderName,
        route: LlmRoute,
    ) -> LlmProvider:
        providers = self.local_providers if route == "local" else self.cloud_providers
        if providers and provider_name in providers:
            return providers[provider_name]
        if provider_name == "fake":
            return self.cloud
        return self._resolve_provider(route)

    @staticmethod
    def _needs_local(messages: Sequence[LlmMessage]) -> bool:
        for message in messages:
            text = flatten_message_text(message.content)
            for pattern in _SECRET_PATTERNS:
                if pattern.search(text):
                    return True
        return False
