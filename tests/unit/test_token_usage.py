"""Token usage limits and recording tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from negotium.archive.token_usage import (
    TokenLimitConfig,
    TokenLimitExceededError,
    TokenUsageStore,
)


def test_token_usage_records_and_summarizes(archive_tmp: Path) -> None:
    store = TokenUsageStore(archive_tmp)
    moment = datetime(2026, 5, 5, 9, 0, tzinfo=UTC)

    store.record(
        provider="openai",
        model="gpt-4o-mini",
        task="chat",
        actor="owner",
        prompt_tokens=120,
        completion_tokens=80,
        now=moment,
    )
    store.record(
        provider="openai",
        model="gpt-4o-mini",
        task="document_generation",
        actor="owner",
        prompt_tokens=600,
        completion_tokens=400,
        now=moment,
    )

    summary = store.summary(now=moment)
    assert summary.daily_total == 1200
    assert summary.monthly_total == 1200
    assert summary.by_provider["openai"] == 1200
    assert summary.by_task["chat"] == 200


def test_token_usage_per_request_limit_blocks_large_request(archive_tmp: Path) -> None:
    store = TokenUsageStore(archive_tmp)
    store.write_limits(
        TokenLimitConfig(
            enforcement_enabled=True,
            per_request_max_tokens=1000,
            daily_total_tokens=10_000,
            monthly_total_tokens=100_000,
        )
    )

    with pytest.raises(TokenLimitExceededError) as excinfo:
        store.check_limits(attempted_tokens=1500)
    assert excinfo.value.scope == "per_request"


def test_token_usage_daily_limit_blocks_after_threshold(archive_tmp: Path) -> None:
    store = TokenUsageStore(archive_tmp)
    moment = datetime(2026, 5, 5, 9, 0, tzinfo=UTC)
    store.write_limits(
        TokenLimitConfig(
            enforcement_enabled=True,
            per_request_max_tokens=10_000,
            daily_total_tokens=1500,
            monthly_total_tokens=10_000,
        )
    )
    store.record(
        provider="openai",
        model="gpt-4o-mini",
        task="chat",
        actor="owner",
        prompt_tokens=600,
        completion_tokens=600,
        now=moment,
    )

    with pytest.raises(TokenLimitExceededError) as excinfo:
        store.check_limits(attempted_tokens=500, now=moment)
    assert excinfo.value.scope == "daily"


def test_token_usage_disabled_enforcement_allows_requests(archive_tmp: Path) -> None:
    store = TokenUsageStore(archive_tmp)
    store.write_limits(
        TokenLimitConfig(
            enforcement_enabled=False,
            per_request_max_tokens=1,
            daily_total_tokens=1,
            monthly_total_tokens=1,
        )
    )

    store.check_limits(attempted_tokens=10_000)
