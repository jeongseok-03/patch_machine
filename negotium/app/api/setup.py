"""Setup API routes (split from the former monolithic router)."""

from __future__ import annotations

from fastapi import APIRouter, Header

from negotium.app.api._shared import (
    _ai_job_payload,
    _apply_initial_setup_llm_routes,
    _audit,
    _complete_office_task,
    _finish_ai_job,
    _initial_office_setup_prompt,
    _initial_setup_memories_with_recommendations,
    _parse_initial_setup_result,
    _require,
    _selected_upload_records,
    _start_ai_job,
)
from negotium.app.company_scan import (
    ScanConfig,
    ScanReport,
    parse_scanned_files,
    scan_company_paths,
)
from negotium.app.container import Container
from negotium.app.initial_setup import parse_setup_uploads
from negotium.app.schemas.core import (
    InitialOfficeAnalyzeRequest,
    InitialOfficeSetupResult,
    OfficeScanRequest,
    OperationsMemoryPayload,
    WorkMemoryPayload,
)
from negotium.archive.access_control import ALL_PERMISSIONS


def create_setup_router(container: Container) -> APIRouter:
    """Routes for the setup domain."""
    router = APIRouter()

    @router.post("/setup/office/scan-preview")
    async def preview_office_scan(
        payload: OfficeScanRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        report = _run_company_scan(payload)
        _audit(
            container,
            actor=actor,
            action="setup.office.scan_preview",
            target="company_scan",
            details={
                "roots": report.roots,
                "missing_roots": report.missing_roots,
                "included": report.included_count,
                "skipped": report.skipped_counts,
                "truncated": report.truncated,
            },
        )
        return report.to_dict()

    @router.post("/setup/office/analyze")
    async def analyze_initial_office_setup(
        payload: InitialOfficeAnalyzeRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> InitialOfficeSetupResult:
        actor = _require(container, x_ng_user, "admin:users")
        uploads = _selected_upload_records(container.uploads.list(), payload.upload_ids)
        parsed_files = parse_setup_uploads(uploads, archive_root=container.settings.archive_dir)
        scan_report: ScanReport | None = None
        force_local = False
        if payload.scan and payload.scan.root_paths:
            scan_report = _run_company_scan(payload.scan)
            parsed_files = [*parsed_files, *parse_scanned_files(scan_report)]
            force_local = not payload.scan.allow_cloud
        prompt = _initial_office_setup_prompt(
            message=payload.message,
            intent=payload.intent,
            parsed_files=parsed_files,
            company_profile=payload.company_profile,
        )
        job = _start_ai_job(
            container,
            task="initial_office_setup.analyze",
            actor=actor,
            input_summary=payload.message or payload.company_profile.company_name,
            used_sources=[str(item.path) for item in parsed_files],
        )
        try:
            markdown = await _complete_office_task(
                container, prompt, task="memory_summary", force_local=force_local
            )
            job = _finish_ai_job(
                container,
                job,
                status="succeeded",
                used_sources=[str(item.path) for item in parsed_files],
            )
        except Exception as exc:
            _finish_ai_job(container, job, status="failed", error=str(exc))
            raise
        result = _parse_initial_setup_result(
            markdown,
            parsed_files=parsed_files,
            company_profile=payload.company_profile,
        )
        result.ai_job = _ai_job_payload(job).model_dump()
        if scan_report is not None:
            result.provenance = {
                "source": "company_scan",
                "roots": scan_report.roots,
                "scanned_files": scan_report.included_count,
                "used_files": [str(item.path) for item in parsed_files],
                "skipped": scan_report.skipped_counts,
                "truncated": scan_report.truncated,
                "route": "local" if force_local else "configured",
            }
            result.notes = [
                *result.notes,
                "이 초안은 회사 폴더 자동 스캔 결과를 바탕으로 AI가 추론한 내용입니다. "
                "적용 전에 각 항목을 확인해 주세요.",
            ]
        return result

    @router.post("/setup/office/apply")
    async def apply_initial_office_setup(
        payload: InitialOfficeSetupResult,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        operations_memory, work_memory = _initial_setup_memories_with_recommendations(payload)
        if operations_memory:
            container.operations_memory.write(
                OperationsMemoryPayload(**operations_memory).to_memory()
            )
        if work_memory:
            container.work_memory.write(WorkMemoryPayload(**work_memory).to_memory())
        for role in payload.roles:
            if role.id.strip():
                container.access_control.upsert_role(role.to_record())
        for user in payload.users:
            if user.id.strip():
                container.access_control.upsert_user(user.to_record())
        if payload.llm_task_routes:
            _apply_initial_setup_llm_routes(container, payload.llm_task_routes)
        _audit(
            container,
            actor=actor,
            action="setup.office.apply",
            target="initial_office_setup",
            details={
                "roles": [role.id for role in payload.roles],
                "users": [user.id for user in payload.users],
                "sensitive_hint": payload.sensitive_hint,
                "recommended_package": payload.recommended_package,
                "agent_packs": [item.get("id") for item in payload.agent_packs],
                "templates": [item.get("id") for item in payload.templates],
                "workflows": [item.get("id") for item in payload.workflows],
                "security_defaults": [item.get("id") for item in payload.security_defaults],
                "integration_priorities": [
                    item.get("id") for item in payload.integration_priorities
                ],
            },
        )
        return {
            "ok": True,
            "access_control": {**container.access_control.read(), "permissions": ALL_PERMISSIONS},
        }

    return router


def _run_company_scan(payload: OfficeScanRequest) -> ScanReport:
    max_files = max(1, min(payload.max_files, 1000))
    return scan_company_paths(
        ScanConfig(
            root_paths=payload.root_paths,
            excluded_paths=payload.excluded_paths,
            max_files=max_files,
        )
    )
