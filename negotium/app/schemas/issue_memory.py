"""Pydantic schemas for Issue Memory and MCP-compatible tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RawExternalEventPayload(BaseModel):
    id: str = ""
    provider: str = "manual"
    event_type: str = "manual"
    external_uri: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    received_at: str = ""
    processed_at: str = ""


class CanonicalIssuePayload(BaseModel):
    id: str = ""
    title: str
    summary: str = ""
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    issue_type: str = "bug"
    severity: str = "medium"
    status: str = "captured"
    affected_repos: list[str] = Field(default_factory=list)
    affected_features: list[str] = Field(default_factory=list)
    customer_impact: str = ""
    evidence: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    test_requirements: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    created_at: str = ""
    updated_at: str = ""


class IssueClusterPayload(BaseModel):
    id: str
    title: str
    summary: str = ""
    status: str = "captured"
    severity: str = "medium"
    canonical_issue_ids: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    affected_repos: list[str] = Field(default_factory=list)
    affected_features: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    created_at: str = ""
    updated_at: str = ""


class PatchCandidatePayload(BaseModel):
    id: str = ""
    cluster_id: str
    target_repo: str = "local"
    title: str
    summary: str = ""
    risk_level: str = "medium"
    status: str = "proposed"
    suggested_branch: str = ""
    created_at: str = ""
    updated_at: str = ""


class TestRequirementPayload(BaseModel):
    id: str = ""
    patch_candidate_id: str
    title: str
    requirement_type: str = "regression"
    given: str = ""
    when: str = ""
    then: str = ""
    priority: str = "medium"
    status: str = "proposed"
    source_refs: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class McpToolCallPayload(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpToolDescriptorPayload(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    required_permission: str = "work:read"


__all__ = [
    "CanonicalIssuePayload",
    "IssueClusterPayload",
    "McpToolCallPayload",
    "McpToolDescriptorPayload",
    "PatchCandidatePayload",
    "RawExternalEventPayload",
    "TestRequirementPayload",
]
