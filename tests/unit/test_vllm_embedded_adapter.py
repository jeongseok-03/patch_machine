"""Unit tests for the in-process VllmEmbeddedProvider."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from negotium.adapters.llm.vllm_embedded_adapter import (
    VllmEmbeddedProvider,
    _EngineBundle,
    reset_engine_for_tests,
)
from negotium.domain.ports import LlmMessage


@dataclass
class _FakeSamplingParams:
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int | None = None


@dataclass
class _FakeCompletion:
    text: str
    token_ids: list[int]


@dataclass
class _FakeRequestOutput:
    prompt_token_ids: list[int]
    outputs: list[_FakeCompletion]


class _FakeEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], _FakeSamplingParams]] = []

    def generate(self, prompts: Sequence[str], params: Any) -> Sequence[_FakeRequestOutput]:
        self.calls.append((list(prompts), params))
        return [
            _FakeRequestOutput(
                prompt_token_ids=[1, 2, 3, 4],
                outputs=[_FakeCompletion(text="hello world", token_ids=[10, 11])],
            )
        ]


class _FakeTokenizer:
    def __init__(self) -> None:
        self.last_messages: list[dict[str, str]] | None = None

    def apply_chat_template(
        self,
        messages: Sequence[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> str:
        assert tokenize is False
        assert add_generation_prompt is True
        self.last_messages = list(messages)
        return "PROMPT::" + "|".join(f"{m['role']}={m['content']}" for m in messages)


def _make_factory(engine: _FakeEngine, tokenizer: _FakeTokenizer) -> Any:
    def factory(**_kwargs: Any) -> _EngineBundle:
        return _EngineBundle(
            engine=engine,
            tokenizer=tokenizer,
            sampling_params_cls=_FakeSamplingParams,
            model=_kwargs["model"],
        )

    return factory


async def test_embedded_provider_runs_chat_template_and_generate() -> None:
    reset_engine_for_tests()
    engine = _FakeEngine()
    tokenizer = _FakeTokenizer()
    provider = VllmEmbeddedProvider(
        model="Qwen/Qwen3-4B",
        engine_factory=_make_factory(engine, tokenizer),
    )

    response = await provider.complete(
        [LlmMessage("system", "you are bpa"), LlmMessage("user", "hi")],
        route="local",
        temperature=0.2,
        max_tokens=64,
    )

    assert response.text == "hello world"
    assert response.prompt_tokens == 4
    assert response.completion_tokens == 2
    assert response.route == "local"
    assert response.model == "Qwen/Qwen3-4B"

    assert tokenizer.last_messages == [
        {"role": "system", "content": "you are bpa"},
        {"role": "user", "content": "hi"},
    ]
    assert len(engine.calls) == 1
    prompts, params = engine.calls[0]
    assert prompts == ["PROMPT::system=you are bpa|user=hi"]
    assert params.temperature == 0.2
    assert params.max_tokens == 64
    reset_engine_for_tests()


async def test_embedded_provider_reuses_engine_for_same_model() -> None:
    reset_engine_for_tests()
    engine = _FakeEngine()
    tokenizer = _FakeTokenizer()
    factory_calls = {"n": 0}

    def factory(**kwargs: Any) -> _EngineBundle:
        factory_calls["n"] += 1
        return _EngineBundle(
            engine=engine,
            tokenizer=tokenizer,
            sampling_params_cls=_FakeSamplingParams,
            model=kwargs["model"],
        )

    provider = VllmEmbeddedProvider(model="Qwen/Qwen3-4B", engine_factory=factory)

    await provider.complete([LlmMessage("user", "a")], route="local")
    await provider.complete([LlmMessage("user", "b")], route="local")

    assert factory_calls["n"] == 1
    reset_engine_for_tests()
