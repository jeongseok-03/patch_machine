from pathlib import Path

from negotium.app.services.issue_memory_service import (
    capture_issue_event,
    capture_manual_issue,
    issue_memory_tool_descriptors,
    redact_issue_payload,
    search_issue_memory,
)
from negotium.archive.issue_memory import IssueMemoryStore
from negotium.domain.entities import IssueEvent, RepoRef


def test_issue_memory_capture_normalizes_and_clusters(tmp_path: Path) -> None:
    store = IssueMemoryStore(tmp_path)
    repo = RepoRef(owner="acme", name="app")
    first = IssueEvent(
        source="github",
        external_id="1",
        repo=repo,
        title="Auth session expires after login",
        body="Users are logged out after refresh.",
        author="alice",
        labels=["bug"],
    )
    second = IssueEvent(
        source="discord",
        external_id="m1",
        repo=repo,
        title="Login session is dropped",
        body="Auth session disappears after page reload.",
        author="bob",
        labels=["support"],
    )

    first_capture = capture_issue_event(store, first)
    second_capture = capture_issue_event(store, second)

    assert first_capture["canonical_issue"]["severity"] == "high"
    assert first_capture["patch_candidate"]["risk_level"] == "high"
    assert first_capture["cluster"]["id"] == second_capture["cluster"]["id"]
    assert len(store.list_test_requirements()) == 1


def test_manual_capture_search_and_secret_redaction(tmp_path: Path) -> None:
    store = IssueMemoryStore(tmp_path)
    captured = capture_manual_issue(
        store,
        {
            "title": "Payment delete permission bug",
            "summary": "token=abc123 user cannot recover deleted payment",
            "affected_repos": ["local"],
            "external_uri": "notion://page/123",
        },
    )

    payload = redact_issue_payload({"body": "API_KEY=sk-test TOKEN=abc"})
    results = search_issue_memory(store, "payment", limit=5)

    assert payload["body"].count("[REDACTED_SECRET]") == 2
    assert results["clusters"][0]["id"] == captured["cluster"]["id"]
    assert results["clusters"][0]["test_requirements"]


def test_issue_memory_mcp_tool_schema_contains_memory_tools() -> None:
    names = {tool["name"] for tool in issue_memory_tool_descriptors()}

    assert "memory.search_issues" in names
    assert "memory.create_test_requirement" in names
