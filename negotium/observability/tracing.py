"""Tracer abstraction.

We keep this minimal so Phase 1 can ship without OpenTelemetry deps. In later
phases, swap ``NoopTracer`` for an OTLP-backed implementation without touching
call sites.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol


class Span(Protocol):
    def set_attribute(self, key: str, value: Any) -> None: ...

    def end(self) -> None: ...


class _NoopSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def end(self) -> None:
        return None


class Tracer(Protocol):
    @contextmanager
    def start(self, name: str, **attrs: Any) -> Iterator[Span]: ...


class NoopTracer:
    @contextmanager
    def start(self, name: str, **attrs: Any) -> Iterator[Span]:
        span = _NoopSpan()
        try:
            yield span
        finally:
            span.end()
