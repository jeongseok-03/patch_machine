"""Persistent runtime switches for chat-oriented LLM providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from negotium.archive._store import read_json_file, write_json_file

LlmProviderName = Literal["vllm", "solar", "openai", "anthropic", "gemini", "together", "fake"]
KNOWN_PROVIDERS: frozenset[str] = frozenset(
    {"vllm", "solar", "openai", "anthropic", "gemini", "together", "fake"}
)
LlmRuntimeRoute = Literal["local", "api"]
LlmTaskName = Literal[
    "memory_summary",
    "agent_planning",
    "document_generation",
    "hiring",
    "handover",
    "chat",
]


@dataclass(frozen=True)
class LlmTaskRoute:
    route: LlmRuntimeRoute = "local"
    provider: LlmProviderName = "vllm"
    model: str = ""

    @classmethod
    def from_mapping(
        cls, payload: dict[str, Any], *, fallback: LlmRuntimeConfig | None = None
    ) -> LlmTaskRoute:
        route = payload.get("route") or (fallback.default_route if fallback else "local")
        provider = payload.get("provider") or (fallback.default_provider if fallback else "vllm")
        if route not in {"local", "api"}:
            route = fallback.default_route if fallback else "local"
        if provider not in KNOWN_PROVIDERS:
            provider = fallback.default_provider if fallback else "vllm"
        return cls(route=route, provider=provider, model=str(payload.get("model") or ""))

    def to_dict(self) -> dict[str, object]:
        return {
            "route": self.route,
            "provider": self.provider,
            "model": self.model,
        }


@dataclass(frozen=True)
class LlmRuntimeConfig:
    local_enabled: bool = True
    api_enabled: bool = True
    default_route: LlmRuntimeRoute = "local"
    default_provider: LlmProviderName = "vllm"
    local_model: str = "Qwen/Qwen3-4B"
    task_routes: dict[str, LlmTaskRoute] | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> LlmRuntimeConfig:
        route = payload.get("default_route") or "local"
        provider = payload.get("default_provider") or "vllm"
        if route not in {"local", "api"}:
            route = "local"
        if provider not in KNOWN_PROVIDERS:
            provider = "vllm"
        base = cls(
            local_enabled=bool(payload.get("local_enabled", True)),
            api_enabled=bool(payload.get("api_enabled", True)),
            default_route=route,
            default_provider=provider,
            local_model=str(payload.get("local_model") or "Qwen/Qwen3-4B"),
        )
        task_routes_payload = payload.get("task_routes")
        task_routes: dict[str, LlmTaskRoute] = {}
        if isinstance(task_routes_payload, dict):
            for task, config in task_routes_payload.items():
                if isinstance(config, dict):
                    task_routes[str(task)] = LlmTaskRoute.from_mapping(config, fallback=base)
        return cls(
            local_enabled=base.local_enabled,
            api_enabled=base.api_enabled,
            default_route=base.default_route,
            default_provider=base.default_provider,
            local_model=base.local_model,
            task_routes=task_routes or None,
        )

    def route_for(self, task: str) -> LlmTaskRoute:
        routes = self.task_routes or {}
        configured = routes.get(task)
        if configured is not None:
            return configured
        return LlmTaskRoute(route=self.default_route, provider=self.default_provider)

    def to_dict(self) -> dict[str, object]:
        return {
            "local_enabled": self.local_enabled,
            "api_enabled": self.api_enabled,
            "default_route": self.default_route,
            "default_provider": self.default_provider,
            "local_model": self.local_model,
            "task_routes": {
                task: route.to_dict() for task, route in (self.task_routes or {}).items()
            },
        }


class LlmRuntimeStore:
    """File-backed runtime flags for the local console."""

    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "llm_runtime.json"

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> LlmRuntimeConfig:
        payload = read_json_file(self._path, default=dict)
        if not payload:
            return LlmRuntimeConfig()
        if not isinstance(payload, dict):
            raise ValueError("LLM runtime config must be a JSON object")
        return LlmRuntimeConfig.from_mapping(payload)

    def write(self, config: LlmRuntimeConfig) -> None:
        payload = {
            **config.to_dict(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        write_json_file(self._path, payload)
