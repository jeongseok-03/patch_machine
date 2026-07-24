"""Standalone FastAPI app for external LLM calls."""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from negotium.adapters.llm.anthropic_adapter import AnthropicProvider
from negotium.adapters.llm.catalog import (
    default_base_url,
    list_models,
    provider_payload,
    require_provider,
)
from negotium.adapters.llm.gemini_adapter import GeminiProvider
from negotium.adapters.llm.openai_adapter import OpenAiProvider
from negotium.adapters.llm.vllm_adapter import VllmProvider
from negotium.app.settings import Settings, load_settings
from negotium.archive.secret_store import SecretStore
from negotium.domain.entities import LlmRoute
from negotium.domain.ports import LlmMessage, LlmProvider, LlmResponse


class GatewayMessage(BaseModel):
    role: str
    content: str


class GatewayChatRequest(BaseModel):
    provider: Literal["solar", "openai", "anthropic", "gemini", "together", "vllm"]
    route: Literal["cloud", "local"] = "cloud"
    messages: list[GatewayMessage]
    temperature: float = 0.0
    max_tokens: int = 1024


class GatewayChatResponse(BaseModel):
    text: str
    route: str
    model: str
    prompt_tokens: int
    completion_tokens: int


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    secret_store = SecretStore(settings.archive_dir, master_key=settings.secret_key)
    app = FastAPI(title="Negotium LLM Gateway", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/v1/providers")
    async def providers() -> dict[str, object]:
        return {"providers": provider_payload(vllm_base_url=settings.llm.vllm_base_url)}

    @app.get("/v1/providers/{provider}/models")
    async def models(provider: str) -> dict[str, object]:
        try:
            require_provider(provider)
            saved = secret_store.read(provider)
            base_url = _base_url(settings, provider, saved.base_url if saved else "")
            api_key = saved.api_key if saved else _settings_api_key(settings, provider)
            return await list_models(provider, api_key=api_key, base_url=base_url)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post("/v1/chat/completions")
    async def chat(payload: GatewayChatRequest) -> GatewayChatResponse:
        try:
            provider = _provider_for(settings, secret_store, payload.provider)
            route: LlmRoute = payload.route
            response = await provider.complete(
                [LlmMessage(message.role, message.content) for message in payload.messages],
                route=route,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return _response_payload(response)

    return app


def _provider_for(settings: Settings, secret_store: SecretStore, provider: str) -> LlmProvider:
    require_provider(provider)
    saved = secret_store.read(provider)
    api_key = saved.api_key if saved else _settings_api_key(settings, provider)
    model = _model(settings, provider, saved.model if saved else "")
    base_url = _base_url(settings, provider, saved.base_url if saved else "")
    if provider == "openai":
        if not api_key:
            raise ValueError("OpenAI API key is not configured")
        return OpenAiProvider(api_key=api_key, model=model, base_url=base_url)
    if provider == "anthropic":
        if not api_key:
            raise ValueError("Anthropic API key is not configured")
        return AnthropicProvider(api_key=api_key, model=model, base_url=base_url)
    if provider == "gemini":
        if not api_key:
            raise ValueError("Gemini API key is not configured")
        return GeminiProvider(api_key=api_key, model=model, base_url=base_url)
    if provider == "together":
        if not api_key:
            raise ValueError("Together API key is not configured")
        return OpenAiProvider(api_key=api_key, model=model, base_url=base_url)
    if provider == "solar":
        if not api_key:
            raise ValueError("Solar API key is not configured")
        return OpenAiProvider(api_key=api_key, model=model, base_url=base_url)
    return VllmProvider(base_url=base_url, model=model, api_key=api_key or "EMPTY")


def _settings_api_key(settings: Settings, provider: str) -> str:
    if provider == "openai":
        return settings.llm.openai_api_key
    if provider == "anthropic":
        return settings.llm.anthropic_api_key
    if provider == "gemini":
        return settings.llm.gemini_api_key
    if provider == "together":
        return settings.llm.together_api_key
    if provider == "solar":
        return settings.llm.solar_api_key
    return ""


def _model(settings: Settings, provider: str, saved_model: str) -> str:
    if saved_model:
        return saved_model
    if provider == "openai":
        return settings.llm.openai_model
    if provider == "anthropic":
        return settings.llm.anthropic_model
    if provider == "gemini":
        return settings.llm.gemini_model
    if provider == "together":
        return settings.llm.together_model
    if provider == "solar":
        return settings.llm.solar_model
    return settings.llm.vllm_model


def _base_url(settings: Settings, provider: str, saved_base_url: str) -> str:
    if provider == "together":
        return (saved_base_url or settings.llm.together_base_url).rstrip("/")
    if provider == "solar":
        return (saved_base_url or settings.llm.solar_base_url).rstrip("/")
    if provider == "vllm" and saved_base_url:
        return saved_base_url.rstrip("/")
    return default_base_url(provider, vllm_base_url=settings.llm.vllm_base_url)


def _response_payload(response: LlmResponse) -> GatewayChatResponse:
    return GatewayChatResponse(
        text=response.text,
        route=response.route,
        model=response.model,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
    )


app = create_app
