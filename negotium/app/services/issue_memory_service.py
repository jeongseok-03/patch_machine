"""Issue Memory normalization, clustering, and MCP-compatible tool helpers."""

from __future__ import annotations

import re
from typing import Any

from negotium.app.services.context_firewall_service import sanitize_context
from negotium.archive.issue_memory import (
    CanonicalIssue,
    IssueCluster,
    IssueMemoryStore,
    PatchCandidate,
    RawExternalEvent,
    TestRequirement,
)
from negotium.domain.entities import IssueEvent

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"(?i)bearer\s+[a-z0-9._\-]+"),
]

HIGH_RISK_KEYWORDS = {"auth", "payment", "session", "delete", "permission"}
FEATURE_KEYWORDS = {
    "auth",
    "login",
    "payment",
    "billing",
    "session",
    "memory",
    "patchops",
    "mcp",
    "github",
    "discord",
    "notion",
    "test",
}


def redact_issue_payload(value: Any) -> Any:
    return _normalize_secret_placeholder(
        sanitize_context(value, destination="local_storage", task_type="issue_memory").sanitized
    )


def _normalize_secret_placeholder(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(
            r"\[REDACTED_[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|URL|ASSIGNMENT)[A-Z0-9_]*\]",
            "[REDACTED_SECRET]",
            value,
        )
    if isinstance(value, list):
        return [_normalize_secret_placeholder(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_secret_placeholder(item) for key, item in value.items()}
    return value


def _legacy_redact_issue_payload(value: Any) -> Any:
    if isinstance(value, str):
        text = value
        for pattern in SECRET_PATTERNS:
            text = pattern.sub("[REDACTED_SECRET]", text)
        return text
    if isinstance(value, list):
        return [redact_issue_payload(item) for item in value]
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if re.search(r"(?i)(api[_-]?key|token|secret|password)", key_text):
                redacted[key_text] = "[REDACTED_SECRET]"
            else:
                redacted[key_text] = redact_issue_payload(item)
        return redacted
    return value


def capture_issue_event(store: IssueMemoryStore, event: IssueEvent) -> dict[str, Any]:
    raw = RawExternalEvent.create(
        provider=event.source,
        event_type="issue_event",
        external_uri=_external_uri(event),
        payload=redact_issue_payload(event.model_dump(mode="json")),
    )
    store.save_raw_event(raw)
    issue = canonicalize_issue_event(event, raw_event_id=raw.id)
    store.save_issue(issue)
    cluster = upsert_cluster_for_issue(store, issue)
    candidate = ensure_patch_candidate(store, cluster)
    requirement = ensure_test_requirement(store, candidate, cluster)
    return {
        "raw_event": raw.to_dict(),
        "canonical_issue": issue.to_dict(),
        "cluster": cluster.to_dict(),
        "patch_candidate": candidate.to_dict(),
        "test_requirement": requirement.to_dict(),
    }


def capture_manual_issue(store: IssueMemoryStore, payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = redact_issue_payload(payload)
    raw = RawExternalEvent.create(
        provider=str(sanitized.get("provider") or "manual"),
        event_type=str(sanitized.get("event_type") or "manual_issue"),
        external_uri=str(sanitized.get("external_uri") or ""),
        payload=sanitized,
    )
    store.save_raw_event(raw)
    issue = canonicalize_manual_payload(sanitized, raw_event_id=raw.id)
    store.save_issue(issue)
    cluster = upsert_cluster_for_issue(store, issue)
    candidate = ensure_patch_candidate(store, cluster)
    requirement = ensure_test_requirement(store, candidate, cluster)
    return {
        "raw_event": raw.to_dict(),
        "canonical_issue": issue.to_dict(),
        "cluster": cluster.to_dict(),
        "patch_candidate": candidate.to_dict(),
        "test_requirement": requirement.to_dict(),
    }


def canonicalize_issue_event(event: IssueEvent, *, raw_event_id: str) -> CanonicalIssue:
    repo = event.repo.full_name
    text = f"{event.title}\n{event.body}\n{' '.join(event.labels)}"
    return CanonicalIssue.create(
        title=event.title,
        summary=_excerpt(event.body or event.title),
        source_refs=[
            {
                "provider": event.source,
                "external_id": event.external_id,
                "uri": _external_uri(event),
                "raw_event_id": raw_event_id,
            }
        ],
        issue_type=_infer_issue_type(text),
        severity=_infer_severity(text),
        affected_repos=[repo],
        affected_features=_extract_features(text),
        evidence=[_excerpt(event.body or event.title, limit=280)],
        open_questions=_default_questions(text),
        test_requirements=[_default_requirement(event.title)],
        confidence=0.72,
    )


def canonicalize_manual_payload(payload: dict[str, Any], *, raw_event_id: str) -> CanonicalIssue:
    title = str(payload.get("title") or payload.get("summary") or "Manual issue")
    body = str(payload.get("body") or payload.get("summary") or "")
    source_refs = payload.get("source_refs")
    if not isinstance(source_refs, list):
        source_refs = [
            {
                "provider": str(payload.get("provider") or "manual"),
                "uri": str(payload.get("external_uri") or ""),
                "raw_event_id": raw_event_id,
            }
        ]
    return CanonicalIssue.create(
        title=title,
        summary=_excerpt(body or title),
        source_refs=source_refs,
        issue_type=str(payload.get("issue_type") or _infer_issue_type(f"{title}\n{body}")),
        severity=str(payload.get("severity") or _infer_severity(f"{title}\n{body}")),
        affected_repos=[str(item) for item in payload.get("affected_repos", ["local"])],
        affected_features=_extract_features(f"{title}\n{body}"),
        evidence=[_excerpt(body or title, limit=280)],
        open_questions=_default_questions(f"{title}\n{body}"),
        test_requirements=[_default_requirement(title)],
        confidence=0.62,
    )


def upsert_cluster_for_issue(store: IssueMemoryStore, issue: CanonicalIssue) -> IssueCluster:
    match = find_cluster_match(store, issue)
    if match is None:
        cluster = IssueCluster.create(
            title=issue.title,
            summary=issue.summary,
            status="open",
            severity=issue.severity,
            canonical_issue_ids=[issue.id],
            source_refs=issue.source_refs,
            affected_repos=issue.affected_repos,
            affected_features=issue.affected_features,
            confidence=issue.confidence,
        )
    else:
        cluster = match.with_issue(issue, confidence=max(match.confidence, issue.confidence))
    return store.save_cluster(cluster)


def find_cluster_match(store: IssueMemoryStore, issue: CanonicalIssue) -> IssueCluster | None:
    best: tuple[float, IssueCluster] | None = None
    for payload in store.list_clusters():
        cluster = IssueCluster.create(**payload)
        score = _cluster_score(cluster, issue)
        if score >= 0.52 and (best is None or score > best[0]):
            best = (score, cluster)
    return best[1] if best else None


def ensure_patch_candidate(
    store: IssueMemoryStore, cluster: IssueCluster, *, target_repo: str = ""
) -> PatchCandidate:
    repo = target_repo or (cluster.affected_repos[0] if cluster.affected_repos else "local")
    for payload in store.list_patch_candidates():
        if payload.get("cluster_id") == cluster.id and payload.get("target_repo") == repo:
            return PatchCandidate.create(**payload)
    candidate = PatchCandidate.create(
        cluster_id=cluster.id,
        target_repo=repo,
        title=f"Patch: {cluster.title}",
        summary=cluster.summary,
        risk_level=_risk_from_cluster(cluster),
        suggested_branch=f"patchops/{cluster.id[:8]}",
    )
    return store.save_patch_candidate(candidate)


def ensure_test_requirement(
    store: IssueMemoryStore, candidate: PatchCandidate, cluster: IssueCluster
) -> TestRequirement:
    existing = store.list_test_requirements(patch_candidate_id=candidate.id)
    if existing:
        return TestRequirement.create(**existing[0])
    requirement = TestRequirement.create(
        patch_candidate_id=candidate.id,
        title=f"Regression coverage for {cluster.title}",
        requirement_type="regression",
        given="A user exercises the affected workflow.",
        when="The reported issue condition is reproduced.",
        then="The workflow completes without the reported failure and preserves existing behavior.",
        priority="high" if candidate.risk_level in {"high", "critical"} else "medium",
        source_refs=[
            str(ref.get("uri") or ref.get("external_id") or "") for ref in cluster.source_refs
        ],
    )
    return store.save_test_requirement(requirement)


def search_issue_memory(store: IssueMemoryStore, query: str, *, limit: int = 10) -> dict[str, Any]:
    clusters = store.search(query, limit=limit)
    candidate_by_cluster: dict[str, list[dict[str, Any]]] = {}
    for candidate in store.list_patch_candidates():
        candidate_by_cluster.setdefault(str(candidate.get("cluster_id")), []).append(candidate)
    for cluster in clusters:
        candidates = candidate_by_cluster.get(str(cluster.get("id")), [])
        cluster["patch_candidates"] = candidates
        cluster["test_requirements"] = [
            requirement
            for candidate in candidates
            for requirement in store.list_test_requirements(
                patch_candidate_id=str(candidate.get("id"))
            )
        ]
    return {"clusters": clusters, "total": len(clusters)}


def issue_memory_tool_descriptors() -> list[dict[str, Any]]:
    return [
        _tool(
            "memory.search_issues",
            "Search canonical issue clusters.",
            {"query": "string", "filters": "object", "limit": "number"},
            "work:read",
        ),
        _tool(
            "memory.get_issue_cluster",
            "Read one issue cluster by id.",
            {"cluster_id": "string"},
            "work:read",
        ),
        _tool(
            "memory.create_patch_candidate",
            "Create a patch candidate for an issue cluster.",
            {
                "cluster_id": "string",
                "target_repo": "string",
                "title": "string",
                "risk_level": "string",
            },
            "memory:write",
        ),
        _tool(
            "memory.create_test_requirement",
            "Create a proposed test requirement.",
            {
                "patch_candidate_id": "string",
                "title": "string",
                "requirement_type": "string",
                "given": "string",
                "when": "string",
                "then": "string",
                "priority": "string",
            },
            "memory:write",
        ),
        _tool(
            "memory.link_source",
            "Capture a manual source reference into Issue Memory.",
            {
                "title": "string",
                "summary": "string",
                "external_uri": "string",
                "provider": "string",
            },
            "memory:write",
        ),
        _tool(
            "memory.record_resolution",
            "Mark a cluster as resolved with summary evidence.",
            {"cluster_id": "string", "summary": "string"},
            "memory:write",
        ),
    ]


def _tool(
    name: str, description: str, properties: dict[str, str], permission: str
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "required_permission": permission,
        "input_schema": {
            "type": "object",
            "properties": {key: {"type": value} for key, value in properties.items()},
        },
    }


def _external_uri(event: IssueEvent) -> str:
    url = event.metadata.get("url") or event.metadata.get("html_url")
    if url:
        return url
    return f"{event.source}:{event.repo.full_name}:{event.external_id}"


def _infer_issue_type(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ["incident", "outage", "장애"]):
        return "incident"
    if any(word in lower for word in ["support", "customer", "문의"]):
        return "support"
    if any(word in lower for word in ["feature", "request", "개선"]):
        return "feature"
    return "bug"


def _infer_severity(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ["critical", "outage", "data loss", "security", "leak"]):
        return "critical"
    if any(
        word in lower for word in ["high", "auth", "payment", "permission", "delete", "session"]
    ):
        return "high"
    if any(word in lower for word in ["minor", "typo", "low"]):
        return "low"
    return "medium"


def _extract_features(text: str) -> list[str]:
    lower = text.lower()
    features = [keyword for keyword in FEATURE_KEYWORDS if keyword in lower]
    return sorted(set(features))


def _cluster_score(cluster: IssueCluster, issue: CanonicalIssue) -> float:
    score = 0.0
    if set(cluster.affected_repos) & set(issue.affected_repos):
        score += 0.35
    if set(cluster.affected_features) & set(issue.affected_features):
        score += 0.35
    title_words = _words(cluster.title) & _words(issue.title)
    score += min(0.3, len(title_words) * 0.06)
    return score


def _risk_from_cluster(cluster: IssueCluster) -> str:
    text = f"{cluster.title} {cluster.summary} {' '.join(cluster.affected_features)}".lower()
    if cluster.severity in {"critical", "high"} or any(word in text for word in HIGH_RISK_KEYWORDS):
        return "high"
    return cluster.severity if cluster.severity in {"low", "medium"} else "medium"


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-zA-Z0-9가-힣_]+", text.lower()) if len(word) >= 3}


def _excerpt(text: str, *, limit: int = 420) -> str:
    compact = " ".join(text.split())
    return compact[:limit]


def _default_questions(text: str) -> list[str]:
    questions = ["Which user workflow proves this issue is fixed?"]
    if any(word in text.lower() for word in HIGH_RISK_KEYWORDS):
        questions.append("What permission, data integrity, or rollback risk must be reviewed?")
    return questions


def _default_requirement(title: str) -> str:
    return f"Add regression coverage for: {title}"
