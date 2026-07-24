from pathlib import Path
from types import SimpleNamespace

from negotium.app.services.patch_execution_service import (
    apply_patch_run_diff,
    create_pr_draft,
    evaluate_diff_policy,
    extract_diff_files,
    validate_branch_name,
)
from negotium.archive.patch_execution import PatchExecutionStore
from negotium.archive.patch_runs import PatchRun


def test_extract_diff_files_from_unified_diff() -> None:
    diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1 @@
-old
+new
"""

    assert extract_diff_files(diff) == ["src/app.py"]


def test_diff_policy_blocks_denylist_and_dependencies() -> None:
    diff = """diff --git a/.env b/.env
--- a/.env
+++ b/.env
diff --git a/frontend/package.json b/frontend/package.json
--- a/frontend/package.json
+++ b/frontend/package.json
"""

    policy = evaluate_diff_policy(
        diff, approval_granted=True, constraints={"no_new_dependencies": True}
    )

    assert policy["ok"] is False
    assert any("denylisted" in reason for reason in policy["blocked_reasons"])
    assert any("dependency" in reason for reason in policy["blocked_reasons"])


def test_branch_name_policy_blocks_main() -> None:
    assert validate_branch_name("main") == ["direct main/master branch execution is blocked"]
    assert validate_branch_name("patchops/fix-auth") == []


def test_apply_patch_run_diff_dry_run_records_attempt(tmp_path: Path) -> None:
    container = SimpleNamespace(
        patch_execution=PatchExecutionStore(tmp_path),
        settings=SimpleNamespace(workspace_dir=tmp_path),
    )
    run = PatchRun.create(
        id="run-1",
        repo_id="local",
        request="Fix auth issue",
        approved_by="owner",
        artifacts={
            "diff_draft": """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1 @@
-old
+new
"""
        },
    )

    result = apply_patch_run_diff(container, run, branch_name="patchops/run-1")

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert container.patch_execution.list(patch_run_id="run-1")[0]["applied_files"] == [
        "src/app.py"
    ]


def test_pr_draft_is_approval_gated(tmp_path: Path) -> None:
    container = SimpleNamespace(
        patch_execution=PatchExecutionStore(tmp_path),
        settings=SimpleNamespace(github=SimpleNamespace(app_token="token")),
    )
    run = PatchRun.create(
        id="run-2",
        repo_id="owner/repo",
        request="Fix callback session",
        target_branch="main",
        artifacts={"suggested_branch": "patchops/run-2", "pr_description": "## Summary"},
    )

    draft = create_pr_draft(container, run)

    assert draft["requires_human_approval"] is True
    assert draft["remote_creation_supported"] is True
    assert draft["remote_created"] is False
