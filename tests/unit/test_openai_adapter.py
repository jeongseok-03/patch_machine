"""OpenAI chat adapter parameter routing tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from negotium.adapters.llm.openai_adapter import (
    OpenAiProvider,
    _model_uses_completion_tokens_param,
)
from negotium.domain.ports import LlmMessage


@dataclass
class _FakeUsage:
    prompt_tokens: int = 1
    completion_tokens: int = 1


@dataclass
class _FakeMessage:
    content: str = "ok"


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeResponse:
    choices: list[_FakeChoice]
    usage: _FakeUsage


class _FakeCompletions:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._error = error

    async def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        if self._error is not None and len(self.calls) == 1:
            error = self._error
            self._error = None
            raise error
        return _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content="ok"))],
            usage=_FakeUsage(),
        )


class _FakeChat:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.completions = _FakeCompletions(error=error)


class _FakeClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.chat = _FakeChat(error=error)


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-4.1", False),
        ("gpt-4o-mini", False),
        ("gpt-3.5-turbo", False),
        ("o1", True),
        ("o3-mini", True),
        ("o4-mini", True),
        ("gpt-5", True),
        ("gpt-5-thinking", True),
        ("custom-reasoning-model", True),
    ],
)
def test_model_uses_completion_tokens_param(model: str, expected: bool) -> None:
    assert _model_uses_completion_tokens_param(model) is expected


async def test_openai_provider_uses_max_tokens_for_legacy_model() -> None:
    client = _FakeClient()
    provider = OpenAiProvider(api_key="sk-test", model="gpt-4.1", client=client)

    await provider.complete([LlmMessage("user", "hi")], max_tokens=128)

    call = client.chat.completions.calls[0]
    assert call["max_tokens"] == 128
    assert "max_completion_tokens" not in call


async def test_openai_provider_uses_max_completion_tokens_for_reasoning_model() -> None:
    client = _FakeClient()
    provider = OpenAiProvider(api_key="sk-test", model="o4-mini", client=client)

    await provider.complete([LlmMessage("user", "hi")], max_tokens=128)

    call = client.chat.completions.calls[0]
    assert call["max_completion_tokens"] == 128
    assert "max_tokens" not in call
    assert "temperature" not in call


async def test_openai_provider_retries_when_max_tokens_unsupported() -> None:
    error = RuntimeError(
        "Error code: 400 - {'error': {'message': \"Unsupported parameter: 'max_tokens' "
        "is not supported with this model. Use 'max_completion_tokens' instead.\"}}"
    )
    client = _FakeClient(error=error)
    provider = OpenAiProvider(api_key="sk-test", model="gpt-4.1", client=client)

    await provider.complete([LlmMessage("user", "hi")], max_tokens=64)

    calls = client.chat.completions.calls
    assert len(calls) == 2
    assert calls[0]["max_tokens"] == 64
    assert calls[1]["max_completion_tokens"] == 64
    assert "max_tokens" not in calls[1]


async def test_openai_provider_retries_when_temperature_unsupported() -> None:
    error = RuntimeError(
        "Error code: 400 - {'error': {'message': \"Unsupported value: 'temperature' "
        'does not support 0.2 with this model. Only the default (1) value is supported.", '
        "'param': 'temperature', 'code': 'unsupported_value'}}"
    )
    client = _FakeClient(error=error)
    provider = OpenAiProvider(api_key="sk-test", model="gpt-4.1", client=client)

    await provider.complete([LlmMessage("user", "hi")], temperature=0.2, max_tokens=64)

    calls = client.chat.completions.calls
    assert len(calls) == 2
    assert calls[0]["temperature"] == 0.2
    assert "temperature" not in calls[1]
    assert calls[1]["max_tokens"] == 64


async def test_openai_provider_skips_token_limit_when_none() -> None:
    client = _FakeClient()
    provider = OpenAiProvider(api_key="sk-test", model="gpt-4.1", client=client)

    await provider.complete([LlmMessage("user", "hi")])

    call = client.chat.completions.calls[0]
    assert "max_tokens" not in call
    assert "max_completion_tokens" not in call
