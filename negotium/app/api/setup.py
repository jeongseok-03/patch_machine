"""Setup API routes (split from the former monolithic router)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException

from negotium.app.api._shared import (
    _ai_job_payload,
    _apply_initial_setup_llm_routes,
    _audit,
    _complete_office_task,
    _finish_ai_job,
    _initial_setup_memories_with_recommendations,
    _parse_initial_setup_result,
    _require,
    _selected_upload_records,
    _start_ai_job,
)
from negotium.app.company_analysis import analyze_company_documents, generate_company_report
from negotium.app.company_scan import (
    ScanConfig,
    ScanReport,
    browse_directories,
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

    @router.post("/setup/office/browse")
    async def browse_office_folders(
        payload: dict[str, str],
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "admin:users")
        try:
            return browse_directories(str(payload.get("path") or ""))
        except FileNotFoundError:
            raise HTTPException(
                status_code=404, detail="폴더를 찾을 수 없거나 접근할 수 없습니다."
            ) from None

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
            parsed_files = [
                *parsed_files,
                *parse_scanned_files(scan_report, max_files=320, max_total_chars=800_000),
            ]
            force_local = not payload.scan.allow_cloud
            container.company_knowledge.store_scan_config(
                {
                    "root_paths": payload.scan.root_paths,
                    "excluded_paths": payload.scan.excluded_paths,
                    "allow_cloud": payload.scan.allow_cloud,
                }
            )
        job = _start_ai_job(
            container,
            task="initial_office_setup.analyze",
            actor=actor,
            input_summary=payload.message or "회사 문서 자동 분석",
            used_sources=[str(item.path) for item in parsed_files],
        )

        async def _complete(prompt: str, max_tokens: int) -> str:
            return await _complete_office_task(
                container,
                prompt,
                task="memory_summary",
                force_local=force_local,
                max_tokens=max_tokens,
            )

        try:
            analysis = await analyze_company_documents(
                parsed_files,
                store=container.company_knowledge,
                complete=_complete,
                extra_request=payload.message,
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
        profile = analysis.profile
        draft = {
            "operations_memory": {
                "company_name": profile.get("company_name", ""),
                "organization": profile.get("organization", ""),
                "departments": profile.get("departments", ""),
                "roles": profile.get("roles", ""),
                "key_workflows": profile.get("key_workflows", ""),
                "sensitive_policy": profile.get("sensitive_policy", ""),
            },
            "work_memory": {},
            "notes": list(analysis.notes),
            "warnings": [],
            "questions": list(profile.get("questions") or []),
        }
        result = _parse_initial_setup_result(
            json.dumps(draft, ensure_ascii=False),
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
                "summarized_files": analysis.summarized_files,
                "cached_files": analysis.cached_files,
                "deferred_files": analysis.deferred_files,
            }
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

    @router.post("/setup/office/report/generate")
    async def generate_office_report(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        config = container.company_knowledge.scan_config()
        if not config.get("root_paths"):
            raise HTTPException(
                status_code=400,
                detail="스캔 설정이 없습니다. 초기 세팅에서 회사 폴더를 먼저 지정해 주세요.",
            )
        scan = OfficeScanRequest.model_validate(config)
        report_scan = _run_company_scan(scan)
        parsed_files = parse_scanned_files(report_scan, max_files=320, max_total_chars=800_000)
        force_local = not scan.allow_cloud

        async def _complete(prompt: str, max_tokens: int) -> str:
            return await _complete_office_task(
                container,
                prompt,
                task="memory_summary",
                force_local=force_local,
                max_tokens=max_tokens,
            )

        report = await generate_company_report(
            parsed_files, store=container.company_knowledge, complete=_complete
        )
        if report is None:
            raise HTTPException(
                status_code=502, detail="리포트 생성에 실패했습니다. 잠시 후 다시 시도해 주세요."
            )
        report["created_at"] = datetime.now(UTC).isoformat()
        container.company_knowledge.store_report(report)
        _audit(
            container,
            actor=actor,
            action="setup.office.report",
            target="company_report",
            details={
                "read_files": report.get("read_files"),
                "changed_files": report.get("changed_files"),
            },
        )
        return report

    @router.get("/setup/office/report/latest")
    async def latest_office_report(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "admin:users")
        report = container.company_knowledge.latest_report()
        schedule = container.company_knowledge.report_schedule()
        return {
            "report": report,
            "schedule": schedule,
            "is_due": _report_is_due(schedule, report),
        }

    @router.get("/setup/office/report/schedule")
    async def get_report_schedule(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "admin:users")
        return container.company_knowledge.report_schedule()

    @router.put("/setup/office/report/schedule")
    async def put_report_schedule(
        payload: dict[str, str],
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        interval = str(payload.get("interval") or "off")
        if interval not in REPORT_INTERVALS:
            raise HTTPException(
                status_code=400, detail="interval은 off/monthly/quarterly/semiannual 중 하나입니다."
            )
        schedule = {**container.company_knowledge.report_schedule(), "interval": interval}
        container.company_knowledge.store_report_schedule(schedule)
        _audit(
            container,
            actor=actor,
            action="setup.office.report_schedule",
            target="company_report",
            details={"interval": interval},
        )
        return schedule

    return router


REPORT_INTERVALS: dict[str, int] = {"off": 0, "monthly": 30, "quarterly": 91, "semiannual": 182}


def _report_is_due(schedule: dict[str, object], report: dict[str, object]) -> bool:
    interval = str(schedule.get("interval") or "off")
    days = REPORT_INTERVALS.get(interval, 0)
    if days <= 0:
        return False
    created = str(report.get("created_at") or "")
    if not created:
        return True
    try:
        last = datetime.fromisoformat(created)
    except ValueError:
        return True
    return (datetime.now(UTC) - last).days >= days


def _run_company_scan(payload: OfficeScanRequest) -> ScanReport:
    max_files = max(1, min(payload.max_files, 1000))
    return scan_company_paths(
        ScanConfig(
            root_paths=payload.root_paths,
            excluded_paths=payload.excluded_paths,
            max_files=max_files,
        )
    )
