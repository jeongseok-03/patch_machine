"""Pytest fixtures shared across test packages."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from negotium.domain.entities import IssueEvent, RepoRef


@pytest.fixture
def sample_repo() -> RepoRef:
    return RepoRef(owner="acme", name="payments", default_branch="main")


@pytest.fixture
def sample_issue(sample_repo: RepoRef) -> IssueEvent:
    return IssueEvent(
        source="github",
        external_id="42",
        repo=sample_repo,
        title="결제 환불 시 idempotency key 가 재사용되어 중복 환불",
        body="최근 고객이 동일 트랜잭션으로 2회 환불된 사례가 있습니다. /api/refund 경로의 처리 로직을 확인해주세요.",
        author="qa-tester",
        labels=["bug", "negotium"],
    )


@pytest.fixture
def archive_tmp(tmp_path: Path) -> Iterator[Path]:
    target = tmp_path / "archive"
    target.mkdir()
    yield target
