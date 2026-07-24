"""vLLM OpenAI-compatible chat completion adapter."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence

import httpx

from negotium.adapters.llm.multimodal import to_text
from negotium.domain.entities import LlmRoute
from negotium.domain.ports import LlmMessage, LlmProvider, LlmResponse
from negotium.observability import get_logger

# httpx default read timeout is too small for first-request / long generations
_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)


class VllmConnectionError(RuntimeError):
    """Raised when the vLLM HTTP server stays unreachable after startup retries."""


class VllmProvider(LlmProvider):
    def __init__(
        self,
        *,
        base_url: str,
        model: str = "Qwen/Qwen3-4B",
        api_key: str = "EMPTY",
        client: httpx.AsyncClient | None = None,
        startup_wait_seconds: float = 5.0,
        retry_interval_seconds: float = 2.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._client = client
        self._startup_wait_seconds = startup_wait_seconds
        self._retry_interval_seconds = retry_interval_seconds
        self._log = get_logger(component="llm.vllm", model=model)

    async def complete(
        self,
        messages: Sequence[LlmMessage],
        *,
        route: LlmRoute = "local",
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LlmResponse:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": to_text(m.content)} for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        started = time.perf_counter()
        client = self._resolve_client()
        deadline = time.monotonic() + self._startup_wait_seconds
        while True:
            try:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                break
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                if time.monotonic() >= deadline:
                    self._log.warning(
                        "llm.vllm.unreachable",
                        base_url=self._base_url,
                        error=str(exc),
                    )
                    raise VllmConnectionError(
                        f"vLLM HTTP 서버({self._base_url})에 연결할 수 없습니다. "
                        "로컬 GPU 임베드 모드는 Docker 백엔드가 아니라 호스트에서 "
                        "`NG_VLLM_MODE=embedded uv run negotium serve`로 실행해야 합니다."
                    ) from exc
                self._log.info(
                    "llm.vllm.waiting_for_server",
                    retry_in_s=self._retry_interval_seconds,
                    base_url=self._base_url,
                )
                await asyncio.sleep(self._retry_interval_seconds)
            except httpx.HTTPStatusError as exc:
                # Cold start: engine may return 5xx while weights load
                if exc.response.status_code >= 500 and time.monotonic() < deadline:
                    self._log.info(
                        "llm.vllm.server_error_retry",
                        status=exc.response.status_code,
                        retry_in_s=self._retry_interval_seconds,
                    )
                    await asyncio.sleep(self._retry_interval_seconds)
                    continue
                raise

        data = response.json()
        latency_ms = int((time.perf_counter() - started) * 1000)
        choice = data["choices"][0]
        text = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        self._log.info("llm.vllm.complete", route=route, latency_ms=latency_ms)
        return LlmResponse(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            route=route,
            model=self._model,
        )

    def _resolve_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        return self._client
