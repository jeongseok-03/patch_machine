"""Core domain entities.

These types are the canonical contract between layers. They must stay free of
framework and I/O concerns. Adapters translate external payloads into these
structures; agents and orchestration read/produce them exclusively.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

IssueSourceKind = Literal["github", "discord"]
LlmRoute = Literal["cloud", "local"]
ReviewOutcome = Literal["approve", "needs_fix", "reject"]


class RepoRef(BaseModel):
    """Logical reference to a source repository."""

    model_config = ConfigDict(frozen=True)

    owner: str
    name: str
    default_branch: str = "main"

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class IssueEvent(BaseModel):
    """A normalized bug/feature request from any ingestion source."""

    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid4)
    source: IssueSourceKind
    external_id: str
    repo: RepoRef
    title: str
    body: str
    author: str
    labels: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, str] = Field(default_factory=dict)


class WorkSpec(BaseModel):
    """PM Agent output: what needs to change and why."""

    issue: IssueEvent
    target_modules: list[str] = Field(default_factory=list)
    related_logs: list[Path] = Field(default_factory=list)
    rationale_md: str = ""


class PatchProposal(BaseModel):
    """Developer Agent output."""

    workspec: WorkSpec
    unified_diff: str
    cot_md: str = ""
    iteration: int = 1


class ReviewVerdict(BaseModel):
    """Reviewer Agent output."""

    verdict: ReviewOutcome
    findings_md: str = ""
    suggested_fix_md: str = ""
