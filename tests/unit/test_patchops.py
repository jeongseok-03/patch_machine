from pathlib import Path
from typing import Any

from negotium.app.services.patchops_service import (
    apply_policy_to_plan,
    context_policy,
    fallback_plan,
    fallback_questions,
    is_high_risk_path,
    parse_json_array,
    parse_json_object,
    redact_secrets,
)
from negotium.archive.patch_runs import PatchRun, PatchRunStore


def test_patch_run_store_roundtrip_and_events(tmp_path: Path) -> None:
    store = PatchRunStore(tmp_path)
    run = store.create(
        PatchRun.create(
            repo_id="local",
            request="Fix auth refresh race",
            autonomy_level="L1",
            privacy_mode="hybrid_redacted",
            created_by="owner",
        )
    )

    event = store.append_event(run.id, event_type="repo.scanned", summary="scanned")
    loaded = store.read(run.id)

    assert loaded.request == "Fix auth refresh race"
    assert store.list()[0]["id"] == run.id
    events: list[dict[str, Any]] = store.list_events(run.id)
    assert events[0]["id"] == event["id"]


def test_patchops_json_parsers_strip_fences() -> None:
    assert parse_json_object('```json\n{"risk_level":"medium"}\n```') == {"risk_level": "medium"}
    assert parse_json_array('```json\n[{"question":"Q"}]\n```') == [{"question": "Q"}]


def test_patchops_policy_detects_high_risk_paths() -> None:
    plan = apply_policy_to_plan({"target_files": ["src/auth/session.ts"], "risk_reasons": []})

    assert is_high_risk_path("src/auth/session.ts") is True
    assert plan["risk_level"] == "high"
    assert plan["approval_required"] is True


def test_patchops_context_policy_and_secret_redaction() -> None:
    assert context_policy("local_only")["allow_frontier"] is False
    redacted = redact_secrets("API_KEY=sk-secret PASSWORD=hunter2")
    assert "sk-secret" not in redacted
    assert "hunter2" not in redacted


def test_patchops_fallback_plan_uses_candidates() -> None:
    context = {
        "candidate_files": ["src/api/httpClient.ts"],
        "test_files": ["tests/api/test_http_client.py"],
    }
    questions = fallback_questions("세션 끊김 수정", context)
    plan = fallback_plan("세션 끊김 수정", context, questions)

    assert plan["target_files"] == ["src/api/httpClient.ts"]
    assert plan["questions"] == questions
    assert plan["approval_required"] is True
