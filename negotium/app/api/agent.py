"""Agent API routes (split from the former monolithic router)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, status

from negotium.app.api._shared import (
    _ai_job_payload,
    _audit,
    _collect_plan_source_files,
    _complete_office_task,
    _complete_patchops_task,
    _generate_agent_plan_steps,
    _patch_artifact_relative_path,
    _patch_record_detail_payload,
    _patch_record_payload,
    _render_agent_plan_markdown,
    _require,
    _revise_patch_plan_markdown,
    _write_generated_doc,
)
from negotium.app.container import Container
from negotium.app.schemas.core import (
    AgentPlanRequest,
    AiJobStatusPayload,
    PatchPlanMarkdownPayload,
    PatchPlanPromotePayload,
    PatchPlanRevisePayload,
    PatchRecordCreatePayload,
    PatchRecordDetailPayload,
    PatchRecordPayload,
    PatchRunApprovalPayload,
    PatchRunCreatePayload,
    PatchRunPayload,
    SkillCreateRequest,
    SkillRunRequest,
)
from negotium.app.services.patchops_service import (
    analyze_patch_run,
    draft_patch_artifacts,
    write_patch_memory,
)
from negotium.app.services.skill_registry import (
    Skill,
    SkillInput,
    get_skill,
    get_skills,
    register_skill,
)
from negotium.app.services.skill_runtime import SkillError, run_skill
from negotium.archive.agent_execution import AgentPlan
from negotium.archive.patch_runs import PatchRun


def create_agent_router(container: Container) -> APIRouter:
    """Routes for the agent domain."""
    router = APIRouter()

    @router.get("/ai-jobs/recent")
    async def list_ai_jobs(
        limit: int = 30,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {
            "jobs": [
                _ai_job_payload(record).model_dump()
                for record in container.ai_jobs.recent(limit=max(1, min(limit, 200)))
            ]
        }

    @router.get("/ai-jobs/{job_id}")
    async def read_ai_job(
        job_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> AiJobStatusPayload:
        _require(container, x_ng_user, "work:read")
        record = container.ai_jobs.get(job_id)
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="AI job not found")
        return _ai_job_payload(record)

    @router.post("/agent/plans/generate")
    async def generate_agent_plan(
        payload: AgentPlanRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        memory_refs = payload.memory_refs or [
            str(source["path"]) for source in container.permanent_memory.recent(limit=5)
        ]
        schedule_refs = payload.schedule_refs or [
            str(item["id"]) for item in container.work_schedule.list()[:10]
        ]
        steps = await _generate_agent_plan_steps(
            container,
            objective=payload.objective,
            context=payload.context,
            schedule_refs=schedule_refs,
            memory_refs=memory_refs,
        )
        plan_title = payload.title or payload.objective
        markdown = _render_agent_plan_markdown(
            title=plan_title,
            objective=payload.objective,
            steps=steps,
            context=payload.context,
        )
        markdown_path = _write_generated_doc(
            container.settings.archive_dir,
            folder="plans",
            slug=f"plan_{plan_title}",
            markdown=markdown,
        )
        plan = container.agent_execution.save_plan(
            AgentPlan.create(
                title=plan_title,
                objective=payload.objective,
                mode=payload.mode,
                schedule_refs=schedule_refs,
                memory_refs=memory_refs,
                steps=steps,
                created_by=actor,
                plan_markdown_path=markdown_path,
            )
        )
        _audit(
            container,
            actor=actor,
            action="agent.plan.generate",
            target="agent_plan",
            target_id=plan.id,
        )
        return {"ok": True, "plan": plan.to_dict()}

    @router.get("/agent/plans")
    async def list_agent_plans(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {"plans": container.agent_execution.list_plans()}

    @router.post("/agent/plans/{plan_id}/approve")
    async def approve_agent_plan(
        plan_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        plan = container.agent_execution.approve_plan(plan_id, actor=actor)
        _audit(
            container,
            actor=actor,
            action="agent.plan.approve",
            target="agent_plan",
            target_id=plan_id,
        )
        return {"ok": True, "plan": plan.to_dict()}

    @router.post("/agent/plans/{plan_id}/run")
    async def run_agent_plan(
        plan_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        plan = container.agent_execution.read_plan(plan_id)
        if plan.status != "approved" and plan.mode != "plan_only":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="agent plan requires approval before run"
            )
        run = container.agent_execution.append_run(
            plan_id, actor=actor, event="run_requested", details={"mode": plan.mode}
        )
        _audit(
            container,
            actor=actor,
            action="agent.plan.run_requested",
            target="agent_plan",
            target_id=plan_id,
        )
        return {"ok": True, "run": run}

    @router.post("/agent/runs/{run_id}/approve-step")
    async def approve_agent_run_step(
        run_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        _audit(
            container,
            actor=actor,
            action="agent.run.step_approved",
            target="agent_run",
            target_id=run_id,
        )
        return {"ok": True, "run_id": run_id, "approved_by": actor}

    @router.post("/patch-runs")
    async def create_patch_run(
        payload: PatchRunCreatePayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        run = container.patch_runs.create(
            PatchRun.create(
                repo_id=payload.repo_id,
                request=payload.request,
                autonomy_level=payload.autonomy_level,
                privacy_mode=payload.privacy_mode,
                target_branch=payload.target_branch,
                constraints=payload.constraints,
                created_by=actor,
            )
        )
        container.patch_runs.append_event(
            run.id,
            event_type="patch.created",
            summary="PatchOps run을 생성했습니다.",
            payload={
                "repo_id": run.repo_id,
                "autonomy_level": run.autonomy_level,
                "privacy_mode": run.privacy_mode,
            },
        )
        _audit(
            container, actor=actor, action="patchops.create", target="patch_run", target_id=run.id
        )
        return {"ok": True, "patch_run": PatchRunPayload(**run.to_dict())}

    @router.get("/patch-runs")
    async def list_patch_runs(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {"patch_runs": container.patch_runs.list()}

    @router.get("/patch-runs/{patch_id}")
    async def read_patch_run(
        patch_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        try:
            run = container.patch_runs.read(patch_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return {"patch_run": run.to_dict(), "events": container.patch_runs.list_events(patch_id)}

    @router.get("/patch-runs/{patch_id}/events")
    async def list_patch_run_events(
        patch_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {"events": container.patch_runs.list_events(patch_id)}

    @router.get("/patch-runs/{patch_id}/files")
    async def list_patch_run_files(
        patch_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        try:
            container.patch_runs.read(patch_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return {"files": container.patch_runs.list_artifacts(patch_id)}

    @router.get("/patch-runs/{patch_id}/files/{artifact_path:path}")
    async def read_patch_run_file(
        patch_id: str,
        artifact_path: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        try:
            container.patch_runs.read(patch_id)
            artifact = container.patch_runs.read_artifact(
                patch_id, _patch_artifact_relative_path(patch_id, artifact_path)
            )
        except FileNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"file": artifact}

    @router.put("/patch-runs/{patch_id}/plan-md")
    async def save_patch_plan_markdown(
        patch_id: str,
        payload: PatchPlanMarkdownPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        try:
            run = container.patch_runs.read(patch_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        artifact = container.patch_runs.write_artifact(patch_id, "plan.md", payload.content)
        updated = container.patch_runs.save(
            run.with_updates(
                status="PLAN_CREATED",
                artifacts={
                    **run.artifacts,
                    "plan_path": artifact["path"],
                    "plan_markdown": payload.content,
                },
            )
        )
        container.patch_runs.append_event(
            patch_id,
            event_type="plan.md.saved",
            summary="plan.md를 직접 저장했습니다.",
            payload={"actor": actor, "bytes": artifact["bytes"]},
        )
        _audit(
            container,
            actor=actor,
            action="patchops.plan_md.save",
            target="patch_run",
            target_id=patch_id,
        )
        return {
            "ok": True,
            "patch_run": updated.to_dict(),
            "file": container.patch_runs.read_artifact(patch_id, "plan.md"),
        }

    @router.post("/patch-runs/{patch_id}/plan-md/revise")
    async def revise_patch_plan_markdown(
        patch_id: str,
        payload: PatchPlanRevisePayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        try:
            run = container.patch_runs.read(patch_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        current = payload.current_content.strip()
        if not current:
            try:
                current = str(
                    container.patch_runs.read_artifact(patch_id, "plan.md").get("content") or ""
                )
            except (FileNotFoundError, ValueError):
                current = ""
        sources = _collect_plan_source_files(container, payload.source_refs)
        revised = await _revise_patch_plan_markdown(
            container,
            run=run,
            current=current,
            instruction=payload.instruction,
            sources=sources,
        )
        artifact = container.patch_runs.write_artifact(patch_id, "plan.md", revised)
        updated = container.patch_runs.save(
            run.with_updates(
                status="PLAN_CREATED",
                artifacts={
                    **run.artifacts,
                    "plan_path": artifact["path"],
                    "plan_markdown": revised,
                },
            )
        )
        summary = (
            "참고 파일과 지시를 합성해 plan.md를 작성했습니다."
            if sources
            else "대화 요청을 반영해 plan.md를 수정했습니다."
        )
        container.patch_runs.append_event(
            patch_id,
            event_type="plan.md.revised",
            summary=summary,
            payload={
                "actor": actor,
                "instruction": payload.instruction[:500],
                "source_refs": [str(item.get("id") or "") for item in sources],
            },
        )
        _audit(
            container,
            actor=actor,
            action="patchops.plan_md.revise",
            target="patch_run",
            target_id=patch_id,
        )
        return {
            "ok": True,
            "patch_run": updated.to_dict(),
            "file": container.patch_runs.read_artifact(patch_id, "plan.md"),
        }

    @router.post("/patch-runs/{patch_id}/plan-md/promote-memory")
    async def promote_patch_plan_memory(
        patch_id: str,
        payload: PatchPlanPromotePayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        try:
            run = container.patch_runs.read(patch_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        content = payload.content.strip()
        if not content:
            try:
                content = str(
                    container.patch_runs.read_artifact(patch_id, "plan.md").get("content") or ""
                ).strip()
            except (FileNotFoundError, ValueError):
                content = ""
        if not content:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="저장할 plan.md 내용이 없습니다. 먼저 plan.md를 작성하세요.",
            )
        promoted = container.permanent_memory.promote(
            title=f"코딩 에이전트 계획서: {run.request[:60]}",
            content=content,
            source_refs=[run.id],
            actor=actor,
        )
        container.patch_runs.append_event(
            patch_id,
            event_type="plan.md.promoted",
            summary="plan.md를 영구 메모리에 저장했습니다.",
            payload={"actor": actor, "memory": promoted},
        )
        _audit(
            container,
            actor=actor,
            action="patchops.plan_md.promote",
            target="patch_run",
            target_id=patch_id,
        )
        return {"ok": True, "patch_run": run.to_dict(), "memory": promoted}

    @router.post("/patch-runs/{patch_id}/analyze")
    async def analyze_patch_run_endpoint(
        patch_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        try:
            run = container.patch_runs.read(patch_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        async def complete(prompt: str, task: str) -> str:
            return await _complete_patchops_task(container, prompt, task=task)

        analyzed = await analyze_patch_run(
            container, run.with_updates(status="REPO_SCANNING"), complete
        )
        _audit(
            container,
            actor=actor,
            action="patchops.analyze",
            target="patch_run",
            target_id=patch_id,
        )
        return {
            "ok": True,
            "patch_run": analyzed.to_dict(),
            "events": container.patch_runs.list_events(patch_id),
        }

    @router.post("/patch-runs/{patch_id}/approve-plan")
    async def approve_patch_plan(
        patch_id: str,
        payload: PatchRunApprovalPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        status_value = "WAITING_APPROVAL" if payload.decision == "approve" else "CANCELLED"
        try:
            run = container.patch_runs.update(
                patch_id,
                status=status_value,
                approved_by=actor if payload.decision == "approve" else "",
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        container.patch_runs.append_event(
            patch_id,
            event_type="approval.decided",
            summary=f"패치 계획 {payload.decision}",
            payload={"decision": payload.decision, "comment": payload.comment, "actor": actor},
        )
        _audit(
            container,
            actor=actor,
            action="patchops.approval",
            target="patch_run",
            target_id=patch_id,
        )
        return {"ok": True, "patch_run": run.to_dict()}

    @router.post("/patch-runs/{patch_id}/draft-diff")
    async def draft_patch_diff(
        patch_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        try:
            run = container.patch_runs.read(patch_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        async def complete(prompt: str, task: str) -> str:
            return await _complete_patchops_task(container, prompt, task=task)

        drafted = await draft_patch_artifacts(container, run, complete)
        _audit(
            container,
            actor=actor,
            action="patchops.draft_diff",
            target="patch_run",
            target_id=patch_id,
        )
        return {
            "ok": True,
            "patch_run": drafted.to_dict(),
            "events": container.patch_runs.list_events(patch_id),
        }

    @router.post("/patch-runs/{patch_id}/write-memory")
    async def write_patch_run_memory(
        patch_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        try:
            run = container.patch_runs.read(patch_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        async def complete(prompt: str, task: str) -> str:
            return await _complete_patchops_task(container, prompt, task=task)

        memory = await write_patch_memory(container, run, complete, actor=actor)
        _audit(
            container,
            actor=actor,
            action="patchops.memory_write",
            target="patch_run",
            target_id=patch_id,
        )
        return {
            "ok": True,
            "memory": memory,
            "patch_run": container.patch_runs.read(patch_id).to_dict(),
        }

    @router.get("/patch-records")
    async def list_patch_records(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, list[PatchRecordPayload]]:
        _require(container, x_ng_user, "patch_records:read")
        return {
            "items": [_patch_record_payload(record) for record in container.patch_records.list()],
        }

    @router.get("/patch-records/{record_id}")
    async def read_patch_record(
        record_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> PatchRecordDetailPayload:
        _require(container, x_ng_user, "patch_records:read")
        record = container.patch_records.get(record_id)
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="패치 기록을 찾을 수 없습니다.")
        markdown = container.patch_records.read_markdown(record_id) or ""
        return _patch_record_detail_payload(record, markdown)

    @router.post("/patch-records")
    async def create_patch_record(
        payload: PatchRecordCreatePayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> PatchRecordDetailPayload:
        actor = _require(container, x_ng_user, "patch_records:write")
        if not payload.title.strip():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="title 은 필수입니다.",
            )
        record = container.patch_records.append(
            title=payload.title,
            summary=payload.summary,
            request=payload.request,
            plan=payload.plan,
            changed_files=payload.changed_files,
            verification=payload.verification,
            follow_ups=payload.follow_ups,
            tags=payload.tags,
            actor=actor,
            agent=payload.agent,
        )
        markdown = container.patch_records.read_markdown(record.record_id) or ""
        _audit(
            container,
            actor=actor,
            action="patch_record.create",
            target="patch_record",
            target_id=record.record_id,
        )
        return _patch_record_detail_payload(record, markdown)

    @router.get("/skills")
    async def list_skills(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {"skills": [skill.to_descriptor() for skill in get_skills().values()]}

    @router.post("/skills")
    async def create_skill(
        payload: SkillCreateRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        skill = Skill(
            id=payload.id.strip(),
            name=payload.name.strip(),
            description=payload.description.strip(),
            executor=payload.executor,
            category=payload.category.strip() or "general",
            required_permission=payload.required_permission.strip(),
            risk=payload.risk.strip() or "low",
            tool=payload.tool.strip(),
            output_format=payload.output_format.strip() or "auto",
            output_folder=payload.output_folder.strip() or "documents",
            task=payload.task.strip() or "document_generation",
            inputs=[
                SkillInput(
                    name=item.name.strip(),
                    type=item.type.strip() or "string",
                    required=item.required,
                    description=item.description.strip(),
                )
                for item in payload.inputs
                if item.name.strip()
            ],
            instructions=payload.instructions.strip(),
        )
        if skill.executor == "prompt" and not skill.instructions:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="prompt 스킬은 본문(instructions)이 필요합니다.",
            )
        if skill.executor == "tool" and not skill.tool:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="tool 스킬은 tool 이름이 필요합니다."
            )
        try:
            register_skill(skill)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        _audit(
            container,
            actor=actor,
            action="skill.create",
            target="skill",
            target_id=skill.id,
        )
        return {
            "ok": True,
            "skill": skill.to_descriptor(),
            "skills": [item.to_descriptor() for item in get_skills().values()],
        }

    @router.post("/skills/{skill_id}/run")
    async def run_skill_endpoint(
        skill_id: str,
        payload: SkillRunRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        skill = get_skill(skill_id)
        if skill is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="해당 스킬을 찾을 수 없습니다.")
        actor = _require(container, x_ng_user, skill.required_permission or "work:read")

        async def _completion(prompt: str, image_parts: list[dict[str, Any]] | None) -> str:
            return await _complete_office_task(
                container, prompt, task=skill.task, image_parts=image_parts
            )

        try:
            result = await run_skill(
                container, skill_id, dict(payload.inputs), actor=actor, completion=_completion
            )
        except SkillError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        _audit(
            container,
            actor=actor,
            action="skill.run",
            target="skill",
            target_id=skill_id,
            details={"status": result.status},
        )
        return {"ok": result.status == "succeeded", "result": result.to_dict()}

    return router
