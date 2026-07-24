"""In-process EventBus backed by ``asyncio.Queue``.

Phase 1 MVP uses a single-process queue with back-pressure. The public surface
(``publish``, ``consume``) is small enough that swapping in a RabbitMQ/Kafka
adapter later only requires re-implementing this class.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Final

from negotium.domain.entities import IssueEvent
from negotium.domain.events import DomainEvent
from negotium.observability import get_logger

_DEFAULT_QUEUE_SIZE: Final[int] = 100
_MAX_ATTEMPTS: Final[int] = 3


class QueueFullError(RuntimeError):
    """Raised when the bus cannot accept an event immediately.

    Adapters use this to surface a visible "still processing" message back to
    the user instead of dropping events silently.
    """


class EventBus:
    """Thin, typed wrapper over ``asyncio.Queue[DomainEvent]``.

    Separate ``publish_nowait`` and ``publish`` let synchronous adapters (like
    a FastAPI background task) report overflow immediately while async
    producers (discord bot) can await capacity.
    """

    def __init__(self, max_size: int = _DEFAULT_QUEUE_SIZE) -> None:
        self._queue: asyncio.Queue[DomainEvent] = asyncio.Queue(maxsize=max_size)
        self._log = get_logger(component="event_bus")
        self._max_size = max_size

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def capacity(self) -> int:
        return self._max_size

    def publish_nowait(self, event: IssueEvent) -> DomainEvent:
        envelope = DomainEvent(payload=event)
        try:
            self._queue.put_nowait(envelope)
        except asyncio.QueueFull as exc:
            self._log.warning(
                "event_bus.full",
                event_id=str(event.event_id),
                size=self._queue.qsize(),
                capacity=self._max_size,
            )
            raise QueueFullError("event bus at capacity") from exc
        self._log.info(
            "event_bus.enqueued",
            event_id=str(event.event_id),
            source=event.source,
            size=self._queue.qsize(),
        )
        return envelope

    async def publish(self, event: IssueEvent) -> DomainEvent:
        envelope = DomainEvent(payload=event)
        await self._queue.put(envelope)
        self._log.info(
            "event_bus.enqueued",
            event_id=str(event.event_id),
            source=event.source,
            size=self._queue.qsize(),
        )
        return envelope

    async def consume(self) -> AsyncIterator[DomainEvent]:
        """Yield events forever. Caller is responsible for handling exceptions
        and calling :meth:`retry` on failures that should be redelivered."""
        while True:
            envelope = await self._queue.get()
            try:
                yield envelope
            finally:
                self._queue.task_done()

    async def retry(self, envelope: DomainEvent) -> bool:
        """Re-enqueue ``envelope`` with an incremented attempt count.

        Returns False when the event has exceeded ``_MAX_ATTEMPTS`` and must be
        dead-lettered (the caller decides how to persist the failure).
        """
        if envelope.attempt >= _MAX_ATTEMPTS:
            self._log.error(
                "event_bus.exhausted",
                event_id=str(envelope.payload.event_id),
                attempts=envelope.attempt,
            )
            return False
        retry_envelope = DomainEvent(
            payload=envelope.payload,
            trace_id=envelope.trace_id,
            attempt=envelope.attempt + 1,
        )
        await self._queue.put(retry_envelope)
        self._log.info(
            "event_bus.retry",
            event_id=str(envelope.payload.event_id),
            attempt=retry_envelope.attempt,
        )
        return True
