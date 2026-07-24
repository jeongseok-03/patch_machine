"""Safe PatchOps execution helpers for branch, diff, tests, and PR drafts."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any, cast

from negotium.app.services.context_firewall_service import (
    load_context_firewall_policy,
    record_firewall_audit,
    sanitize_context,
    sanitize_text,
)
from negotium.app.services.issue_memory_service import redact_issue_payload
from negotium.app.services.test_writer_service import analyze_test_failure, run_test_command
from negotium.archive.patch_execution import PatchExecutionAttempt
from negotium.archive.patch_runs import PatchRun

DENYLIST_RE = re.compile(
    r"(^|/)(\.env|.*credentials.*|.*secret.*|.*private[_-]?key.*|id_rsa|id_dsa)(\..*)?$",
    re.IGNORECASE,
)
HIGH_RISK_RE = re.compile(r"(?i)(auth|payment|permission|infra|delete|deletion|secret)")
DEPENDENCY_FILES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pyproject.toml",
    "poetry.lock",
    "requirements.txt",
}
BRANCH_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/\-]{0,80}$")


def extract_diff_files(diff: str) -> list[str]:
    files: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++ b/") or (line.startswith("--- a/") and "/dev/null" not in line):
            files.append(line[6:].strip())
        elif line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4 and parts[3].startswith("b/"):
                files.append(parts[3][2:])
    return list(dict.fromkeys(path for path in files if path and path != "/dev/null"))


def validate_branch_name(branch_name: str) -> list[str]:
    if not branch_name:
        return ["branch name is required"]
    if branch_name in {"main", "master"}:
        return ["direct main/master branch execution is blocked"]
    if not BRANCH_RE.match(branch_name):
        return ["branch name contains unsupported characters"]
    if (
        ".." in branch_name
        or branch_name.endswith(("/", "."))
        or branch_name.startswith(("/", "."))
    ):
        return ["branch name is not git-safe"]
    return []


def evaluate_diff_policy(
    diff: str, *, approval_granted: bool, constraints: dict[str, Any] | None = None
) -> dict[str, Any]:
    constraints = constraints or {}
    files = extract_diff_files(diff)
    blocked: list[str] = []
    warnings: list[str] = []
    high_risk = [path for path in files if HIGH_RISK_RE.search(path)]
    dependency_files = [path for path in files if Path(path).name in DEPENDENCY_FILES]
    denylisted = [path for path in files if DENYLIST_RE.search(path)]
    if not diff.strip():
        blocked.append("diff is empty")
    if denylisted:
        blocked.append("denylisted path changed: " + ", ".join(denylisted))
    if dependency_files and constraints.get("no_new_dependencies", True):
        blocked.append("dependency manifest or lockfile change requires explicit approval")
    if high_risk and not approval_granted:
        blocked.append("high-risk path requires approval: " + ", ".join(high_risk))
    if high_risk:
        warnings.append("high-risk paths detected: " + ", ".join(high_risk))
    firewall = sanitize_context(diff, destination="local_storage", task_type="git.diff")
    if firewall.removed_counts:
        blocked.append(
            "diff contains sensitive content: "
            + ", ".join(f"{key}={value}" for key, value in sorted(firewall.removed_counts.items()))
        )
    return {
        "ok": not blocked,
        "files": files,
        "blocked_reasons": blocked,
        "warnings": warnings,
        "high_risk_files": high_risk,
        "dependency_files": dependency_files,
        "context_firewall": {
            "decision": firewall.decision,
            "highest_sensitivity": firewall.highest_sensitivity,
            "removed_counts": firewall.removed_counts,
            "blocked_items": firewall.blocked_items,
        },
    }


def create_branch(container: Any, *, branch_name: str, dry_run: bool = True) -> dict[str, Any]:
    root = _workspace_root(container)
    blocked = validate_branch_name(branch_name)
    if blocked:
        return {"ok": False, "branch_name": branch_name, "blocked_reasons": blocked}
    if dry_run:
        return {"ok": True, "dry_run": True, "branch_name": branch_name}
    completed = _run_git(root, ["checkout", "-B", branch_name])
    return {"ok": completed["exit_code"] == 0, "branch_name": branch_name, **completed}


def apply_patch_run_diff(
    container: Any,
    run: PatchRun,
    *,
    branch_name: str = "",
    apply: bool = False,
) -> dict[str, Any]:
    diff = str(run.artifacts.get("diff_draft") or "")
    branch = branch_name or str(run.artifacts.get("suggested_branch") or f"patchops/{run.id[:8]}")
    branch_blocked = validate_branch_name(branch)
    policy = evaluate_diff_policy(
        diff, approval_granted=bool(run.approved_by), constraints=run.constraints
    )
    blocked = [*branch_blocked, *policy["blocked_reasons"]]
    attempt = PatchExecutionAttempt.create(
        patch_run_id=run.id,
        branch_name=branch,
        diff_hash=_hash(diff),
        applied_files=policy["files"],
        blocked_reasons=blocked,
        status="blocked" if blocked else ("applied" if apply else "ready"),
    )
    if blocked:
        saved = container.patch_execution.save(attempt)
        return {"ok": False, "attempt": saved.to_dict(), "policy": policy}
    if not apply:
        saved = container.patch_execution.save(attempt)
        return {"ok": True, "dry_run": True, "attempt": saved.to_dict(), "policy": policy}
    root = _workspace_root(container)
    dirty = _git_has_changes(root)
    if dirty["dirty"]:
        saved = container.patch_execution.save(
            attempt.with_updates(status="blocked", command_results=[dirty])
        )
        return {
            "ok": False,
            "attempt": saved.to_dict(),
            "policy": policy,
            "blocked_reasons": [
                "workspace has uncommitted changes; apply requires a clean dedicated branch"
            ],
            "workspace": dirty,
        }
    branch_result = create_branch(container, branch_name=branch, dry_run=False)
    if not branch_result.get("ok"):
        saved = container.patch_execution.save(
            attempt.with_updates(status="blocked", command_results=[branch_result])
        )
        return {
            "ok": False,
            "attempt": saved.to_dict(),
            "policy": policy,
            "branch_result": branch_result,
        }
    check = _run_git(root, ["apply", "--check", "-"], input_text=diff)
    if check["exit_code"] != 0:
        saved = container.patch_execution.save(
            attempt.with_updates(status="failed_patch_apply", command_results=[check])
        )
        return {"ok": False, "attempt": saved.to_dict(), "policy": policy, "apply_check": check}
    applied = _run_git(root, ["apply", "-"], input_text=diff)
    status = "applied" if applied["exit_code"] == 0 else "failed_patch_apply"
    saved = container.patch_execution.save(
        attempt.with_updates(status=status, command_results=[dirty, branch_result, check, applied])
    )
    return {
        "ok": applied["exit_code"] == 0,
        "attempt": saved.to_dict(),
        "policy": policy,
        "apply_result": applied,
    }


def git_diff(container: Any, *, cached: bool = False) -> dict[str, Any]:
    args = ["diff", "--cached"] if cached else ["diff"]
    result = _run_git(_workspace_root(container), args)
    firewall = sanitize_context(
        str(result.get("output_excerpt") or ""),
        destination="mcp_result",
        task_type="git.diff",
        policy=load_context_firewall_policy(_workspace_root(container)),
    )
    firewall = record_firewall_audit(
        container, firewall, destination="mcp_result", task_type="git.diff"
    )
    return {
        "ok": result["exit_code"] == 0,
        "diff": str(firewall.sanitized),
        **result,
        "output_excerpt": str(firewall.sanitized),
        "context_firewall": {
            "audit_id": firewall.audit_id,
            "decision": firewall.decision,
            "highest_sensitivity": firewall.highest_sensitivity,
            "removed_counts": firewall.removed_counts,
        },
    }


def run_patch_tests(
    container: Any,
    run: PatchRun,
    *,
    command: str = "python -m pytest -q",
    dry_run: bool = True,
) -> dict[str, Any]:
    result = run_test_command(_workspace_root(container), command=command, dry_run=dry_run)
    if "output_excerpt" in result:
        sanitized_output = sanitize_text(
            str(result.get("output_excerpt") or ""),
            destination="local_storage",
            task_type="test.run",
            policy=load_context_firewall_policy(_workspace_root(container)),
        )
        result = {**result, "output_excerpt": sanitized_output}
    attempts = container.patch_execution.list(patch_run_id=run.id, limit=1)
    if attempts:
        attempt = PatchExecutionAttempt.create(**attempts[0])
        container.patch_execution.save(
            attempt.with_updates(
                status="tests_passed" if result.get("ok") else "tests_failed",
                command_results=[*attempt.command_results, result],
            )
        )
    return result


def analyze_patch_test_failure(output: str) -> dict[str, Any]:
    return analyze_test_failure(
        {
            "output": sanitize_text(
                output, destination="local_storage", task_type="test.analyze_failure"
            )
        }
    )


def create_pr_draft(container: Any, run: PatchRun, *, branch_name: str = "") -> dict[str, Any]:
    branch = branch_name or str(run.artifacts.get("suggested_branch") or f"patchops/{run.id[:8]}")
    title = str(run.plan.get("goal") or run.request)[:120]
    body = str(run.artifacts.get("pr_description") or "")
    configured = bool(container.settings.github.app_token)
    draft = {
        "configured": configured,
        "repo_id": run.repo_id,
        "base": run.target_branch,
        "head": branch,
        "title": title,
        "body": body,
        "draft": True,
        "requires_human_approval": True,
        "remote_creation_supported": configured,
        "remote_created": False,
        "approval_note": "This endpoint only prepares the PR payload. Remote creation requires a separate approved action.",
        "note": "GitHub credential not configured; returning PR draft payload only."
        if not configured
        else "Ready for GitHub PR creation.",
    }
    attempts = container.patch_execution.list(patch_run_id=run.id, limit=1)
    if attempts:
        attempt = PatchExecutionAttempt.create(**attempts[0])
        container.patch_execution.save(attempt.with_updates(status="pr_drafted", pr_draft=draft))
    return cast(dict[str, Any], redact_issue_payload(draft))


def execution_memory_markdown(run: PatchRun, execution: dict[str, Any]) -> str:
    rendered = "\n".join(
        [
            f"# Patch Execution: {run.request[:80]}",
            "",
            "## Patch Run",
            f"- id: {run.id}",
            f"- repo: {run.repo_id}",
            f"- status: {run.status}",
            "",
            "## Execution",
            "```json",
            _json_excerpt(execution),
            "```",
        ]
    )
    return sanitize_text(rendered, destination="local_storage", task_type="patch_execution_memory")


def _workspace_root(container: Any) -> Path:
    return Path(container.settings.workspace_dir).resolve()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run_git(root: Path, args: list[str], *, input_text: str = "") -> dict[str, Any]:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    output = (completed.stdout + "\n" + completed.stderr).strip()
    return {
        "command": "git " + " ".join(args),
        "exit_code": completed.returncode,
        "output_excerpt": output[:4000],
    }


def _git_has_changes(root: Path) -> dict[str, Any]:
    result = _run_git(root, ["status", "--porcelain"])
    output = str(result.get("output_excerpt") or "")
    return {**result, "dirty": bool(output.strip())}


def _json_excerpt(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(redact_issue_payload(payload), ensure_ascii=False, indent=2)[:5000]
