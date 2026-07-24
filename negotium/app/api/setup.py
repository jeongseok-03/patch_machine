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
from negotium.app.container import Container
from negotium.app.initial_setup import parse_setup_uploads
from negotium.app.schemas.core import (
    InitialOfficeAnalyzeRequest,
    InitialOfficeSetupResult,
    OperationsMemoryPayload,
    WorkMemoryPayload,
)
from negotium.archive.access_control import ALL_PERMISSIONS


def create_setup_router(container: Container) -> APIRouter:
    """Routes for the setup domain."""
    router = APIRouter()

    @router.post("/setup/office/analyze")
    async def analyze_initial_office_setup(
        payload: InitialOfficeAnalyzeRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> InitialOfficeSetupResult:
        actor = _require(container, x_ng_user, "admin:users")
        uploads = _selected_upload_records(container.uploads.list(), payload.upload_ids)
        parsed_files = parse_setup_uploads(uploads, archive_root=container.settings.archive_dir)
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
            markdown = await _complete_office_task(container, prompt, task="memory_summary")
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
