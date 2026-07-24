"""Documents API routes (split from the former monolithic router)."""

from __future__ import annotations

from fastapi import APIRouter, Header

from negotium.adapters.llm.catalog import (
    model_supports_audio,
    model_supports_vision,
)
from negotium.app.api._shared import (
    _ai_job_payload,
    _audit,
    _complete_office_task,
    _finish_ai_job,
    _generate_hiring_document,
    _hr_evaluation_context,
    _hr_evaluation_markdown,
    _office_context,
    _readable_context_bundle,
    _require,
    _resolve_document_attachments,
    _resolve_output_format,
    _resolve_runtime_task,
    _resolve_task_model,
    _start_ai_job,
    _write_generated_doc,
)
from negotium.app.container import Container
from negotium.app.schemas.core import (
    GeneratedDocumentPayload,
    HiringRequest,
    HrEvaluationDraftRequest,
    HrEvaluationSaveRequest,
    OfficeDocumentRequest,
    ReadableContextBundlePayload,
    ReadableContextPreviewRequest,
)
from negotium.prompts import render as render_prompt


def create_documents_router(container: Container) -> APIRouter:
    """Routes for the documents domain."""
    router = APIRouter()

    @router.post("/hr/role-requirements")
    async def create_role_requirements(
        payload: HiringRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> GeneratedDocumentPayload:
        actor = _require(container, x_ng_user, "documents:write")
        result = await _generate_hiring_document(
            container,
            payload,
            actor=actor,
            kind="role_requirements",
            instruction="필요 역량, 경험, 성향, 필수/우대 조건을 정리하세요.",
        )
        _audit(
            container,
            actor=actor,
            action="document.create",
            target="document",
            target_id=result.path,
        )
        return result

    @router.post("/hr/interview-kit")
    async def create_interview_kit(
        payload: HiringRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> GeneratedDocumentPayload:
        actor = _require(container, x_ng_user, "documents:write")
        result = await _generate_hiring_document(
            container,
            payload,
            actor=actor,
            kind="interview_kit",
            instruction="면접 질문, 좋은 답변 기준, 평가 루브릭을 작성하세요.",
        )
        _audit(
            container,
            actor=actor,
            action="document.create",
            target="document",
            target_id=result.path,
        )
        return result

    @router.post("/hr/onboarding-plan")
    async def create_onboarding_plan(
        payload: HiringRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> GeneratedDocumentPayload:
        actor = _require(container, x_ng_user, "documents:write")
        result = await _generate_hiring_document(
            container,
            payload,
            actor=actor,
            kind="onboarding_plan",
            instruction="입사 후 1주/1개월/3개월 온보딩 계획과 산출물을 작성하세요.",
        )
        _audit(
            container,
            actor=actor,
            action="document.create",
            target="document",
            target_id=result.path,
        )
        return result

    @router.get("/hr/evaluation/context")
    async def hr_evaluation_context(
        user_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "admin:hr_evaluation")
        return _hr_evaluation_context(container, user_id=user_id)

    @router.post("/hr/evaluation/draft")
    async def hr_evaluation_draft(
        payload: HrEvaluationDraftRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:hr_evaluation")
        context = _hr_evaluation_context(
            container, user_id=payload.user_id, work_item_ids=payload.work_item_ids
        )
        prompt = render_prompt(
            "office/hr_evaluation.md.j2",
            context=context,
            period=payload.period,
            criteria=payload.criteria,
            notes=payload.notes,
        ).strip()
        text = await _complete_office_task(container, prompt, task="hiring")
        _audit(
            container,
            actor=actor,
            action="hr.evaluation.draft",
            target="user",
            target_id=payload.user_id,
        )
        return {"ok": True, "draft": text, "context": context}

    @router.post("/hr/evaluation/save")
    async def hr_evaluation_save(
        payload: HrEvaluationSaveRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:hr_evaluation")
        from negotium.archive.hr_evaluations import HrEvaluationRecord

        context = _hr_evaluation_context(
            container, user_id=payload.user_id, work_item_ids=payload.work_item_ids
        )
        draft_record = HrEvaluationRecord.create(
            user_id=payload.user_id,
            period=payload.period,
            work_item_ids=payload.work_item_ids,
            draft=payload.draft,
            final_text=payload.final_text,
            evidence=payload.evidence,
            created_by=actor,
            source_refs=payload.source_refs,
        )
        document_path = _write_generated_doc(
            container.settings.archive_dir,
            folder="hr/evaluations",
            slug=f"hr_evaluation_{payload.user_id}_{payload.period or draft_record.id[:8]}",
            markdown=_hr_evaluation_markdown(draft_record, context=context),
        )
        record = container.hr_evaluations.append(
            HrEvaluationRecord.from_mapping(
                {**draft_record.to_dict(), "document_path": document_path}
            )
        )
        _audit(
            container,
            actor=actor,
            action="hr.evaluation.save",
            target="user",
            target_id=payload.user_id,
            details={"document_path": document_path},
        )
        return {"ok": True, "record": record.to_dict(), "document_path": document_path}

    @router.get("/hr/evaluation/records")
    async def hr_evaluation_records(
        user_id: str = "",
        limit: int = 100,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "admin:hr_evaluation")
        return {"records": container.hr_evaluations.list_recent(user_id=user_id, limit=limit)}

    @router.post("/documents/generate")
    async def create_office_document(
        payload: OfficeDocumentRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> GeneratedDocumentPayload:
        actor = _require(container, x_ng_user, "documents:write")
        labels = {
            "meeting_minutes": "회의록",
            "report_draft": "보고서 초안",
            "work_request": "업무 요청서",
            "ppt_outline": "PPT 초안",
        }
        readable_bundle: ReadableContextBundlePayload | None = None
        if payload.source_ids or payload.query.strip():
            readable_bundle = _readable_context_bundle(
                container,
                ReadableContextPreviewRequest(
                    query=payload.query or payload.title,
                    source_ids=payload.source_ids,
                    source_limit=payload.source_limit,
                    include_volatile=payload.include_volatile,
                    token_budget=payload.token_budget,
                ),
            )
        readable_context = readable_bundle.markdown if readable_bundle else ""
        used_sources = (
            [source.id for source in readable_bundle.used_sources] if readable_bundle else []
        )

        provider, route = _resolve_runtime_task(container, "document_generation")
        model = _resolve_task_model(container, "document_generation", provider, route)
        vision = model_supports_vision(provider, model)
        audio = model_supports_audio(provider, model)
        attachment_context, image_parts, attachment_notes = _resolve_document_attachments(
            container, payload.attachment_ids, vision_enabled=vision, audio_enabled=audio
        )

        prompt = render_prompt(
            "office/document_generation.md.j2",
            context=_office_context(container),
            readable_context=readable_context,
            attachment_context=attachment_context,
            document_label=labels[payload.document_type],
            title=payload.title,
            audience=payload.audience,
            source_text=payload.source_text,
            output_format=payload.output_format,
        ).strip()
        job = _start_ai_job(
            container,
            task="document_generation",
            actor=actor,
            input_summary=f"{payload.document_type}: {payload.title}",
            used_sources=used_sources,
        )
        try:
            raw = await _complete_office_task(
                container, prompt, task="document_generation", image_parts=image_parts or None
            )
            resolved_format, body = _resolve_output_format(raw, requested=payload.output_format)
            path = _write_generated_doc(
                container.settings.archive_dir,
                folder="documents",
                slug=f"{payload.document_type}_{payload.title}",
                markdown=body,
                output_format=resolved_format,
            )
            job = _finish_ai_job(
                container, job, status="succeeded", result_path=path, used_sources=used_sources
            )
        except Exception as exc:
            _finish_ai_job(container, job, status="failed", error=str(exc))
            raise
        result = GeneratedDocumentPayload(
            title=payload.title,
            markdown=body,
            path=path,
            ai_job=_ai_job_payload(job).model_dump(),
            output_format=resolved_format,
            attachment_notes=attachment_notes,
        )
        _audit(container, actor=actor, action="document.create", target="document", target_id=path)
        return result

    return router
