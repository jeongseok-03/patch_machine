"""LLM gateway routing safety net."""

from __future__ import annotations

import httpx
import pytest

from negotium.adapters.llm import catalog
from negotium.adapters.llm.fake_adapter import FakeLlmProvider, ScriptedResponse
from negotium.adapters.llm.gateway import LlmGateway
from negotium.domain.ports import LlmMessage


async def test_default_route_uses_cloud_provider() -> None:
    cloud = FakeLlmProvider(responses=[ScriptedResponse(text="ok")])
    gateway = LlmGateway(cloud=cloud)
    response = await gateway.complete([LlmMessage("user", "hello")])
    assert response.text == "ok"
    assert response.route == "cloud"


async def test_secret_pattern_forces_local_and_raises_without_local() -> None:
    cloud = FakeLlmProvider(responses=[ScriptedResponse(text="leaked")])
    gateway = LlmGateway(cloud=cloud)
    msg = LlmMessage("user", "please review sk-abcdefghijklmnopqrstuvwxyz123456")
    with pytest.raises(RuntimeError):
        await gateway.complete([msg])


async def test_secret_pattern_routes_to_local_when_available() -> None:
    cloud = FakeLlmProvider(responses=[ScriptedResponse(text="cloud")])
    local = FakeLlmProvider(responses=[ScriptedResponse(text="local")])
    gateway = LlmGateway(cloud=cloud, local=local)
    msg = LlmMessage("user", "sk-aaaaaaaaaaaaaaaaaaaaaaaaa123456")
    response = await gateway.complete([msg])
    assert response.text == "local"
    assert response.route == "local"


async def test_anthropic_model_catalog_parses_live_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, *args: object, **kwargs: object) -> httpx.Response:
            request = httpx.Request("GET", "https://api.anthropic.com/v1/models")
            return httpx.Response(
                200,
                request=request,
                json={
                    "data": [
                        {"id": "claude-sonnet-4-6"},
                        {"id": "claude-opus-4-7"},
                    ]
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    payload = await catalog.list_models("anthropic", api_key="test-key")

    assert payload["source"] == "live"
    assert payload["models"] == ["claude-opus-4-7", "claude-sonnet-4-6"]
    assert payload["configured"] is True


async def test_openai_model_catalog_filters_non_chat_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, *args: object, **kwargs: object) -> httpx.Response:
            request = httpx.Request("GET", "https://api.openai.com/v1/models")
            return httpx.Response(
                200,
                request=request,
                json={
                    "data": [
                        {"id": "babbage-002"},
                        {"id": "text-embedding-3-large"},
                        {"id": "whisper-1"},
                        {"id": "gpt-4o-mini"},
                        {"id": "gpt-4.1"},
                        {"id": "o4-mini"},
                    ]
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    payload = await catalog.list_models("openai", api_key="test-key")

    assert payload["source"] == "live"
    assert payload["models"] == ["gpt-4.1", "gpt-4o-mini", "o4-mini"]
    assert "babbage-002" not in payload["models"]
    assert "text-embedding-3-large" not in payload["models"]


async def test_together_model_catalog_uses_openai_compatible_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str, *args: object, **kwargs: object) -> httpx.Response:
            request = httpx.Request("GET", url)
            return httpx.Response(
                200,
                request=request,
                json={
                    "data": [
                        {"id": "meta-llama/Llama-3-8b-chat-hf"},
                        {"id": "openai/gpt-oss-20b"},
                    ]
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    payload = await catalog.list_models("together", api_key="test-key")

    assert payload["source"] == "live"
    assert payload["models"] == ["meta-llama/Llama-3-8b-chat-hf", "openai/gpt-oss-20b"]
    assert payload["configured"] is True


async def test_solar_model_catalog_uses_openai_compatible_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str, *args: object, **kwargs: object) -> httpx.Response:
            assert url.startswith("https://api.upstage.ai/v1")
            request = httpx.Request("GET", url)
            return httpx.Response(
                200,
                request=request,
                json={
                    "data": [
                        {"id": "solar-open2"},
                        {"id": "solar-pro2"},
                    ]
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    payload = await catalog.list_models("solar", api_key="test-key")

    assert payload["source"] == "live"
    assert payload["models"] == ["solar-open2", "solar-pro2"]
    assert payload["configured"] is True


async def test_solar_model_catalog_falls_back_without_api_key() -> None:
    payload = await catalog.list_models("solar", api_key="")

    assert payload["source"] == "fallback"
    assert "solar-open2" in payload["models"]
    assert payload["configured"] is False
    assert payload["requires_api_key"] is True
