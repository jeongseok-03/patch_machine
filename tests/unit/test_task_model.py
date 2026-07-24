"""Unit tests for unified task model resolution."""

from __future__ import annotations

from pathlib import Path

from negotium.app.api import _resolve_runtime_model, _resolve_task_model
from negotium.app.container import Container
from negotium.app.settings import Settings
from negotium.archive.llm_runtime import LlmRuntimeConfig, LlmTaskRoute


def test_resolve_runtime_model_prefers_local_model(tmp_path: Path) -> None:
    container = Container.build(
        Settings(env="test", archive_dir=tmp_path / "archive", workspace_dir=tmp_path / "work")
    )
    container.llm_runtime.write(
        LlmRuntimeConfig(local_model="custom/local-model", local_enabled=True, api_enabled=True)
    )
    model = _resolve_runtime_model(container, "vllm", "local")
    assert model == "custom/local-model"


def test_resolve_task_model_uses_task_route_override(tmp_path: Path) -> None:
    container = Container.build(
        Settings(env="test", archive_dir=tmp_path / "archive", workspace_dir=tmp_path / "work")
    )
    runtime = container.llm_runtime.read()
    routes = dict(runtime.task_routes or {})
    routes["chat"] = LlmTaskRoute(route="api", provider="openai", model="gpt-4o-mini-override")
    container.llm_runtime.write(
        LlmRuntimeConfig(
            local_enabled=runtime.local_enabled,
            api_enabled=runtime.api_enabled,
            default_route=runtime.default_route,
            default_provider=runtime.default_provider,
            local_model=runtime.local_model,
            task_routes=routes,
        )
    )
    model = _resolve_task_model(container, "chat", "openai", "cloud")
    assert model == "gpt-4o-mini-override"
