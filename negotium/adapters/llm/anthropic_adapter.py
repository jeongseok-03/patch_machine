"""Anthropic Messages API adapter."""

from __future__ import annotations

import time
from collections.abc import Sequence

import httpx

from negotium.adapters.llm.multimodal import to_anthropic_content, to_text
from negotium.domain.entities import LlmRoute
from negotium.domain.ports import LlmMessage, LlmProvider, LlmResponse
from negotium.observability import get_logger


class AnthropicProvider(LlmProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.anthropic.com/v1",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._log = get_logger(component="llm.anthropic", model=model)

    async def complete(
        self,
        messages: Sequence[LlmMessage],
        *,
        route: LlmRoute = "cloud",
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LlmResponse:
        system = "\n\n".join(to_text(m.content) for m in messages if m.role == "system")
        user_messages = [
            {
                "role": "assistant" if m.role == "assistant" else "user",
                "content": to_anthropic_content(m.content),
            }
            for m in messages
            if m.role != "system"
        ]
        payload: dict[str, object] = {
            "model": self._model,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
        }
        if system:
            payload["system"] = system

        started = time.perf_counter()
        client = self._resolve_client()
        response = await client.post(
            f"{self._base_url}/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        latency_ms = int((time.perf_counter() - started) * 1000)
        text = "".join(part.get("text", "") for part in data.get("content", []) if part)
        usage = data.get("usage") or {}
        self._log.info("llm.anthropic.complete", route=route, latency_ms=latency_ms)
        return LlmResponse(
            text=text,
            prompt_tokens=int(usage.get("input_tokens") or 0),
            completion_tokens=int(usage.get("output_tokens") or 0),
            route=route,
            model=self._model,
        )

    def _resolve_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60)
        return self._client
