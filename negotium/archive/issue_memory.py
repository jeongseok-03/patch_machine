"""File-backed Issue Memory Engine records."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import portalocker

ProviderName = Literal["github", "discord", "notion", "manual", "memory"]


@dataclass(frozen=True)
class RawExternalEvent:
    id: str
    provider: ProviderName
    event_type: str
    external_uri: str
    payload: dict[str, Any]
    received_at: str = ""
    processed_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> RawExternalEvent:
        return cls(
            id=str(payload.get("id") or uuid4()),
            provider=_provider(payload.get("provider")),
            event_type=str(payload.get("event_type") or "manual"),
            external_uri=str(payload.get("external_uri") or ""),
            payload=dict(payload.get("payload") or {}),
            received_at=str(payload.get("received_at") or datetime.now(UTC).isoformat()),
            processed_at=str(payload.get("processed_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "event_type": self.event_type,
            "external_uri": self.external_uri,
            "payload": self.payload,
            "received_at": self.received_at,
            "processed_at": self.processed_at,
        }


@dataclass(frozen=True)
class CanonicalIssue:
    id: str
    title: str
    summary: str = ""
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    issue_type: str = "bug"
    severity: str = "medium"
    status: str = "captured"
    affected_repos: list[str] = field(default_factory=list)
    affected_features: list[str] = field(default_factory=list)
    customer_impact: str = ""
    evidence: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    test_requirements: list[str] = field(default_factory=list)
    confidence: float = 0.5
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> CanonicalIssue:
        now = datetime.now(UTC).isoformat()
        return cls(
            id=str(payload.get("id") or uuid4()),
            title=str(payload.get("title") or "Untitled issue"),
            summary=str(payload.get("summary") or ""),
            source_refs=[item for item in payload.get("source_refs", []) if isinstance(item, dict)],
            issue_type=str(payload.get("issue_type") or "bug"),
            severity=str(payload.get("severity") or "medium"),
            status=str(payload.get("status") or "captured"),
            affected_repos=[str(item) for item in payload.get("affected_repos", [])],
            affected_features=[str(item) for item in payload.get("affected_features", [])],
            customer_impact=str(payload.get("customer_impact") or ""),
            evidence=[str(item) for item in payload.get("evidence", [])],
            open_questions=[str(item) for item in payload.get("open_questions", [])],
            test_requirements=[str(item) for item in payload.get("test_requirements", [])],
            confidence=float(payload.get("confidence", 0.5) or 0.5),
            created_at=str(payload.get("created_at") or now),
            updated_at=now,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class IssueCluster:
    id: str
    title: str
    summary: str = ""
    status: str = "captured"
    severity: str = "medium"
    canonical_issue_ids: list[str] = field(default_factory=list)
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    affected_repos: list[str] = field(default_factory=list)
    affected_features: list[str] = field(default_factory=list)
    confidence: float = 0.5
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> IssueCluster:
        now = datetime.now(UTC).isoformat()
        return cls(
            id=str(payload.get("id") or uuid4()),
            title=str(payload.get("title") or "Issue Cluster"),
            summary=str(payload.get("summary") or ""),
            status=str(payload.get("status") or "captured"),
            severity=str(payload.get("severity") or "medium"),
            canonical_issue_ids=[str(item) for item in payload.get("canonical_issue_ids", [])],
            source_refs=[item for item in payload.get("source_refs", []) if isinstance(item, dict)],
            affected_repos=[str(item) for item in payload.get("affected_repos", [])],
            affected_features=[str(item) for item in payload.get("affected_features", [])],
            confidence=float(payload.get("confidence", 0.5) or 0.5),
            created_at=str(payload.get("created_at") or now),
            updated_at=now,
        )

    def with_issue(self, issue: CanonicalIssue, *, confidence: float) -> IssueCluster:
        ids = list(dict.fromkeys([*self.canonical_issue_ids, issue.id]))
        refs = [*self.source_refs, *issue.source_refs]
        repos = list(dict.fromkeys([*self.affected_repos, *issue.affected_repos]))
        features = list(dict.fromkeys([*self.affected_features, *issue.affected_features]))
        severity = _max_severity(self.severity, issue.severity)
        return IssueCluster.create(
            **{
                **self.to_dict(),
                "canonical_issue_ids": ids,
                "source_refs": refs,
                "affected_repos": repos,
                "affected_features": features,
                "severity": severity,
                "confidence": max(self.confidence, confidence),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class PatchCandidate:
    id: str
    cluster_id: str
    target_repo: str
    title: str
    summary: str = ""
    risk_level: str = "medium"
    status: str = "proposed"
    suggested_branch: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> PatchCandidate:
        now = datetime.now(UTC).isoformat()
        return cls(
            id=str(payload.get("id") or uuid4()),
            cluster_id=str(payload.get("cluster_id") or ""),
            target_repo=str(payload.get("target_repo") or "local"),
            title=str(payload.get("title") or "Patch Candidate"),
            summary=str(payload.get("summary") or ""),
            risk_level=str(payload.get("risk_level") or "medium"),
            status=str(payload.get("status") or "proposed"),
            suggested_branch=str(payload.get("suggested_branch") or ""),
            created_at=str(payload.get("created_at") or now),
            updated_at=now,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class TestRequirement:
    id: str
    patch_candidate_id: str
    title: str
    requirement_type: str = "regression"
    given: str = ""
    when: str = ""
    then: str = ""
    priority: str = "medium"
    status: str = "proposed"
    source_refs: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, **payload: Any) -> TestRequirement:
        now = datetime.now(UTC).isoformat()
        return cls(
            id=str(payload.get("id") or uuid4()),
            patch_candidate_id=str(payload.get("patch_candidate_id") or ""),
            title=str(payload.get("title") or "Test Requirement"),
            requirement_type=str(payload.get("requirement_type") or "regression"),
            given=str(payload.get("given") or payload.get("given_text") or ""),
            when=str(payload.get("when") or payload.get("when_text") or ""),
            then=str(payload.get("then") or payload.get("then_text") or ""),
            priority=str(payload.get("priority") or "medium"),
            status=str(payload.get("status") or "proposed"),
            source_refs=[str(item) for item in payload.get("source_refs", [])],
            created_at=str(payload.get("created_at") or now),
            updated_at=now,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class IssueMemoryStore:
    def __init__(self, archive_dir: Path) -> None:
        root = archive_dir / "issue_memory"
        self._raw = root / "raw_events"
        self._issues = root / "canonical_issues"
        self._clusters = root / "clusters"
        self._candidates = root / "patch_candidates"
        self._requirements = root / "test_requirements"

    def save_raw_event(self, event: RawExternalEvent) -> RawExternalEvent:
        return self._save(self._raw, event.id, event)

    def save_issue(self, issue: CanonicalIssue) -> CanonicalIssue:
        return self._save(self._issues, issue.id, issue)

    def save_cluster(self, cluster: IssueCluster) -> IssueCluster:
        return self._save(self._clusters, cluster.id, cluster)

    def save_patch_candidate(self, candidate: PatchCandidate) -> PatchCandidate:
        return self._save(self._candidates, candidate.id, candidate)

    def save_test_requirement(self, requirement: TestRequirement) -> TestRequirement:
        return self._save(self._requirements, requirement.id, requirement)

    def list_issues(self) -> list[dict[str, Any]]:
        return self._list(self._issues, CanonicalIssue)

    def list_clusters(self) -> list[dict[str, Any]]:
        return self._list(self._clusters, IssueCluster)

    def list_patch_candidates(self) -> list[dict[str, Any]]:
        return self._list(self._candidates, PatchCandidate)

    def list_test_requirements(self, *, patch_candidate_id: str = "") -> list[dict[str, Any]]:
        requirements = self._list(self._requirements, TestRequirement)
        if patch_candidate_id:
            requirements = [
                item
                for item in requirements
                if item.get("patch_candidate_id") == patch_candidate_id
            ]
        return requirements

    def read_cluster(self, cluster_id: str) -> IssueCluster:
        return self._read(self._clusters, cluster_id, IssueCluster)

    def read_patch_candidate(self, candidate_id: str) -> PatchCandidate:
        return self._read(self._candidates, candidate_id, PatchCandidate)

    def read_test_requirement(self, requirement_id: str) -> TestRequirement:
        return self._read(self._requirements, requirement_id, TestRequirement)

    def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        needle = query.strip().lower()
        clusters = self.list_clusters()
        if needle:
            clusters = [
                item
                for item in clusters
                if needle in str(item.get("title", "")).lower()
                or needle in str(item.get("summary", "")).lower()
                or any(
                    needle in str(feature).lower() for feature in item.get("affected_features", [])
                )
            ]
        clusters.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return clusters[: max(1, min(limit, 50))]

    def _save(self, folder: Path, item_id: str, record: Any) -> Any:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{item_id}.json"
        with portalocker.Lock(path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump(record.to_dict(), fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return record

    def _list(self, folder: Path, factory: Any) -> list[dict[str, Any]]:
        records: list[Any] = []
        for path in sorted(folder.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                records.append(factory.create(**payload))
        records.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_dict() for item in records]

    def _read(self, folder: Path, item_id: str, factory: Any) -> Any:
        path = folder / f"{item_id}.json"
        if not path.exists():
            raise ValueError("issue memory record not found")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("issue memory record is invalid")
        return factory.create(**payload)


def _provider(value: object) -> ProviderName:
    if value in {"github", "discord", "notion", "manual", "memory"}:
        return value  # type: ignore[return-value]
    return "manual"


def _max_severity(left: str, right: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    return left if order.get(left, 1) >= order.get(right, 1) else right
