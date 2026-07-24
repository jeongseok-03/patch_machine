"""PatchOps execution API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, status

from negotium.app.container import Container
from negotium.app.schemas.issue_memory import McpToolCallPayload
from negotium.app.services.mcp_hub_service import record_mcp_audit
from negotium.app.services.patch_execution_service import (
    analyze_patch_test_failure,
    apply_patch_run_diff,
    create_pr_draft,
    execution_memory_markdown,
    run_patch_tests,
)
from negotium.archive.issue_memory import TestRequirement


def create_patchops_execution_router(container: Container) -> APIRouter:
    router = APIRouter()

    @router.post("/patch-runs/{patch_id}/apply-diff")
    async def apply_patch_run_diff_endpoint(
        patch_id: str,
        payload: McpToolCallPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        try:
            run = container.patch_runs.read(patch_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        result = apply_patch_run_diff(
            container,
            run,
            branch_name=str(payload.arguments.get("branch_name") or ""),
            apply=bool(payload.arguments.get("apply", False)),
        )
        next_status = (
            "PATCH_APPLIED"
            if result.get("ok") and not result.get("dry_run")
            else "FAILED_PATCH_APPLY"
            if not result.get("ok")
            else "PATCHING"
        )
        updated = container.patch_runs.save(
            run.with_updates(status=next_status, artifacts={**run.artifacts, "execution": result})
        )
        container.patch_runs.append_event(
            patch_id,
            event_type="diff.applied" if result.get("ok") else "diff.blocked",
            summary="diff 적용 정책 검사를 완료했습니다.",
            payload=result,
        )
        updated = _write_execution_artifact(
            container,
            updated,
            title="Diff 정책검사",
            payload=result,
        )
        _audit_execution_tool(
            container,
            actor=actor,
            tool_name="repo.apply_patch",
            arguments={"patch_run_id": patch_id, **payload.arguments},
            result=result,
        )
        return {"ok": bool(result.get("ok")), "patch_run": updated.to_dict(), "execution": result}

    @router.post("/patch-runs/{patch_id}/run-tests")
    async def run_patch_run_tests(
        patch_id: str,
        payload: McpToolCallPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        try:
            run = container.patch_runs.read(patch_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        result = run_patch_tests(
            container,
            run,
            command=str(payload.arguments.get("command") or "python -m pytest -q"),
            dry_run=bool(payload.arguments.get("dry_run", True)),
        )
        requirement_status = "passing" if result.get("ok") else "failing"
        artifacts = {
            **run.artifacts,
            "test_run_result": result,
            "test_requirements": _mark_artifact_test_requirements(
                container, run.artifacts.get("test_requirements"), requirement_status
            ),
        }
        updated = container.patch_runs.save(
            run.with_updates(
                status="TESTS_PASSED" if result.get("ok") else "TESTS_FAILED",
                artifacts=artifacts,
            )
        )
        container.patch_runs.append_event(
            patch_id,
            event_type="test.passed" if result.get("ok") else "test.failed",
            summary=f"테스트 명령 실행 결과: {result.get('command')}",
            payload=result,
        )
        updated = _write_execution_artifact(
            container,
            updated,
            title="테스트 실행",
            payload=result,
        )
        _audit_execution_tool(
            container,
            actor=actor,
            tool_name="test.run",
            arguments={"patch_run_id": patch_id, **payload.arguments},
            result=result,
        )
        return {"ok": bool(result.get("ok")), "patch_run": updated.to_dict(), "test_result": result}

    @router.post("/patch-runs/{patch_id}/analyze-test-failure")
    async def analyze_patch_run_test_failure(
        patch_id: str,
        payload: McpToolCallPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        try:
            run = container.patch_runs.read(patch_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        test_result = run.artifacts.get("test_run_result")
        test_result_payload = test_result if isinstance(test_result, dict) else {}
        output = str(
            payload.arguments.get("output") or test_result_payload.get("output_excerpt") or ""
        )
        analysis = analyze_patch_test_failure(output)
        updated = container.patch_runs.save(
            run.with_updates(
                status="TESTS_FAILED",
                artifacts={**run.artifacts, "test_failure_analysis": analysis},
            )
        )
        container.patch_runs.append_event(
            patch_id,
            event_type="test.failure_analyzed",
            summary="테스트 실패 로그를 분석했습니다.",
            payload=analysis,
        )
        updated = _write_execution_artifact(
            container,
            updated,
            title="테스트 실패 분석",
            payload=analysis,
        )
        _audit_execution_tool(
            container,
            actor=actor,
            tool_name="test.analyze_failure",
            arguments={"patch_run_id": patch_id},
            result=analysis,
        )
        return {"ok": True, "patch_run": updated.to_dict(), "analysis": analysis}

    @router.post("/patch-runs/{patch_id}/draft-pr")
    async def draft_patch_run_pr(
        patch_id: str,
        payload: McpToolCallPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        try:
            run = container.patch_runs.read(patch_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        draft = create_pr_draft(
            container, run, branch_name=str(payload.arguments.get("branch_name") or "")
        )
        execution_memory = execution_memory_markdown(run, {"pr_draft": draft})
        promoted = container.permanent_memory.promote(
            title=f"Patch Execution Memory: {run.request[:60]}",
            content=execution_memory,
            source_refs=[patch_id],
            actor=actor,
        )
        updated = container.patch_runs.save(
            run.with_updates(
                status="PR_DRAFTED",
                artifacts={
                    **run.artifacts,
                    "pr_draft": draft,
                    "execution_memory": promoted,
                },
            )
        )
        container.patch_runs.append_event(
            patch_id,
            event_type="pr.drafted",
            summary="PR draft payload를 생성했습니다.",
            payload={"pr_draft": draft, "memory": promoted},
        )
        updated = _write_execution_artifact(
            container,
            updated,
            title="PR Draft 생성",
            payload={"pr_draft": draft, "memory": promoted},
        )
        _audit_execution_tool(
            container,
            actor=actor,
            tool_name="github.create_pr_draft",
            arguments={"patch_run_id": patch_id, **payload.arguments},
            result=draft,
        )
        return {"ok": True, "patch_run": updated.to_dict(), "pr_draft": draft, "memory": promoted}

    return router


def _write_execution_artifact(
    container: Container,
    run: Any,
    *,
    title: str,
    payload: dict[str, Any],
) -> Any:
    existing = str(run.artifacts.get("execution_markdown") or "")
    section = "\n".join(
        [
            f"## {title}",
            "",
            "```json",
            _json_dumps(payload),
            "```",
            "",
        ]
    )
    body = "\n".join(
        [
            f"# PatchOps Execution - {run.request[:80]}",
            "",
            f"- Patch Run: `{run.id}`",
            f"- Status: `{run.status}`",
            "",
            existing,
            section,
        ]
    ).strip()
    return container.patch_runs.save(
        run.with_updates(
            artifacts={
                **run.artifacts,
                "execution_markdown": body,
            }
        )
    )


def _json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _require(container: Container, credential: str | None, permission: str) -> str:
    user_id = _resolve_authenticated_user(container, credential)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="login required")
    if not container.access_control.has_permission(user_id, permission):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"permission required: {permission}")
    return user_id


def _resolve_authenticated_user(container: Container, credential: str | None) -> str | None:
    token = _extract_token(credential)
    if token:
        return container.auth_store.resolve_token(token)
    return None


def _extract_token(credential: str | None) -> str:
    if not credential:
        return ""
    value = credential.strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def _audit_execution_tool(
    container: Container,
    *,
    actor: str,
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> None:
    summary = {"ok": bool(result.get("ok", False)), "keys": sorted(result.keys())}
    record_mcp_audit(
        container,
        actor=actor,
        tool_name=tool_name,
        arguments=arguments,
        result_summary=summary,
        risk_level="high" if tool_name == "repo.apply_patch" else "medium",
    )
    container.audit_log.record(
        actor=actor,
        action="patchops.execution_tool",
        target="mcp_tool",
        target_id=tool_name,
        details={"arguments": arguments, "result_summary": summary},
    )


def _mark_artifact_test_requirements(
    container: Container, value: object, status_value: str
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    updated: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        payload = {**item, "status": status_value}
        updated.append(payload)
        if payload.get("id") and payload.get("patch_candidate_id"):
            container.issue_memory.save_test_requirement(TestRequirement.create(**payload))
    return updated
