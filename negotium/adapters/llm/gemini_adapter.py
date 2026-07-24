"""Gemini generateContent API adapter."""

from __future__ import annotations

import time
from collections.abc import Sequence

import httpx

from negotium.adapters.llm.multimodal import to_gemini_parts, to_text
from negotium.domain.entities import LlmRoute
from negotium.domain.ports import LlmMessage, LlmProvider, LlmResponse
from negotium.observability import get_logger


class GeminiProvider(LlmProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._log = get_logger(component="llm.gemini", model=model)

    async def complete(
        self,
        messages: Sequence[LlmMessage],
        *,
        route: LlmRoute = "cloud",
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LlmResponse:
        system = "\n\n".join(to_text(m.content) for m in messages if m.role == "system")
        user_parts: list[dict[str, object]] = []
        for m in messages:
            if m.role == "system":
                continue
            for part in to_gemini_parts(m.content):
                if "text" in part:
                    part = {"text": f"{m.role}: {part['text']}"}
                user_parts.append(part)
        if not user_parts:
            user_parts.append({"text": ""})
        payload: dict[str, object] = {
            "contents": [{"role": "user", "parts": user_parts}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens or 1024,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        started = time.perf_counter()
        client = self._resolve_client()
        response = await client.post(
            f"{self._base_url}/models/{self._model}:generateContent",
            params={"key": self._api_key},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        latency_ms = int((time.perf_counter() - started) * 1000)
        text = _extract_text(data)
        usage = data.get("usageMetadata") or {}
        self._log.info("llm.gemini.complete", route=route, latency_ms=latency_ms)
        return LlmResponse(
            text=text,
            prompt_tokens=int(usage.get("promptTokenCount") or 0),
            completion_tokens=int(usage.get("candidatesTokenCount") or 0),
            route=route,
            model=self._model,
        )

    def _resolve_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60)
        return self._client


def _extract_text(data: dict[str, object]) -> str:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    first = candidates[0]
    if not isinstance(first, dict):
        return ""
    content = first.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    return "".join(part.get("text", "") for part in parts if isinstance(part, dict))
