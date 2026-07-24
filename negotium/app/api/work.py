"""Work API routes (split from the former monolithic router)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status

from negotium.app.api._shared import (
    _ai_job_payload,
    _assignment_scope,
    _audit,
    _collect_owner_activity,
    _complete_office_task,
    _create_handover_tasks,
    _enqueue_process_steps,
    _ensure_owner_in_scope,
    _extract_process_steps,
    _extract_step_skill_id,
    _finish_ai_job,
    _generate_process_steps,
    _office_context,
    _plan_status_by_step,
    _process_plan_payload,
    _recent_logs,
    _require,
    _require_editable_plan,
    _require_plan,
    _resequence_plan,
    _run_step_skill,
    _schedule_to_work_items,
    _start_ai_job,
    _summarize_bottlenecks,
    _summarize_queue,
    _user_display_name,
    _write_generated_doc,
)
from negotium.app.container import Container
from negotium.app.schemas.core import (
    ApiStatusPayload,
    GeneratedDocumentPayload,
    HandoverRequest,
    ProcessPlanListPayload,
    ProcessPlanModeRequest,
    ProcessPlanPayload,
    ProcessStepCreatePayload,
    ProcessStepEditPayload,
    ProcessStepReorderRequest,
    ProgressPayload,
    WorkArchitecturePayload,
    WorkArchitectureRequest,
    WorkItemSignOffPayload,
    WorkItemsPayload,
    WorkScheduleGenerationRequest,
    WorkScheduleItemPayload,
)
from negotium.app.services.skill_runtime import SkillError
from negotium.archive.process_plans import ProcessPlan
from negotium.archive.work_memory import WorkMemory, WorkScheduleItem
from negotium.prompts import render as render_prompt


def create_work_router(container: Container) -> APIRouter:
    """Routes for the work domain."""
    router = APIRouter()

    @router.get("/status")
    async def read_status() -> ApiStatusPayload:
        memory = container.operations_memory.read()
        return ApiStatusPayload(
            ok=True,
            queue_size=container.bus.size,
            queue_capacity=container.bus.capacity,
            metrics=container.metrics.snapshot(),
            operations_memory_configured=any(memory.to_dict().values()),
        )

    @router.get("/progress")
    async def read_progress() -> ProgressPayload:
        return ProgressPayload(
            current_status_md=container.archive.status.read(),
            queue_size=container.bus.size,
            queue_capacity=container.bus.capacity,
            recent_logs=_recent_logs(container.settings.archive_dir, limit=8),
        )

    @router.get("/work-items")
    async def read_work_items(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> WorkItemsPayload:
        _require(container, x_ng_user, "work:read")
        schedule = container.work_schedule.list()
        queue_items = _schedule_to_work_items(
            schedule, plan_status_by_step=_plan_status_by_step(container)
        )
        logs = _recent_logs(container.settings.archive_dir, limit=20)
        for item in logs:
            item["kind"] = item.get("source") or "archive"
            item["summary"] = f"{item.get('repo', 'unknown')} #{item.get('external_id', '-')}"
        items = queue_items + logs
        summary = _summarize_queue(queue_items) or _summarize_bottlenecks(logs)
        return WorkItemsPayload(items=items, bottleneck_summary=summary)

    @router.post("/work-schedule/items/{item_id}/run")
    async def run_work_schedule_item(
        item_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        item = container.work_schedule.get(item_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="해당 작업을 찾을 수 없습니다."
            )
        if item.status == "done":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="이미 완료된 단계입니다."
            )
        owning_plan = container.process_plans.find_by_architecture(item.source_architecture_id)
        if owning_plan is not None and owning_plan.status not in {"approved", "running"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="프로세스 계획이 아직 승인되지 않았습니다. 프로세스 설계에서 먼저 승인하세요.",
            )
        statuses = {entry["id"]: entry.get("status") for entry in container.work_schedule.list()}
        blocking = [dep for dep in item.dependencies if statuses.get(dep) != "done"]
        if blocking:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이전 단계가 완료되지 않아 이 단계를 실행할 수 없습니다. 순서대로 진행하세요.",
            )
        skill_id = _extract_step_skill_id(item.notes)
        prompt = render_prompt(
            "office/work_process_step.md.j2",
            context=_office_context(container),
            title=item.title,
            notes=item.notes,
            source=item.source_architecture_id,
        ).strip()
        job = _start_ai_job(
            container,
            task="work_process_step",
            actor=actor,
            input_summary=item.title,
            used_sources=[item.source_architecture_id] if item.source_architecture_id else None,
        )
        try:
            if skill_id:
                result_path, markdown = await _run_step_skill(
                    container, skill_id, item=item, actor=actor
                )
            else:
                markdown = await _complete_office_task(
                    container, prompt, task="document_generation"
                )
                result_path = _write_generated_doc(
                    container.settings.archive_dir,
                    folder="work_architecture",
                    slug=f"step_{item.title}",
                    markdown=markdown,
                )
            job = _finish_ai_job(container, job, status="succeeded", result_path=result_path)
        except SkillError as exc:
            _finish_ai_job(container, job, status="failed", error=str(exc))
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            _finish_ai_job(container, job, status="failed", error=str(exc))
            raise
        notes = item.notes
        if result_path not in notes:
            notes = f"{notes} / 실행 결과: {result_path}" if notes else f"실행 결과: {result_path}"
        updated = container.work_schedule.upsert(
            WorkScheduleItem.create(**{**item.to_dict(), "status": "done", "notes": notes})
        )
        plan_payload: dict[str, Any] = {}
        if owning_plan is not None:
            statuses_after = {
                entry["id"]: entry.get("status") for entry in container.work_schedule.list()
            }
            all_done = all(
                statuses_after.get(step_id) == "done" for step_id in owning_plan.step_ids
            )
            next_status = "completed" if all_done else "running"
            owning_plan = container.process_plans.upsert(owning_plan.with_status(next_status))
            plan_payload = _process_plan_payload(container, owning_plan).model_dump()
        _audit(
            container,
            actor=actor,
            action="work_schedule.run",
            target="work_schedule",
            target_id=updated.id,
            details={"result_path": result_path},
        )
        return {
            "ok": True,
            "item": updated.to_dict(),
            "items": _schedule_to_work_items(
                container.work_schedule.list(),
                plan_status_by_step=_plan_status_by_step(container),
            ),
            "result_path": result_path,
            "ai_job": _ai_job_payload(job).model_dump(),
            "plan": plan_payload,
        }

    @router.post("/work-schedule/items/{item_id}/sign-off")
    async def sign_off_work_item(
        item_id: str,
        payload: WorkItemSignOffPayload | None = None,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        item = container.work_schedule.get(item_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="해당 단계를 찾을 수 없습니다."
            )
        signer = _user_display_name(container, actor)
        note = (payload.note if payload else "").strip()
        # Attach a completion record file: prefer the assignee's note, else any
        # existing AI result path already referenced in the notes.
        record_path = item.completion_record
        if note:
            record_md = "\n".join(
                [
                    f"# 업무 완료 기록: {item.title}",
                    "",
                    f"- 담당자: {item.owner_name or '(미지정)'}",
                    f"- 완료 확인: {signer}",
                    f"- 확인 시각: {datetime.now(UTC).isoformat()}",
                    "",
                    "## 처리 내용",
                    note,
                ]
            )
            record_path = _write_generated_doc(
                container.settings.archive_dir,
                folder="work_records",
                slug=f"done_{item.title}",
                markdown=record_md,
            )
        updated = container.work_schedule.upsert(
            WorkScheduleItem.create(
                **{
                    **item.to_dict(),
                    "status": "done",
                    "signed_off_by": signer,
                    "signed_off_at": datetime.now(UTC).isoformat(),
                    "completion_record": record_path,
                }
            )
        )
        plan_payload: dict[str, Any] = {}
        owning_plan = container.process_plans.find_by_architecture(item.source_architecture_id)
        if owning_plan is not None:
            statuses_after = {
                entry["id"]: entry.get("status") for entry in container.work_schedule.list()
            }
            all_done = all(
                statuses_after.get(step_id) == "done" for step_id in owning_plan.step_ids
            )
            owning_plan = container.process_plans.upsert(
                owning_plan.with_status("completed" if all_done else owning_plan.status)
            )
            plan_payload = _process_plan_payload(container, owning_plan).model_dump()
        _audit(
            container,
            actor=actor,
            action="work_schedule.sign_off",
            target="work_schedule",
            target_id=updated.id,
        )
        return {
            "ok": True,
            "item": updated.to_dict(),
            "items": _schedule_to_work_items(
                container.work_schedule.list(),
                plan_status_by_step=_plan_status_by_step(container),
            ),
            "plan": plan_payload,
        }

    @router.get("/process-plans")
    async def list_process_plans(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> ProcessPlanListPayload:
        _require(container, x_ng_user, "work:read")
        items = [
            _process_plan_payload(container, ProcessPlan.from_mapping(raw))
            for raw in container.process_plans.list()
        ]
        return ProcessPlanListPayload(items=items)

    @router.get("/process-plans/{plan_id}")
    async def read_process_plan(
        plan_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> ProcessPlanPayload:
        _require(container, x_ng_user, "work:read")
        plan = container.process_plans.get(plan_id)
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="계획을 찾을 수 없습니다."
            )
        return _process_plan_payload(container, plan, include_markdown=True)

    @router.post("/process-plans/{plan_id}/approve")
    async def approve_process_plan(
        plan_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> ProcessPlanPayload:
        actor = _require(container, x_ng_user, "memory:write")
        plan = _require_plan(container, plan_id)
        if plan.status not in {"draft", "paused"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="초안 또는 일시정지 상태의 계획만 승인할 수 있습니다.",
            )
        updated = container.process_plans.upsert(plan.with_status("approved", approved_by=actor))
        _audit(
            container,
            actor=actor,
            action="process_plan.approve",
            target="process_plan",
            target_id=plan_id,
        )
        return _process_plan_payload(container, updated, include_markdown=True)

    @router.post("/process-plans/{plan_id}/mode")
    async def set_process_plan_mode(
        plan_id: str,
        payload: ProcessPlanModeRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> ProcessPlanPayload:
        actor = _require(container, x_ng_user, "memory:write")
        plan = _require_plan(container, plan_id)
        if payload.mode not in {"manual", "auto"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="mode는 manual 또는 auto여야 합니다.",
            )
        updated = container.process_plans.upsert(plan.with_mode(payload.mode))
        _audit(
            container,
            actor=actor,
            action="process_plan.mode",
            target="process_plan",
            target_id=plan_id,
            details={"mode": payload.mode},
        )
        return _process_plan_payload(container, updated, include_markdown=True)

    @router.post("/process-plans/{plan_id}/pause")
    async def pause_process_plan(
        plan_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> ProcessPlanPayload:
        actor = _require(container, x_ng_user, "memory:write")
        plan = _require_plan(container, plan_id)
        updated = container.process_plans.upsert(plan.with_status("paused"))
        _audit(
            container,
            actor=actor,
            action="process_plan.pause",
            target="process_plan",
            target_id=plan_id,
        )
        return _process_plan_payload(container, updated, include_markdown=True)

    @router.post("/process-plans/{plan_id}/resume")
    async def resume_process_plan(
        plan_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> ProcessPlanPayload:
        actor = _require(container, x_ng_user, "memory:write")
        plan = _require_plan(container, plan_id)
        if plan.status != "paused":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="일시정지 상태의 계획만 재개할 수 있습니다.",
            )
        updated = container.process_plans.upsert(plan.with_status("running"))
        _audit(
            container,
            actor=actor,
            action="process_plan.resume",
            target="process_plan",
            target_id=plan_id,
        )
        return _process_plan_payload(container, updated, include_markdown=True)

    @router.post("/process-plans/{plan_id}/steps")
    async def add_process_step(
        plan_id: str,
        payload: ProcessStepCreatePayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> ProcessPlanPayload:
        actor = _require(container, x_ng_user, "memory:write")
        plan = _require_editable_plan(container, plan_id)
        item = container.work_schedule.upsert(
            WorkScheduleItem.create(
                title=payload.title,
                notes=payload.notes,
                owner_name=payload.owner_name,
                priority=payload.priority,
                assignee_kind=payload.assignee_kind,
                source_architecture_id=plan.architecture_path,
            )
        )
        updated = _resequence_plan(container, plan, [*plan.step_ids, item.id])
        _audit(
            container,
            actor=actor,
            action="process_plan.step.add",
            target="process_plan",
            target_id=plan_id,
            details={"step_id": item.id},
        )
        return _process_plan_payload(container, updated, include_markdown=True)

    @router.put("/process-plans/{plan_id}/steps/{step_id}")
    async def update_process_step(
        plan_id: str,
        step_id: str,
        payload: ProcessStepEditPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> ProcessPlanPayload:
        actor = _require(container, x_ng_user, "memory:write")
        plan = _require_editable_plan(container, plan_id)
        if step_id not in plan.step_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="단계를 찾을 수 없습니다."
            )
        item = container.work_schedule.get(step_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="단계를 찾을 수 없습니다."
            )
        if item.status == "done":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="완료된 단계는 수정할 수 없습니다."
            )
        overrides = item.to_dict()
        if payload.title is not None:
            overrides["title"] = payload.title
        if payload.notes is not None:
            overrides["notes"] = payload.notes
        if payload.owner_name is not None:
            overrides["owner_name"] = payload.owner_name
        if payload.priority is not None:
            overrides["priority"] = payload.priority
        if payload.assignee_kind is not None:
            overrides["assignee_kind"] = payload.assignee_kind
        container.work_schedule.upsert(WorkScheduleItem.create(**overrides))
        plan = _require_plan(container, plan_id)
        _audit(
            container,
            actor=actor,
            action="process_plan.step.update",
            target="process_plan",
            target_id=plan_id,
            details={"step_id": step_id},
        )
        return _process_plan_payload(container, plan, include_markdown=True)

    @router.delete("/process-plans/{plan_id}/steps/{step_id}")
    async def delete_process_step(
        plan_id: str,
        step_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> ProcessPlanPayload:
        actor = _require(container, x_ng_user, "memory:write")
        plan = _require_editable_plan(container, plan_id)
        container.work_schedule.delete(step_id)
        remaining = [sid for sid in plan.step_ids if sid != step_id]
        updated = _resequence_plan(container, plan, remaining)
        _audit(
            container,
            actor=actor,
            action="process_plan.step.delete",
            target="process_plan",
            target_id=plan_id,
            details={"step_id": step_id},
        )
        return _process_plan_payload(container, updated, include_markdown=True)

    @router.post("/process-plans/{plan_id}/reorder")
    async def reorder_process_steps(
        plan_id: str,
        payload: ProcessStepReorderRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> ProcessPlanPayload:
        actor = _require(container, x_ng_user, "memory:write")
        plan = _require_editable_plan(container, plan_id)
        existing = set(plan.step_ids)
        ordered = [sid for sid in payload.ordered_ids if sid in existing]
        # Keep any steps the client omitted at the tail to avoid accidental loss.
        ordered.extend(sid for sid in plan.step_ids if sid not in ordered)
        updated = _resequence_plan(container, plan, ordered)
        _audit(
            container,
            actor=actor,
            action="process_plan.reorder",
            target="process_plan",
            target_id=plan_id,
        )
        return _process_plan_payload(container, updated, include_markdown=True)

    @router.post("/work-architecture/generate")
    async def generate_work_architecture(
        payload: WorkArchitectureRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> WorkArchitecturePayload:
        actor = _require(container, x_ng_user, "memory:write")
        context = _office_context(container) if payload.use_memory else ""
        prompt = render_prompt(
            "office/work_architecture.md.j2",
            context=context,
            objective=payload.objective,
            scope=payload.scope,
            horizon=payload.horizon,
            participants=payload.participants,
            constraints=payload.constraints,
        ).strip()
        job = _start_ai_job(
            container,
            task="work_architecture",
            actor=actor,
            input_summary=payload.objective,
        )
        try:
            raw_markdown = await _complete_office_task(
                container, prompt, task="document_generation"
            )
            markdown, _ = _extract_process_steps(raw_markdown)
            steps = await _generate_process_steps(
                container,
                objective=payload.objective,
                scope=payload.scope,
                markdown=markdown,
            )
            path = _write_generated_doc(
                container.settings.archive_dir,
                folder="work_architecture",
                slug=payload.objective or "work_architecture",
                markdown=markdown,
            )
            job = _finish_ai_job(container, job, status="succeeded", result_path=path)
        except Exception as exc:
            _finish_ai_job(container, job, status="failed", error=str(exc))
            raise
        queue = _enqueue_process_steps(
            container,
            architecture_id=path,
            objective=payload.objective,
            participants=payload.participants,
            steps=steps,
        )
        plan = container.process_plans.upsert(
            ProcessPlan.create(
                objective=payload.objective,
                architecture_path=path,
                status="draft",
                mode="manual",
                step_ids=[str(item.get("id")) for item in queue],
            )
        )
        architecture = {
            "objective": payload.objective,
            "scope": payload.scope,
            "horizon": payload.horizon,
            "participants": payload.participants,
            "constraints": payload.constraints,
            "path": path,
            "step_count": len(queue),
        }
        work_memory = container.work_memory.read()
        if queue:
            next_action = (
                f"AI 설계 검토/수정 후 승인 필요: {len(queue)}단계 (프로세스 설계에서 승인)"
            )
        else:
            next_action = f"업무 프로세스 설계 검토: {path}"
        container.work_memory.write(
            WorkMemory(
                goals=work_memory.goals or payload.objective,
                active_projects=payload.scope or work_memory.active_projects,
                current_focus=payload.objective,
                blockers=work_memory.blockers,
                decisions=work_memory.decisions,
                risks=payload.constraints or work_memory.risks,
                next_actions=next_action,
            )
        )
        _audit(
            container,
            actor=actor,
            action="work_architecture.generate",
            target="work_architecture",
            target_id=path,
            details={"step_count": len(queue)},
        )
        return WorkArchitecturePayload(
            title=payload.objective,
            markdown=markdown,
            path=path,
            architecture=architecture,
            queue=queue,
            plan=_process_plan_payload(container, plan, include_markdown=False).model_dump(),
            ai_job=_ai_job_payload(job).model_dump(),
        )

    @router.get("/work-schedule")
    async def list_work_schedule(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {"items": container.work_schedule.list()}

    @router.get("/work-schedule/assignment-scope")
    async def work_schedule_assignment_scope(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        return _assignment_scope(container, actor)

    @router.post("/work-schedule/items")
    async def create_work_schedule_item(
        payload: WorkScheduleItemPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        _ensure_owner_in_scope(container, actor, payload.owner_id)
        item = container.work_schedule.upsert(payload.to_record())
        _audit(
            container,
            actor=actor,
            action="work_schedule.upsert",
            target="work_schedule",
            target_id=item.id,
        )
        return {"ok": True, "item": item.to_dict(), "items": container.work_schedule.list()}

    @router.put("/work-schedule/items/{item_id}")
    async def update_work_schedule_item(
        item_id: str,
        payload: WorkScheduleItemPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        _ensure_owner_in_scope(container, actor, payload.owner_id)
        item = container.work_schedule.upsert(payload.to_record(item_id=item_id))
        _audit(
            container,
            actor=actor,
            action="work_schedule.upsert",
            target="work_schedule",
            target_id=item.id,
        )
        return {"ok": True, "item": item.to_dict(), "items": container.work_schedule.list()}

    @router.delete("/work-schedule/items/{item_id}")
    async def delete_work_schedule_item(
        item_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        ok = container.work_schedule.delete(item_id)
        _audit(
            container,
            actor=actor,
            action="work_schedule.delete",
            target="work_schedule",
            target_id=item_id,
        )
        return {"ok": ok, "items": container.work_schedule.list()}

    @router.post("/work-schedule/generate")
    async def generate_work_schedule(
        payload: WorkScheduleGenerationRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> GeneratedDocumentPayload:
        actor = _require(container, x_ng_user, "memory:write")
        prompt = render_prompt(
            "office/work_schedule.md.j2",
            context=_office_context(container),
            objective=payload.objective,
            participants=payload.participants,
            horizon=payload.horizon,
            constraints=payload.constraints,
        ).strip()
        job = _start_ai_job(
            container,
            task="work_schedule.generate",
            actor=actor,
            input_summary=payload.objective,
        )
        try:
            markdown = await _complete_office_task(container, prompt, task="document_generation")
            path = _write_generated_doc(
                container.settings.archive_dir,
                folder="work_architecture",
                slug=f"schedule_{payload.objective}",
                markdown=markdown,
            )
            job = _finish_ai_job(container, job, status="succeeded", result_path=path)
        except Exception as exc:
            _finish_ai_job(container, job, status="failed", error=str(exc))
            raise
        item = container.work_schedule.upsert(
            WorkScheduleItem.create(
                title=f"AI 생성 스케줄 검토: {payload.objective}",
                owner_name=payload.participants,
                priority="high",
                notes=f"생성 문서: {path}",
                source_architecture_id=path,
            )
        )
        _audit(
            container,
            actor=actor,
            action="work_schedule.generate",
            target="work_schedule",
            target_id=item.id,
        )
        return GeneratedDocumentPayload(
            title=payload.objective,
            markdown=markdown,
            path=path,
            ai_job=_ai_job_payload(job).model_dump(),
        )

    @router.post("/handover/brief")
    async def create_handover_brief(
        payload: HandoverRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> GeneratedDocumentPayload:
        actor = _require(container, x_ng_user, "documents:write")
        context = _office_context(container)
        activity_log = _collect_owner_activity(container, payload.outgoing_owner)
        prompt = render_prompt(
            "office/handover.md.j2",
            context=context,
            work_title=payload.work_title,
            outgoing_owner=payload.outgoing_owner,
            incoming_owner=payload.incoming_owner,
            notes=payload.notes,
            activity_log=activity_log,
        ).strip()
        job = _start_ai_job(
            container,
            task="handover",
            actor=actor,
            input_summary=payload.work_title or payload.notes,
        )
        try:
            markdown = await _complete_office_task(container, prompt, task="handover")
            path = _write_generated_doc(
                container.settings.archive_dir,
                folder="handover",
                slug=payload.work_title or "handover",
                markdown=markdown,
            )
            job = _finish_ai_job(container, job, status="succeeded", result_path=path)
        except Exception as exc:
            _finish_ai_job(container, job, status="failed", error=str(exc))
            raise
        if payload.generate_tasks:
            created = await _create_handover_tasks(
                container,
                work_title=payload.work_title,
                incoming_owner=payload.incoming_owner,
                handover_markdown=markdown,
                activity_log=activity_log,
                source_path=path,
            )
            if created:
                bullets = "\n".join(f"- {title}" for title in created)
                markdown = (
                    f"{markdown}\n\n## 신규 담당자 인수 업무 (작업 스케줄 등록됨)\n{bullets}\n"
                )
        result = GeneratedDocumentPayload(
            title=payload.work_title,
            markdown=markdown,
            path=path,
            ai_job=_ai_job_payload(job).model_dump(),
        )
        _audit(container, actor=actor, action="document.create", target="document", target_id=path)
        return result

    return router
