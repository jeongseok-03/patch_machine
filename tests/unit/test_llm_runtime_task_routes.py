from __future__ import annotations

from pathlib import Path

from negotium.archive.llm_runtime import LlmRuntimeConfig, LlmRuntimeStore, LlmTaskRoute


def test_runtime_task_routes_roundtrip(tmp_path: Path) -> None:
    store = LlmRuntimeStore(tmp_path)
    config = LlmRuntimeConfig(
        default_route="local",
        default_provider="vllm",
        task_routes={
            "memory_summary": LlmTaskRoute(route="api", provider="openai", model="gpt-4.1-mini"),
            "chat": LlmTaskRoute(route="local", provider="vllm", model="Qwen/Qwen3-4B"),
        },
    )
    store.write(config)

    loaded = store.read()
    assert loaded.route_for("memory_summary").route == "api"
    assert loaded.route_for("memory_summary").provider == "openai"
    assert loaded.route_for("memory_summary").model == "gpt-4.1-mini"
    assert loaded.route_for("unknown_task").route == "local"
    assert loaded.route_for("unknown_task").provider == "vllm"


def test_runtime_task_routes_sanitize_invalid_values() -> None:
    loaded = LlmRuntimeConfig.from_mapping(
        {
            "default_route": "api",
            "default_provider": "anthropic",
            "task_routes": {
                "hiring": {"route": "bad", "provider": "bad", "model": "x"},
            },
        },
    )

    route = loaded.route_for("hiring")
    assert route.route == "api"
    assert route.provider == "anthropic"
    assert route.model == "x"


def test_runtime_task_routes_accept_together_provider() -> None:
    loaded = LlmRuntimeConfig.from_mapping(
        {
            "default_route": "api",
            "default_provider": "together",
            "task_routes": {
                "chat": {
                    "route": "api",
                    "provider": "together",
                    "model": "openai/gpt-oss-20b",
                },
            },
        },
    )

    assert loaded.default_provider == "together"
    assert loaded.route_for("chat").provider == "together"
    assert loaded.route_for("chat").model == "openai/gpt-oss-20b"


def test_runtime_task_routes_accept_solar_provider() -> None:
    """Solar must survive the provider whitelist round-trip (no silent vllm downgrade)."""

    loaded = LlmRuntimeConfig.from_mapping(
        {
            "default_route": "api",
            "default_provider": "solar",
            "task_routes": {
                "chat": {
                    "route": "api",
                    "provider": "solar",
                    "model": "solar-open2",
                },
            },
        },
    )

    assert loaded.default_provider == "solar"
    assert loaded.route_for("chat").provider == "solar"
    assert loaded.route_for("chat").model == "solar-open2"
