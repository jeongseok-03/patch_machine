"""Provider metadata and model catalog helpers for external LLM APIs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import httpx

ProviderName = Literal["solar", "openai", "anthropic", "gemini", "together", "vllm"]


@dataclass(frozen=True)
class ProviderMetadata:
    id: ProviderName
    label: str
    default_base_url: str
    fallback_models: tuple[str, ...]


PROVIDERS: dict[str, ProviderMetadata] = {
    "solar": ProviderMetadata(
        id="solar",
        label="Upstage / Solar",
        default_base_url="https://api.upstage.ai/v1",
        fallback_models=(
            "solar-open2",
            "solar-pro2",
            "solar-mini",
        ),
    ),
    "openai": ProviderMetadata(
        id="openai",
        label="OpenAI / GPT",
        default_base_url="https://api.openai.com/v1",
        fallback_models=(
            "gpt-5.5-pro",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5-nano",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4o",
            "gpt-4o-mini",
            "o4-mini",
        ),
    ),
    "anthropic": ProviderMetadata(
        id="anthropic",
        label="Anthropic / Claude",
        default_base_url="https://api.anthropic.com/v1",
        fallback_models=(
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
            "claude-3-7-sonnet-latest",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
        ),
    ),
    "gemini": ProviderMetadata(
        id="gemini",
        label="Google / Gemini",
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        fallback_models=(
            "gemini-3.1-pro",
            "gemini-3-flash",
            "gemini-3-flash-lite",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ),
    ),
    "together": ProviderMetadata(
        id="together",
        label="Together AI",
        default_base_url="https://api.together.ai/v1",
        fallback_models=(
            "openai/gpt-oss-20b",
            "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
            "meta-llama/Llama-3-8b-chat-hf",
            "mistralai/Mixtral-8x7B-Instruct-v0.1",
        ),
    ),
    "vllm": ProviderMetadata(
        id="vllm",
        label="vLLM / Local HTTP",
        default_base_url="http://localhost:8000/v1",
        fallback_models=("Qwen/Qwen3-4B",),
    ),
}


def require_provider(provider: str) -> ProviderMetadata:
    try:
        return PROVIDERS[provider]
    except KeyError as exc:
        raise ValueError(f"unsupported LLM provider: {provider}") from exc


# Substrings (case-insensitive) that mark a model as image/vision capable.
_VISION_MODEL_MARKERS: dict[str, tuple[str, ...]] = {
    "openai": ("gpt-4o", "gpt-4.1", "gpt-5", "gpt-6", "o3", "o4", "vision"),
    "anthropic": ("claude-3-5", "claude-3-7", "claude-sonnet-4", "claude-opus-4", "claude-haiku-4"),
    "gemini": ("gemini-1.5", "gemini-2", "gemini-3", "gemini-pro-vision", "flash"),
    "together": ("llama-3.2", "llava", "vision", "qwen2-vl", "qwen2.5-vl"),
    "vllm": ("vl", "llava", "vision", "qwen2-vl", "qwen2.5-vl"),
}


def model_supports_vision(provider: str, model: str) -> bool:
    """Best-effort check whether a provider/model accepts image input.

    This is intentionally conservative: when unsure we return ``False`` so the
    pipeline falls back to text/OCR rather than sending images a model cannot
    read. ``vllm`` defaults to text-only unless the model name hints vision.
    """

    name = (model or "").strip().lower()
    if not name:
        return False
    markers = _VISION_MODEL_MARKERS.get(provider, ())
    return any(marker in name for marker in markers)


# Substrings (case-insensitive) that mark a model as audio-input capable.
_AUDIO_MODEL_MARKERS: dict[str, tuple[str, ...]] = {
    "openai": ("gpt-4o-audio", "gpt-4o-realtime", "audio-preview", "gpt-audio"),
    # Gemini 1.5+/2.x/3.x natively accept inline audio.
    "gemini": ("gemini-1.5", "gemini-2", "gemini-3", "flash", "pro"),
    "together": ("audio", "whisper"),
    "vllm": ("audio", "qwen2-audio", "qwen2.5-omni"),
}


def model_supports_audio(provider: str, model: str) -> bool:
    """Best-effort check whether a provider/model accepts audio input.

    Anthropic has no audio-input support, so it always returns ``False``.
    """

    name = (model or "").strip().lower()
    if not name:
        return False
    markers = _AUDIO_MODEL_MARKERS.get(provider, ())
    return any(marker in name for marker in markers)


def default_base_url(provider: str, *, vllm_base_url: str = "") -> str:
    metadata = require_provider(provider)
    if provider == "vllm" and vllm_base_url.strip():
        return vllm_base_url.strip().rstrip("/")
    return metadata.default_base_url


async def list_models(
    provider: str,
    *,
    api_key: str = "",
    base_url: str = "",
) -> dict[str, object]:
    metadata = require_provider(provider)
    refreshed_at = datetime.now(UTC).isoformat()
    requires_api_key = provider in {"solar", "openai", "anthropic", "gemini", "together"}
    if not api_key and requires_api_key:
        return _fallback_payload(
            metadata,
            reason="api key is not configured",
            refreshed_at=refreshed_at,
            configured=False,
            requires_api_key=requires_api_key,
        )
    try:
        if provider == "openai":
            models = await _openai_models(
                api_key=api_key, base_url=base_url or metadata.default_base_url
            )
        elif provider == "anthropic":
            models = await _anthropic_models(
                api_key=api_key, base_url=base_url or metadata.default_base_url
            )
        elif provider == "gemini":
            models = await _gemini_models(
                api_key=api_key, base_url=base_url or metadata.default_base_url
            )
        elif provider in {"solar", "together", "vllm"}:
            models = await _openai_compatible_models(
                base_url=base_url or metadata.default_base_url, api_key=api_key
            )
        else:
            models = []
        if models:
            return {
                "provider": provider,
                "models": models,
                "source": "live",
                "refreshed_at": refreshed_at,
                "reason": "",
                "configured": bool(api_key) or not requires_api_key,
                "requires_api_key": requires_api_key,
            }
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        return _fallback_payload(
            metadata,
            reason=str(exc),
            refreshed_at=refreshed_at,
            configured=bool(api_key) or not requires_api_key,
            requires_api_key=requires_api_key,
        )
    return _fallback_payload(
        metadata,
        reason="live model list is unavailable",
        refreshed_at=refreshed_at,
        configured=bool(api_key) or not requires_api_key,
        requires_api_key=requires_api_key,
    )


def provider_payload(*, vllm_base_url: str = "") -> list[dict[str, object]]:
    return [
        {
            "provider": provider,
            "label": metadata.label,
            "base_url": default_base_url(provider, vllm_base_url=vllm_base_url),
            "base_url_source": "system",
            "fallback_models": list(metadata.fallback_models),
        }
        for provider, metadata in PROVIDERS.items()
    ]


def _fallback_payload(
    metadata: ProviderMetadata,
    *,
    reason: str,
    refreshed_at: str,
    configured: bool = False,
    requires_api_key: bool = True,
) -> dict[str, object]:
    return {
        "provider": metadata.id,
        "models": list(metadata.fallback_models),
        "source": "fallback",
        "refreshed_at": refreshed_at,
        "reason": reason,
        "configured": configured,
        "requires_api_key": requires_api_key,
    }


async def _openai_models(*, api_key: str, base_url: str) -> list[str]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
    ids = [
        model["id"]
        for model in response.json().get("data", [])
        if isinstance(model, dict) and isinstance(model.get("id"), str)
    ]
    return _chat_model_order(
        "openai", [model_id for model_id in ids if _is_openai_chat_model(model_id)]
    )


def _is_openai_chat_model(model_id: str) -> bool:
    """Return True for OpenAI models suitable for chat/responses-style text generation."""

    blocked_prefixes = (
        "babbage",
        "davinci",
        "text-",
        "dall-e",
        "tts",
        "whisper",
        "omni-moderation",
        "text-embedding",
    )
    if model_id.startswith(blocked_prefixes):
        return False
    if "embedding" in model_id or "moderation" in model_id or "audio" in model_id:
        return False
    return model_id.startswith(("gpt-", "o1", "o3", "o4"))


def _chat_model_order(provider: str, models: list[str]) -> list[str]:
    metadata = require_provider(provider)
    seen: set[str] = set()
    ordered: list[str] = []
    for preferred in metadata.fallback_models:
        if preferred in models and preferred not in seen:
            ordered.append(preferred)
            seen.add(preferred)
    for model in sorted(models):
        if model not in seen:
            ordered.append(model)
            seen.add(model)
    return ordered


async def _openai_compatible_models(*, base_url: str, api_key: str) -> list[str]:
    headers = {"Authorization": f"Bearer {api_key or 'EMPTY'}"}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
        response.raise_for_status()
    return sorted(
        model["id"]
        for model in response.json().get("data", [])
        if isinstance(model, dict) and isinstance(model.get("id"), str)
    )


async def _anthropic_models(*, api_key: str, base_url: str) -> list[str]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{base_url.rstrip('/')}/models",
            params={"limit": 100},
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        response.raise_for_status()
    return sorted(
        model["id"]
        for model in response.json().get("data", [])
        if isinstance(model, dict) and isinstance(model.get("id"), str)
    )


async def _gemini_models(*, api_key: str, base_url: str) -> list[str]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(f"{base_url.rstrip('/')}/models", params={"key": api_key})
        response.raise_for_status()
    models: list[str] = []
    for item in response.json().get("models", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").removeprefix("models/")
        methods = item.get("supportedGenerationMethods") or []
        if name and "generateContent" in methods:
            models.append(name)
    return sorted(models)


async def search_huggingface_models(query: str, *, limit: int = 12) -> list[dict[str, object]]:
    term = query.strip()
    if not term:
        return [
            {
                "id": model_id,
                "downloads": 0,
                "likes": 0,
                "tags": ["recommended"],
                "pipeline_tag": "text-generation",
            }
            for model_id in (
                "Qwen/Qwen3-4B",
                "Qwen/Qwen3-8B",
                "Qwen/Qwen2.5-7B-Instruct",
                "LGAI-EXAONE/EXAONE-4.5-33B",
                "LGAI-EXAONE/EXAONE-4.0-1.2B",
                "LGAI-EXAONE/EXAONE-3.0-7.8B-Instruct",
                "upstage/SOLAR-10.7B-Instruct-v1.0",
            )
        ]
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            "https://huggingface.co/api/models",
            params={
                "search": term,
                "filter": "text-generation",
                "sort": "downloads",
                "direction": "-1",
                "limit": limit,
            },
        )
        response.raise_for_status()
    results: list[dict[str, object]] = []
    for item in response.json():
        if not isinstance(item, dict):
            continue
        model_id = item.get("modelId") or item.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue
        results.append(
            {
                "id": model_id,
                "downloads": int(item.get("downloads") or 0),
                "likes": int(item.get("likes") or 0),
                "tags": [str(tag) for tag in item.get("tags", [])[:8]],
                "pipeline_tag": str(item.get("pipeline_tag") or ""),
            }
        )
    return results
