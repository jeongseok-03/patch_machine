"""Llm API routes (split from the former monolithic router)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import cast

import httpx
from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from negotium.adapters.llm.catalog import (
    list_models,
    provider_payload,
    require_provider,
    search_huggingface_models,
)
from negotium.app.api._shared import (
    _audit,
    _chat_complete,
    _chunk_text,
    _default_base_url,
    _local_llm_status,
    _require,
    _settings_api_key,
    _sse_event,
    _sync_local_llm_state,
    _token_limit_status,
)
from negotium.app.container import Container
from negotium.app.schemas.core import (
    ChatRequest,
    ChatResponse,
    HuggingFaceModelItemPayload,
    HuggingFaceModelSearchPayload,
    HuggingFaceModelSearchResultPayload,
    LlmRuntimePayload,
    LocalLlmStatusPayload,
    ProviderModelPayload,
    ProviderModelPreviewPayload,
    TokenLimitPayload,
    TokenLimitStatusPayload,
)
from negotium.archive.llm_runtime import LlmRuntimeConfig
from negotium.archive.token_usage import (
    TokenLimitConfig,
)


def create_llm_router(container: Container) -> APIRouter:
    """Routes for the llm domain."""
    router = APIRouter()

    @router.get("/llm/providers")
    async def list_llm_providers() -> dict[str, object]:
        return {"providers": provider_payload(vllm_base_url=container.settings.llm.vllm_base_url)}

    @router.get("/llm/providers/{provider}/models")
    async def list_provider_models(provider: str) -> ProviderModelPayload:
        try:
            metadata = require_provider(provider)
            saved = container.secret_store.read(provider)
            api_key = saved.api_key if saved else _settings_api_key(container, provider)
            base_url = _default_base_url(container, provider)
            if provider == "vllm":
                base_url = (saved.base_url if saved and saved.base_url else base_url).rstrip("/")
            payload = await list_models(provider, api_key=api_key, base_url=base_url)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raw_models = payload.get("models")
        models = cast(list[object], raw_models) if isinstance(raw_models, list) else []
        return ProviderModelPayload(
            provider=str(payload.get("provider") or metadata.id),
            models=[str(model) for model in models],
            source=str(payload.get("source") or "fallback"),
            refreshed_at=str(payload.get("refreshed_at") or ""),
            reason=str(payload.get("reason") or ""),
            configured=bool(payload.get("configured", False)),
            requires_api_key=bool(payload.get("requires_api_key", True)),
        )

    @router.post("/llm/providers/{provider}/models/preview")
    async def preview_provider_models(
        provider: str,
        payload: ProviderModelPreviewPayload,
    ) -> ProviderModelPayload:
        try:
            metadata = require_provider(provider)
            base_url = payload.base_url.strip() or _default_base_url(container, provider)
            result = await list_models(provider, api_key=payload.api_key.strip(), base_url=base_url)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raw_models = result.get("models")
        models = cast(list[object], raw_models) if isinstance(raw_models, list) else []
        return ProviderModelPayload(
            provider=str(result.get("provider") or metadata.id),
            models=[str(model) for model in models],
            source=str(result.get("source") or "fallback"),
            refreshed_at=str(result.get("refreshed_at") or ""),
            reason=str(result.get("reason") or ""),
            configured=bool(result.get("configured", False)),
            requires_api_key=bool(result.get("requires_api_key", True)),
        )

    @router.post("/llm/local/huggingface/search")
    async def search_local_huggingface_models(
        payload: HuggingFaceModelSearchPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> HuggingFaceModelSearchResultPayload:
        _require(container, x_ng_user, "admin:api_keys")
        try:
            results = await search_huggingface_models(
                payload.query,
                limit=max(1, min(payload.limit, 50)),
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail=f"Hugging Face model search failed: {exc}",
            ) from exc
        return HuggingFaceModelSearchResultPayload(
            query=payload.query,
            models=[HuggingFaceModelItemPayload(**item) for item in results],
        )

    @router.get("/llm/runtime")
    async def read_llm_runtime() -> LlmRuntimePayload:
        return LlmRuntimePayload.from_config(container.llm_runtime.read(), container)

    @router.put("/llm/runtime")
    async def write_llm_runtime(
        payload: LlmRuntimePayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> LlmRuntimePayload:
        actor = _require(container, x_ng_user, "admin:local_llm")
        config = payload.to_config()
        container.llm_runtime.write(config)
        _sync_local_llm_state(container, enabled=config.local_enabled)
        _audit(
            container,
            actor=actor,
            action="llm_runtime.update",
            target="llm_runtime",
            details=config.to_dict(),
        )
        return LlmRuntimePayload.from_config(config, container)

    @router.get("/llm/local-status")
    async def read_local_llm_status() -> LocalLlmStatusPayload:
        return _local_llm_status(container)

    @router.post("/llm/local/start")
    async def start_local_llm(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> LocalLlmStatusPayload:
        actor = _require(container, x_ng_user, "admin:local_llm")
        if container.embedded_vllm() is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(
                    "현재 백엔드는 vLLM 임베드 모드가 아닙니다. Docker 백엔드는 로컬 GPU 모델을 "
                    "직접 올릴 수 없으니 호스트에서 NG_VLLM_MODE=embedded 로 negotium serve를 "
                    "실행하세요."
                ),
            )
        runtime = container.llm_runtime.read()
        if not runtime.local_enabled:
            container.llm_runtime.write(
                LlmRuntimeConfig(
                    local_enabled=True,
                    api_enabled=runtime.api_enabled,
                    default_route=runtime.default_route,
                    default_provider=runtime.default_provider,
                    local_model=runtime.local_model,
                    task_routes=runtime.task_routes,
                )
            )
        _sync_local_llm_state(container, enabled=True)
        _audit(container, actor=actor, action="llm_local.start", target="llm_runtime")
        return _local_llm_status(container)

    @router.post("/llm/local/stop")
    async def stop_local_llm(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> LocalLlmStatusPayload:
        actor = _require(container, x_ng_user, "admin:local_llm")
        runtime = container.llm_runtime.read()
        container.llm_runtime.write(
            LlmRuntimeConfig(
                local_enabled=False,
                api_enabled=runtime.api_enabled,
                default_route=runtime.default_route,
                default_provider=runtime.default_provider,
                local_model=runtime.local_model,
                task_routes=runtime.task_routes,
            )
        )
        _sync_local_llm_state(container, enabled=False)
        _audit(container, actor=actor, action="llm_local.stop", target="llm_runtime")
        return _local_llm_status(container)

    @router.post("/llm/chat")
    async def chat(
        payload: ChatRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> ChatResponse:
        actor = _require(container, x_ng_user, "llm:chat")
        return await _chat_complete(container, payload, actor)

    @router.post("/llm/chat/stream")
    async def chat_stream(
        payload: ChatRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> StreamingResponse:
        actor = _require(container, x_ng_user, "llm:chat")

        async def events() -> AsyncIterator[str]:
            try:
                result = await _chat_complete(container, payload, actor)
            except HTTPException as exc:
                yield _sse_event("error", {"detail": str(exc.detail), "status": exc.status_code})
                return
            except Exception as exc:
                yield _sse_event("error", {"detail": str(exc)})
                return
            yield _sse_event(
                "meta",
                {
                    "route": result.route,
                    "provider": result.provider,
                    "model": result.model,
                    "skill_id": result.skill_id,
                },
            )
            for chunk in _chunk_text(result.answer):
                yield _sse_event("delta", {"text": chunk})
                await asyncio.sleep(0.02)
            yield _sse_event("done", result.model_dump())

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/llm/token-limits")
    async def read_token_limits(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> TokenLimitStatusPayload:
        _require(container, x_ng_user, "admin:token_limits")
        return _token_limit_status(container)

    @router.put("/llm/token-limits")
    async def update_token_limits(
        payload: TokenLimitPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> TokenLimitStatusPayload:
        actor = _require(container, x_ng_user, "admin:token_limits")
        container.token_usage.write_limits(
            TokenLimitConfig(
                enforcement_enabled=payload.enforcement_enabled,
                per_request_max_tokens=max(0, int(payload.per_request_max_tokens or 0)),
                daily_total_tokens=max(0, int(payload.daily_total_tokens or 0)),
                monthly_total_tokens=max(0, int(payload.monthly_total_tokens or 0)),
            )
        )
        _audit(
            container,
            actor=actor,
            action="llm.token_limits.update",
            target="token_limits",
            details=payload.model_dump(),
        )
        return _token_limit_status(container)

    return router
