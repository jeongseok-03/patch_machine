"""OpenAI chat completion adapter."""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from typing import Any

from negotium.adapters.llm.multimodal import to_openai_content
from negotium.domain.entities import LlmRoute
from negotium.domain.ports import LlmMessage, LlmProvider, LlmResponse
from negotium.observability import get_logger

_COMPLETION_TOKENS_PREFIXES = (
    "o1",
    "o3",
    "o4",
    "o5",
    "gpt-5",
    "gpt-6",
)
_COMPLETION_TOKENS_KEYWORDS = ("reasoning",)


def _model_uses_completion_tokens_param(model: str) -> bool:
    """Return True when the model only accepts ``max_completion_tokens``.

    OpenAI reasoning/next-gen chat models (``o*``, ``gpt-5*``) reject the
    legacy ``max_tokens`` parameter and require ``max_completion_tokens``
    instead. Older chat models keep using ``max_tokens``.
    """

    name = (model or "").strip().lower()
    if not name:
        return False
    if name.startswith(_COMPLETION_TOKENS_PREFIXES):
        return True
    return any(keyword in name for keyword in _COMPLETION_TOKENS_KEYWORDS)


_UNSUPPORTED_PARAM_RE = re.compile(r"Unsupported parameter:\s*'?(?P<param>[\w_]+)'?", re.IGNORECASE)
_UNSUPPORTED_VALUE_PARAM_RE = re.compile(r"Unsupported value:.*?'(?P<param>[\w_]+)'", re.IGNORECASE)


def _extract_unsupported_param(message: str) -> str | None:
    match = _UNSUPPORTED_PARAM_RE.search(message or "")
    if not match:
        match = _UNSUPPORTED_VALUE_PARAM_RE.search(message or "")
    if not match:
        return None
    return match.group("param")


class OpenAiProvider(LlmProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        client: object | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url or None
        self._client = client
        self._log = get_logger(component="llm.openai", model=model)

    async def complete(
        self,
        messages: Sequence[LlmMessage],
        *,
        route: LlmRoute = "cloud",
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LlmResponse:
        client = self._resolve_client()
        payload = [{"role": m.role, "content": to_openai_content(m.content)} for m in messages]
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": payload,
        }
        if not _model_uses_completion_tokens_param(self._model):
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            if _model_uses_completion_tokens_param(self._model):
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["max_tokens"] = max_tokens
        started = time.perf_counter()
        response = await self._create_completion(client, kwargs)
        latency_ms = int((time.perf_counter() - started) * 1000)
        choice = response.choices[0]
        text = choice.message.content or ""
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        self._log.info(
            "llm.openai.complete",
            route=route,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return LlmResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            route=route,
            model=self._model,
        )

    async def _create_completion(self, client: Any, kwargs: dict[str, Any]) -> Any:
        try:
            return await client.chat.completions.create(**kwargs)
        except Exception as exc:  # pragma: no cover - defensive remap
            message = str(exc)
            param = _extract_unsupported_param(message)
            if param == "max_tokens" and "max_tokens" in kwargs:
                fallback = dict(kwargs)
                fallback["max_completion_tokens"] = fallback.pop("max_tokens")
                self._log.info(
                    "llm.openai.retry_with_max_completion_tokens",
                    model=self._model,
                )
                return await client.chat.completions.create(**fallback)
            if param == "max_completion_tokens" and "max_completion_tokens" in kwargs:
                fallback = dict(kwargs)
                fallback["max_tokens"] = fallback.pop("max_completion_tokens")
                self._log.info(
                    "llm.openai.retry_with_max_tokens",
                    model=self._model,
                )
                return await client.chat.completions.create(**fallback)
            if param == "temperature" and "temperature" in kwargs:
                fallback = dict(kwargs)
                fallback.pop("temperature", None)
                self._log.info(
                    "llm.openai.retry_without_temperature",
                    model=self._model,
                )
                return await client.chat.completions.create(**fallback)
            raise

    def _resolve_client(self) -> Any:
        if self._client is not None:
            return self._client
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client
