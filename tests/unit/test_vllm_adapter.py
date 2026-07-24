"""vLLM OpenAI-compatible adapter tests."""

from __future__ import annotations

import httpx
import pytest

from negotium.adapters.llm.vllm_adapter import VllmConnectionError, VllmProvider
from negotium.domain.ports import LlmMessage


async def test_vllm_provider_posts_openai_compatible_payload() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = VllmProvider(base_url="http://vllm.local/v1", model="Qwen/Qwen3-4B", client=client)

    response = await provider.complete([LlmMessage("user", "hello")], route="local")

    assert captured["url"] == "http://vllm.local/v1/chat/completions"
    assert '"model":"Qwen/Qwen3-4B"' in str(captured["payload"])
    assert response.text == "ok"
    assert response.prompt_tokens == 7
    await client.aclose()


async def test_vllm_provider_retries_until_server_ready() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ready"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = VllmProvider(
        base_url="http://vllm.local/v1",
        model="Qwen/Qwen3-4B",
        client=client,
        startup_wait_seconds=30.0,
        retry_interval_seconds=0.01,
    )

    response = await provider.complete([LlmMessage("user", "hello")], route="local")

    assert attempts == 3
    assert response.text == "ready"
    await client.aclose()


async def test_vllm_provider_raises_after_startup_deadline() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = VllmProvider(
        base_url="http://vllm.local/v1",
        model="Qwen/Qwen3-4B",
        client=client,
        startup_wait_seconds=0.0,
        retry_interval_seconds=0.01,
    )

    with pytest.raises(VllmConnectionError):
        await provider.complete([LlmMessage("user", "hello")], route="local")

    await client.aclose()
