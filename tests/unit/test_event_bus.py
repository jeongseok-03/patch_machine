"""EventBus back-pressure and retry semantics."""

from __future__ import annotations

import asyncio

import pytest

from negotium.application.event_bus import EventBus, QueueFullError
from negotium.domain.entities import IssueEvent, RepoRef


def _make_event(idx: int) -> IssueEvent:
    return IssueEvent(
        source="github",
        external_id=str(idx),
        repo=RepoRef(owner="acme", name="payments"),
        title=f"bug {idx}",
        body="",
        author="user",
    )


async def test_publish_nowait_raises_when_full() -> None:
    bus = EventBus(max_size=1)
    bus.publish_nowait(_make_event(1))
    with pytest.raises(QueueFullError):
        bus.publish_nowait(_make_event(2))


async def test_retry_increments_attempt_until_exhausted() -> None:
    bus = EventBus(max_size=8)
    envelope = bus.publish_nowait(_make_event(1))

    async def drain() -> list[int]:
        async for delivered in bus.consume():
            if delivered.attempt < 3:
                assert await bus.retry(delivered) is True
                continue
            assert await bus.retry(delivered) is False
            return [delivered.attempt]
        return []

    attempts = await asyncio.wait_for(drain(), timeout=1.0)
    assert attempts == [3]
    assert envelope.attempt == 1
