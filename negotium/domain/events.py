"""Lightweight domain event envelope used by the in-process EventBus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from negotium.domain.entities import IssueEvent


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Transport envelope that carries a payload through the EventBus.

    Wrapping ``IssueEvent`` lets the bus append delivery metadata (attempt,
    trace id) without mutating the immutable domain entity.
    """

    payload: IssueEvent
    trace_id: UUID = field(default_factory=uuid4)
    attempt: int = 1
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
