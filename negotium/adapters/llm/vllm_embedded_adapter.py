"""In-process vLLM provider that loads the model directly via ``vllm.LLM``.

Unlike :mod:`negotium.adapters.llm.vllm_adapter` which speaks to an
OpenAI-compatible HTTP server, this adapter embeds the engine inside the
FastAPI process. It is the recommended path for local GPU machines because
it avoids container/network plumbing and lets us pass ``flash-attn`` /
``vllm`` settings as plain Python kwargs.

Engine startup is heavy (weights load + CUDA graph capture), so the engine
is constructed lazily on the first request and shared as a module-level
singleton across adapter instances. Because ``vllm.LLM.generate`` is a
blocking call, we offload it to a worker thread via ``asyncio.to_thread``
to keep the FastAPI event loop responsive.
"""

from __future__ import annotations

import asyncio
import gc
import os
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, cast

from negotium.domain.entities import LlmRoute
from negotium.domain.ports import (
    LlmMessage,
    LlmProvider,
    LlmResponse,
    flatten_message_text,
)
from negotium.observability import get_logger


class _ChatTokenizer(Protocol):
    def apply_chat_template(
        self,
        messages: Sequence[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> str: ...


class _Engine(Protocol):
    def generate(
        self,
        prompts: Sequence[str],
        sampling_params: Any,
    ) -> Sequence[Any]: ...


@dataclass
class _EngineBundle:
    engine: _Engine
    tokenizer: _ChatTokenizer
    sampling_params_cls: Any
    model: str


VllmEngineState = Literal["offline", "loading", "running", "error"]


class VllmEmbeddedError(RuntimeError):
    """Raised when the embedded vLLM engine cannot be started or used."""


_ENGINE: _EngineBundle | None = None
_ENGINE_LOCK = threading.Lock()
_ENGINE_STATE: VllmEngineState = "offline"
_ENGINE_ERROR = ""
_ENGINE_STARTED_AT: datetime | None = None
_ENGINE_READY_AT: datetime | None = None


def _friendly_engine_error(exc: BaseException) -> str:
    raw = str(exc)
    if "Cannot re-initialize CUDA in forked subprocess" in raw:
        return (
            "vLLM EngineCore가 fork 방식으로 CUDA를 다시 초기화하려다 실패했습니다. "
            "NG_VLLM_WORKER_MULTIPROC_METHOD=spawn 으로 실행해야 합니다. "
            "프로세스를 완전히 종료한 뒤 다시 시작하세요."
        )
    return raw


def _default_engine_factory(
    *,
    model: str,
    dtype: str,
    max_model_len: int,
    gpu_memory_utilization: float,
    enforce_eager: bool,
    trust_remote_code: bool,
    worker_multiproc_method: str,
) -> _EngineBundle:
    """Build the real :class:`vllm.LLM` engine plus its chat tokenizer.

    Imports are local so importing this module never triggers a CUDA load.
    """

    # vLLM starts an EngineCore subprocess. With uvicorn/FastAPI, CUDA can be
    # touched before that subprocess exists; fork then fails with
    # "Cannot re-initialize CUDA in forked subprocess". Force spawn before vLLM import.
    os.environ["VLLM_WORKER_MULTIPROC_METHOD"] = worker_multiproc_method

    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams

    engine = LLM(
        model=model,
        dtype=cast(Any, dtype),
        max_model_len=max_model_len,
        gpu_memory_utilization=gpu_memory_utilization,
        enforce_eager=enforce_eager,
        trust_remote_code=trust_remote_code,
    )
    tokenizer = AutoTokenizer.from_pretrained(model, trust_remote_code=trust_remote_code)
    return _EngineBundle(
        engine=cast(_Engine, engine),
        tokenizer=cast(_ChatTokenizer, tokenizer),
        sampling_params_cls=SamplingParams,
        model=model,
    )


class VllmEmbeddedProvider(LlmProvider):
    """:class:`LlmProvider` that runs vLLM inside the current Python process."""

    def __init__(
        self,
        *,
        model: str,
        dtype: str = "bfloat16",
        max_model_len: int = 8192,
        gpu_memory_utilization: float = 0.9,
        enforce_eager: bool = False,
        trust_remote_code: bool = True,
        worker_multiproc_method: str = "spawn",
        top_p: float = 0.95,
        engine_factory: Any = None,
    ) -> None:
        self._model = model
        self._dtype = dtype
        self._max_model_len = max_model_len
        self._gpu_memory_utilization = gpu_memory_utilization
        self._enforce_eager = enforce_eager
        self._trust_remote_code = trust_remote_code
        self._worker_multiproc_method = worker_multiproc_method
        self._top_p = top_p
        self._engine_factory = engine_factory or _default_engine_factory
        self._log = get_logger(component="llm.vllm.embedded", model=model)

    async def preload(self) -> None:
        """Load the vLLM engine before the first chat request arrives."""

        await asyncio.to_thread(self._ensure_engine)

    def unload(self) -> None:
        """Release the in-process engine and ask CUDA to return cached memory."""

        reset_engine_for_tests(clear_cuda=True)

    def configure_model(self, model: str) -> None:
        next_model = model.strip()
        if not next_model or next_model == self._model:
            return
        self.unload()
        self._model = next_model
        self._log = get_logger(component="llm.vllm.embedded", model=next_model)

    def status(self) -> dict[str, object]:
        return {
            "mode": "embedded",
            "state": _ENGINE_STATE,
            "model": self._model,
            "loaded": _ENGINE is not None and _ENGINE.model == self._model,
            "error": _ENGINE_ERROR,
            "started_at": _ENGINE_STARTED_AT.isoformat() if _ENGINE_STARTED_AT else "",
            "ready_at": _ENGINE_READY_AT.isoformat() if _ENGINE_READY_AT else "",
        }

    async def complete(
        self,
        messages: Sequence[LlmMessage],
        *,
        route: LlmRoute = "local",
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LlmResponse:
        bundle = await asyncio.to_thread(self._ensure_engine)
        prompt = bundle.tokenizer.apply_chat_template(
            [{"role": m.role, "content": flatten_message_text(m.content)} for m in messages],
            tokenize=False,
            add_generation_prompt=True,
        )
        sampling_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "top_p": self._top_p,
        }
        if max_tokens is not None:
            sampling_kwargs["max_tokens"] = max_tokens
        params = bundle.sampling_params_cls(**sampling_kwargs)

        started = time.perf_counter()
        outputs = await asyncio.to_thread(bundle.engine.generate, [prompt], params)
        latency_ms = int((time.perf_counter() - started) * 1000)

        request = outputs[0]
        completion = request.outputs[0]
        text = (getattr(completion, "text", "") or "").strip()
        prompt_tokens = len(getattr(request, "prompt_token_ids", []) or [])
        completion_tokens = len(getattr(completion, "token_ids", []) or [])
        self._log.info(
            "llm.vllm.embedded.complete",
            route=route,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return LlmResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            route=route,
            model=bundle.model,
        )

    def _ensure_engine(self) -> _EngineBundle:
        global _ENGINE, _ENGINE_ERROR, _ENGINE_READY_AT, _ENGINE_STARTED_AT, _ENGINE_STATE
        if _ENGINE is not None and _ENGINE.model == self._model:
            _ENGINE_STATE = "running"
            return _ENGINE
        with _ENGINE_LOCK:
            if _ENGINE is not None and _ENGINE.model == self._model:
                _ENGINE_STATE = "running"
                return _ENGINE
            _ENGINE_STATE = "loading"
            _ENGINE_ERROR = ""
            _ENGINE_STARTED_AT = datetime.now(UTC)
            _ENGINE_READY_AT = None
            self._log.info(
                "llm.vllm.embedded.boot",
                dtype=self._dtype,
                max_model_len=self._max_model_len,
                gpu_memory_utilization=self._gpu_memory_utilization,
                enforce_eager=self._enforce_eager,
            )
            try:
                bundle = self._engine_factory(
                    model=self._model,
                    dtype=self._dtype,
                    max_model_len=self._max_model_len,
                    gpu_memory_utilization=self._gpu_memory_utilization,
                    enforce_eager=self._enforce_eager,
                    trust_remote_code=self._trust_remote_code,
                    worker_multiproc_method=self._worker_multiproc_method,
                )
            except Exception as exc:
                _ENGINE_STATE = "error"
                _ENGINE_ERROR = _friendly_engine_error(exc)
                raise VllmEmbeddedError(_ENGINE_ERROR) from exc
            else:
                _ENGINE = bundle
                _ENGINE_STATE = "running"
                _ENGINE_READY_AT = datetime.now(UTC)
                return bundle


def reset_engine_for_tests(*, clear_cuda: bool = False) -> None:
    """Test helper to force a re-init on the next call."""

    global _ENGINE, _ENGINE_ERROR, _ENGINE_READY_AT, _ENGINE_STARTED_AT, _ENGINE_STATE
    with _ENGINE_LOCK:
        _ENGINE = None
        _ENGINE_STATE = "offline"
        _ENGINE_ERROR = ""
        _ENGINE_STARTED_AT = None
        _ENGINE_READY_AT = None
    gc.collect()
    if clear_cuda:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
