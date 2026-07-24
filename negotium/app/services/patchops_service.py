"""PatchOps MVP orchestration helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from negotium.app.services.context_firewall_service import (
    load_context_firewall_policy,
    record_firewall_audit,
    sanitize_context,
)
from negotium.app.services.issue_memory_service import (
    capture_manual_issue,
    ensure_patch_candidate,
    ensure_test_requirement,
    search_issue_memory,
)
from negotium.app.services.test_writer_service import (
    detect_test_frameworks,
    find_existing_test_patterns,
    run_test_command,
)
from negotium.archive.issue_memory import IssueCluster, PatchCandidate, TestRequirement
from negotium.archive.patch_runs import PatchRun
from negotium.context.ast_indexer import AstIndexer
from negotium.prompts import render as render_prompt

if TYPE_CHECKING:
    from negotium.app.container import Container

PatchComplete = Callable[[str, str], Awaitable[str]]

CODE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".java",
    ".rb",
    ".md",
    ".toml",
    ".json",
    ".yml",
    ".yaml",
}
SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
}
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|private[_-]?key|password|passwd|jwt[_-]?secret|token|secret)\s*[:=]\s*['\"]?[^'\"\s]+"
)
HIGH_RISK_RE = re.compile(
    r"(?i)(auth|payment|permission|access|secret|credential|delete|infra|migration)"
)


async def analyze_patch_run(
    container: Container, run: PatchRun, complete: PatchComplete
) -> PatchRun:
    container.patch_runs.append_event(
        run.id, event_type="repo.scanned", summary="저장소 후보 파일 스캔을 시작했습니다."
    )
    context = build_codebase_context(container, run)
    context = await enrich_context_with_issue_memory(container, run, context, complete)
    context = sanitize_patchops_context(container, run, context)
    container.patch_runs.append_event(
        run.id,
        event_type="repo.scanned",
        summary=f"후보 파일 {len(context['candidate_files'])}개와 테스트 후보 {len(context['test_files'])}개를 찾았습니다.",
        payload={
            "candidate_files": context["candidate_files"],
            "test_files": context["test_files"],
        },
    )
    for file_path in context["candidate_files"][:8]:
        container.patch_runs.append_event(
            run.id, event_type="file.read", summary=f"{file_path} 요약 완료"
        )

    questions_prompt = render_prompt(
        "patchops/interview.md.j2",
        request=run.request,
        context_md=context["context_md"],
        memory_md=context["memory_md"],
    )
    questions_raw = await complete(questions_prompt, "patch_interview")
    questions = parse_json_array(questions_raw) or fallback_questions(run.request, context)
    for question in questions:
        container.patch_runs.append_event(
            run.id,
            event_type="question.created",
            summary=str(question.get("question") or "Patch interview question"),
            payload=question,
        )

    plan_prompt = render_prompt(
        "patchops/plan.md.j2",
        request=run.request,
        privacy_mode=run.privacy_mode,
        autonomy_level=run.autonomy_level,
        context_md=context["context_md"],
        questions_md=json.dumps(questions, ensure_ascii=False, indent=2),
        memory_md=context["memory_md"],
    )
    plan_raw = await complete(plan_prompt, "patch_planning")
    plan = parse_json_object(plan_raw) or fallback_plan(run.request, context, questions)
    plan = apply_policy_to_plan(plan)
    plan_artifact = container.patch_runs.write_artifact(
        run.id,
        "plan.md",
        render_plan_markdown(run, plan=plan, questions=questions, context=context),
    )
    container.patch_runs.append_event(
        run.id,
        event_type="patch.plan.updated",
        summary=f"패치 계획 생성 완료: risk={plan.get('risk_level', 'medium')}",
        payload={**plan, "plan_path": plan_artifact["path"]},
    )
    artifacts = {
        "plan_path": plan_artifact["path"],
        "test_requirements": context.get("test_requirements", []),
        "test_frameworks": context.get("test_frameworks", {}),
        "test_patterns": context.get("test_patterns", {}),
        "test_writer_notes": ["AI Test Writer will draft test-only diff after plan approval."],
    }
    return container.patch_runs.save(
        run.with_updates(
            status="WAITING_APPROVAL" if plan.get("approval_required", True) else "PLAN_CREATED",
            risk_level=str(plan.get("risk_level") or "medium"),
            context=context,
            questions=questions,
            plan=plan,
            artifacts=artifacts,
        )
    )


async def draft_patch_artifacts(
    container: Container, run: PatchRun, complete: PatchComplete
) -> PatchRun:
    context_md = str(run.context.get("context_md") or "")
    plan_md = json.dumps(run.plan, ensure_ascii=False, indent=2)
    diff_prompt = render_prompt(
        "patchops/diff_draft.md.j2",
        request=run.request,
        plan_md=plan_md,
        context_md=context_md,
    )
    diff_raw = await complete(diff_prompt, "patch_diff_draft")
    diff_payload = parse_json_object(diff_raw) or fallback_diff_artifact(run)
    diff_payload["diff_draft"] = _sanitize_patchops_text(
        container,
        str(diff_payload.get("diff_draft") or ""),
        task_type="patch_diff_draft",
        source_uri="patchops://diff",
    )
    container.patch_runs.append_event(
        run.id,
        event_type="diff.proposed",
        summary="검토용 diff 초안과 검증 명령을 생성했습니다.",
        payload={"verification_commands": diff_payload.get("verification_commands", [])},
    )

    docs_prompt = render_prompt(
        "patchops/pr_description.md.j2",
        request=run.request,
        plan_md=plan_md,
        diff_draft=diff_payload.get("diff_draft", ""),
    )
    docs_raw = await complete(docs_prompt, "patch_review")
    docs_payload = parse_json_object(docs_raw) or fallback_docs(run, diff_payload)
    test_prompt = render_prompt(
        "patchops/test_writer.md.j2",
        request=run.request,
        plan_md=plan_md,
        test_requirements_md=json.dumps(
            run.artifacts.get("test_requirements", []), ensure_ascii=False, indent=2
        ),
        context_md=context_md,
    )
    test_raw = await complete(test_prompt, "patch_test_writer")
    test_payload = parse_json_object(test_raw) or fallback_test_writer_artifact(run)
    test_payload["test_diff_draft"] = _sanitize_patchops_text(
        container,
        str(test_payload.get("test_diff_draft") or ""),
        task_type="patch_test_writer",
        source_uri="patchops://test-diff",
    )
    test_payload["test_run_preview"] = run_test_command(
        Path(str(run.context.get("repo_root") or container.settings.workspace_dir)),
        command="python -m pytest -q",
        dry_run=True,
    )
    container.patch_runs.append_event(
        run.id,
        event_type="test.diff.proposed",
        summary="AI Test Writer가 테스트 diff 초안을 생성했습니다.",
        payload={"test_plan": test_payload.get("test_plan", [])},
    )
    plan_artifact = container.patch_runs.write_artifact(
        run.id,
        "plan.md",
        render_plan_markdown(
            run,
            plan=run.plan,
            questions=run.questions,
            context=run.context,
            diff_payload=diff_payload,
            docs_payload=docs_payload,
            test_payload=test_payload,
        ),
    )
    artifacts = {
        **run.artifacts,
        **diff_payload,
        **docs_payload,
        **test_payload,
        "plan_path": plan_artifact["path"],
    }
    return container.patch_runs.save(
        run.with_updates(status="VERIFICATION_PLANNED", artifacts=artifacts)
    )


async def write_patch_memory(
    container: Container, run: PatchRun, complete: PatchComplete, *, actor: str
) -> dict[str, object]:
    artifacts_md = json.dumps(run.artifacts, ensure_ascii=False, indent=2)
    prompt = render_prompt(
        "patchops/memory_summary.md.j2",
        request=run.request,
        plan_md=json.dumps(run.plan, ensure_ascii=False, indent=2),
        questions_md=json.dumps(run.questions, ensure_ascii=False, indent=2),
        artifacts_md=artifacts_md,
    )
    raw = await complete(prompt, "patch_memory")
    memory = _sanitize_patchops_text(
        container,
        raw.strip() or fallback_memory(run),
        task_type="patch_memory",
        source_uri="patchops://memory",
    )
    promoted = container.permanent_memory.promote(
        title=f"PatchOps Memory: {run.request[:60]}",
        content=memory,
        source_refs=[run.id],
        actor=actor,
    )
    container.patch_runs.append_event(
        run.id,
        event_type="memory.written",
        summary="PatchOps 영구 메모리를 저장했습니다.",
        payload={"memory": promoted},
    )
    container.patch_runs.save(run.with_updates(status="COMPLETED"))
    return promoted


def build_codebase_context(container: Container, run: PatchRun) -> dict[str, Any]:
    root = _repo_root(container.settings.workspace_dir, run.repo_id)
    files = _repo_files(root)
    keywords = _keywords(run.request)
    candidate_files = _candidate_files(root, files, keywords)
    test_files = [path for path in files if _is_test_file(path)]
    ast_paths = [root / path for path in candidate_files[:20]]
    ast_summary = AstIndexer(token_budget=12000).summarize(ast_paths).to_markdown()
    tree_md = "\n".join(f"- {path}" for path in files[:120])
    candidate_md = "\n".join(f"- {path}" for path in candidate_files[:30]) or "- 후보 파일 없음"
    test_md = "\n".join(f"- {path}" for path in test_files[:20]) or "- 테스트 후보 없음"
    memory_sources = container.permanent_memory.search(run.request, limit=5)
    test_frameworks = detect_test_frameworks(root)
    test_patterns = find_existing_test_patterns(root, query=run.request)
    memory_md = "\n".join(
        f"- {item.get('path')}: {item.get('title')}\n  {item.get('excerpt')}"
        for item in memory_sources
    )
    context_md = "\n\n".join(
        [
            f"Repo root: {root}",
            "## File tree\n" + tree_md,
            "## Candidate files\n" + candidate_md,
            "## Test candidates\n" + test_md,
            "## AST summary\n" + ast_summary,
        ]
    )
    return {
        "repo_root": str(root),
        "keywords": keywords,
        "candidate_files": candidate_files[:50],
        "test_files": test_files[:50],
        "ast_summary": ast_summary,
        "memory_sources": memory_sources,
        "memory_md": memory_md,
        "test_frameworks": test_frameworks,
        "test_patterns": test_patterns,
        "context_md": context_md,
        "policy": context_policy(run.privacy_mode),
    }


async def enrich_context_with_issue_memory(
    container: Container, run: PatchRun, context: dict[str, Any], complete: PatchComplete
) -> dict[str, Any]:
    issue_memory = search_issue_memory(container.issue_memory, run.request, limit=5)
    clusters = list(issue_memory.get("clusters", []))
    if not clusters:
        captured = capture_manual_issue(
            container.issue_memory,
            {
                "title": run.request[:120],
                "summary": run.request,
                "provider": "manual",
                "affected_repos": [run.repo_id or "local"],
                "external_uri": f"patchops:{run.id}",
            },
        )
        clusters = [captured["cluster"]]
    candidates = [
        candidate
        for cluster in clusters
        for candidate in cluster.get("patch_candidates", [])
        if isinstance(candidate, dict)
    ]
    if not candidates and clusters:
        cluster = IssueCluster.create(**clusters[0])
        candidate = ensure_patch_candidate(container.issue_memory, cluster, target_repo=run.repo_id)
        requirement = ensure_test_requirement(container.issue_memory, candidate, cluster)
        candidates = [candidate.to_dict()]
        clusters[0]["patch_candidates"] = candidates
        clusters[0]["test_requirements"] = [requirement.to_dict()]
    requirements = [
        requirement
        for cluster in clusters
        for requirement in cluster.get("test_requirements", [])
        if isinstance(requirement, dict)
    ]
    if clusters and not requirements:
        cluster = IssueCluster.create(**clusters[0])
        candidate = (
            PatchCandidate.create(**candidates[0])
            if candidates
            else ensure_patch_candidate(container.issue_memory, cluster, target_repo=run.repo_id)
        )
        requirement = ensure_test_requirement(container.issue_memory, candidate, cluster)
        requirements = [requirement.to_dict()]
    generated_requirements = await generate_test_requirements(
        run, context, clusters, requirements, complete
    )
    for item in generated_requirements:
        if not isinstance(item, dict) or not candidates:
            continue
        payload = {
            **item,
            "patch_candidate_id": str(candidates[0].get("id") or ""),
            "status": "proposed",
        }
        saved = container.issue_memory.save_test_requirement(TestRequirement.create(**payload))
        requirements.append(saved.to_dict())
    issue_memory_md = _issue_memory_md(clusters, candidates, requirements)
    return {
        **context,
        "issue_clusters": clusters,
        "patch_candidates": candidates,
        "test_requirements": requirements,
        "issue_memory_md": issue_memory_md,
        "context_md": context["context_md"] + "\n\n## Issue Memory\n" + issue_memory_md,
    }


async def generate_test_requirements(
    run: PatchRun,
    context: dict[str, Any],
    clusters: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    complete: PatchComplete,
) -> list[dict[str, Any]]:
    if existing:
        return []
    prompt = render_prompt(
        "patchops/test_requirements.md.j2",
        request=run.request,
        issue_memory_md=_issue_memory_md(clusters, [], []),
        test_files_md="\n".join(f"- {item}" for item in context.get("test_files", [])[:20]),
    )
    return parse_json_array(await complete(prompt, "patch_test_requirements")) or []


def context_policy(privacy_mode: str) -> dict[str, object]:
    if privacy_mode == "local_only":
        return {"allow_frontier": False, "context_policy": "code_local_only"}
    if privacy_mode == "frontier_assisted":
        return {"allow_frontier": True, "context_policy": "allowed_files_may_include_snippets"}
    return {"allow_frontier": True, "context_policy": "redacted_summaries_only"}


def sanitize_patchops_context(
    container: Container, run: PatchRun, context: dict[str, Any]
) -> dict[str, Any]:
    policy = load_context_firewall_policy(container.settings.workspace_dir)
    sanitized_context = dict(context)
    for key, task_type in {
        "context_md": "patchops_context",
        "memory_md": "patchops_memory_context",
        "issue_memory_md": "issue_memory_context",
    }.items():
        if key not in sanitized_context:
            continue
        result = sanitize_context(
            str(sanitized_context.get(key) or ""),
            destination="frontier_llm" if run.privacy_mode != "local_only" else "local_llm",
            task_type=task_type,
            source_uri=f"patchops://{run.id}/{key}",
            policy=policy,
        )
        result = record_firewall_audit(
            container,
            result,
            agent_run_id=run.id,
            destination="frontier_llm" if run.privacy_mode != "local_only" else "local_llm",
            task_type=task_type,
        )
        sanitized_context[key] = str(result.sanitized)
        sanitized_context.setdefault("context_firewall", {})[key] = {
            "audit_id": result.audit_id,
            "decision": result.decision,
            "highest_sensitivity": result.highest_sensitivity,
            "removed_counts": result.removed_counts,
            "blocked_items": result.blocked_items,
        }
    return sanitized_context


def _sanitize_patchops_text(
    container: Container, text: str, *, task_type: str, source_uri: str
) -> str:
    policy = load_context_firewall_policy(container.settings.workspace_dir)
    result = sanitize_context(
        redact_secrets(text),
        destination="local_storage",
        task_type=task_type,
        source_uri=source_uri,
        policy=policy,
    )
    record_firewall_audit(
        container,
        result,
        destination="local_storage",
        task_type=task_type,
    )
    return str(result.sanitized)


def parse_json_object(raw: str) -> dict[str, Any] | None:
    loaded = _load_json(raw)
    return loaded if isinstance(loaded, dict) else None


def parse_json_array(raw: str) -> list[dict[str, Any]] | None:
    loaded = _load_json(raw)
    if not isinstance(loaded, list):
        return None
    return [item for item in loaded if isinstance(item, dict)]


def fallback_questions(request: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "question": "요청과 가장 관련된 코드 경로가 어디인가?",
            "why_it_matters": "수정 전 영향 범위를 좁혀야 합니다.",
            "can_answer_from_code": True,
            "required_tool": "repo.search_text",
            "risk_if_unanswered": "관련 없는 파일을 수정할 수 있습니다.",
            "priority": "high",
            "answer": ", ".join(context.get("candidate_files", [])[:5]),
            "needs_human": False,
        },
        {
            "question": "이 변경이 인증, 권한, 결제, 삭제, 배포 설정에 영향을 주는가?",
            "why_it_matters": "고위험 영역은 사람 승인과 추가 검증이 필요합니다.",
            "can_answer_from_code": True,
            "required_tool": "repo.search_text",
            "risk_if_unanswered": "보안 회귀가 발생할 수 있습니다.",
            "priority": "high",
            "answer": "후보 파일 경로에서 고위험 키워드를 검사하세요.",
            "needs_human": False,
        },
    ]


def fallback_plan(
    request: str, context: dict[str, Any], questions: list[dict[str, Any]]
) -> dict[str, Any]:
    candidate_files = list(context.get("candidate_files", []))[:8]
    high_risk = any(is_high_risk_path(path) for path in candidate_files)
    return {
        "goal": request,
        "current_understanding": [
            f"후보 파일 {len(candidate_files)}개를 찾았습니다.",
            "AST 요약과 테스트 후보를 기반으로 최소 변경 계획을 세웁니다.",
        ],
        "assumptions": ["자동 diff 적용은 하지 않고 검토용 초안만 생성합니다."],
        "questions": questions,
        "target_files": candidate_files,
        "patch_steps": [
            "후보 파일을 추가 확인합니다.",
            "영향 범위와 테스트 후보를 확정합니다.",
            "최소 변경 unified diff 초안을 작성합니다.",
            "테스트/린트/타입체크 명령을 제안합니다.",
        ],
        "risk_level": "high" if high_risk else "medium",
        "risk_reasons": ["고위험 경로 포함"] if high_risk else ["코드 변경 전 검증 필요"],
        "test_plan": _test_commands(candidate_files, list(context.get("test_files", []))),
        "rollback_plan": ["제안 diff를 적용하지 않거나 적용 후 revert합니다."],
        "approval_required": True,
    }


def fallback_diff_artifact(run: PatchRun) -> dict[str, Any]:
    return {
        "diff_draft": "",
        "implementation_notes": ["MVP 안전 모드에서는 코드 원문 검토 후 diff 초안을 생성합니다."],
        "verification_commands": run.plan.get("test_plan", []),
        "risk_notes": run.plan.get("risk_reasons", []),
    }


def render_plan_markdown(
    run: PatchRun,
    *,
    plan: dict[str, Any],
    questions: list[dict[str, Any]],
    context: dict[str, Any],
    diff_payload: dict[str, Any] | None = None,
    docs_payload: dict[str, Any] | None = None,
    test_payload: dict[str, Any] | None = None,
) -> str:
    steps = plan.get("patch_steps") or plan.get("steps") or []
    target_files = [str(item) for item in plan.get("target_files", [])]
    tests = [str(item) for item in plan.get("test_plan", [])]
    risks = [str(item) for item in plan.get("risk_reasons", [])]
    diff_payload = diff_payload or {}
    docs_payload = docs_payload or {}
    test_payload = test_payload or {}
    question_lines = [
        f"- {item.get('question', '확인 질문')} ({item.get('priority', 'normal')})"
        for item in questions
    ]
    step_lines = [f"{index + 1}. {step}" for index, step in enumerate(steps)]
    return "\n".join(
        [
            f"# 코딩 에이전트 계획서 - {run.request[:80]}",
            "",
            f"- Patch Run: `{run.id}`",
            f"- Repo: `{run.repo_id}`",
            f"- Autonomy: `{run.autonomy_level}`",
            f"- Privacy: `{run.privacy_mode}`",
            f"- Risk: `{plan.get('risk_level', run.risk_level)}`",
            f"- Approval required: `{plan.get('approval_required', True)}`",
            "",
            "## Goal",
            str(plan.get("goal") or run.request),
            "",
            "## Target Files",
            *(f"- `{path}`" for path in target_files),
            "",
            "## Questions",
            *(question_lines or ["- 추가 질문 없음"]),
            "",
            "## Steps",
            *(step_lines or ["1. 후보 파일과 테스트를 추가 확인합니다."]),
            "",
            "## Test Plan",
            *(f"- `{cmd}`" for cmd in tests),
            "",
            "## Risk Notes",
            *(f"- {risk}" for risk in risks),
            "",
            "## Code Change Draft",
            str(diff_payload.get("diff_draft") or "아직 코드 변경안 초안이 생성되지 않았습니다."),
            "",
            "## Implementation Notes",
            *(
                f"- {note}"
                for note in diff_payload.get("implementation_notes", [])
                if isinstance(note, str)
            ),
            "",
            "## Test Draft",
            str(test_payload.get("test_diff_draft") or "아직 테스트 초안이 생성되지 않았습니다."),
            "",
            "## Test Writer Notes",
            *(
                f"- {note}"
                for note in test_payload.get("test_writer_notes", [])
                if isinstance(note, str)
            ),
            "",
            "## PR Draft",
            str(docs_payload.get("pr_description") or "아직 PR 초안이 생성되지 않았습니다."),
            "",
            "## Internal Patch Note",
            str(
                docs_payload.get("internal_patch_note")
                or "아직 내부 패치 노트가 생성되지 않았습니다."
            ),
            "",
            "## Context Sources",
            *(f"- `{path}`" for path in context.get("candidate_files", [])[:20]),
            "",
        ]
    )


def fallback_test_writer_artifact(run: PatchRun) -> dict[str, Any]:
    requirements = run.artifacts.get("test_requirements", [])
    titles = [
        str(item.get("title"))
        for item in requirements
        if isinstance(item, dict) and item.get("title")
    ]
    return {
        "test_plan": run.plan.get("test_plan", []),
        "test_diff_draft": "",
        "test_writer_notes": titles
        or ["관련 테스트 파일을 확인한 뒤 regression test diff를 작성해야 합니다."],
    }


def fallback_docs(run: PatchRun, diff_payload: dict[str, Any]) -> dict[str, str]:
    summary = run.plan.get("goal") or run.request
    tests = "\n".join(f"- {cmd}" for cmd in diff_payload.get("verification_commands", []))
    return {
        "pr_description": f"## Summary\n\n{summary}\n\n## Test Plan\n{tests or '- 테스트 명령 확인 필요'}",
        "internal_patch_note": f"# 내부 패치 노트\n\n## 변경 목적\n\n{summary}\n\n## 검증\n\n{tests or '- 검증 계획 수립 필요'}",
        "customer_release_note": "## 안정성 개선\n\n내부 코드 변경 요청에 대한 패치 계획과 검증 초안을 준비했습니다.",
    }


def fallback_memory(run: PatchRun) -> str:
    return "\n".join(
        [
            f"# PatchOps Memory: {run.request}",
            "",
            "## Patch Plan",
            json.dumps(run.plan, ensure_ascii=False, indent=2),
            "",
            "## Future Guidance",
            "- 관련 패치 전 후보 파일과 테스트 후보를 먼저 확인하세요.",
            "- 인증/권한/결제/삭제/배포 설정은 사람 승인을 유지하세요.",
        ]
    )


def apply_policy_to_plan(plan: dict[str, Any]) -> dict[str, Any]:
    target_files = [str(item) for item in plan.get("target_files", [])]
    high_risk = any(is_high_risk_path(path) for path in target_files)
    if high_risk:
        plan["risk_level"] = "high"
        plan["approval_required"] = True
        reasons = [str(item) for item in plan.get("risk_reasons", [])]
        reasons.append("고위험 경로(auth/payment/permission/infra/delete/secret) 포함")
        plan["risk_reasons"] = list(dict.fromkeys(reasons))
    plan.setdefault("approval_required", True)
    plan.setdefault("test_plan", _test_commands(target_files, []))
    return plan


def is_high_risk_path(path: str) -> bool:
    return bool(HIGH_RISK_RE.search(path))


def redact_secrets(text: str) -> str:
    return SECRET_RE.sub(lambda match: f"{match.group(1)}=<redacted>", text)


def _repo_root(workspace_dir: Path, repo_id: str) -> Path:
    if repo_id in {"", "local", "."}:
        return workspace_dir
    candidate = workspace_dir / repo_id.replace("/", "__")
    return candidate if candidate.exists() else workspace_dir


def _repo_files(root: Path) -> list[str]:
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix.lower() not in CODE_SUFFIXES:
            continue
        files.append(rel.as_posix())
        if len(files) >= 500:
            break
    return files


def _keywords(request: str) -> list[str]:
    words = re.findall(r"[\w가-힣]{3,}", request.lower())
    return list(dict.fromkeys(words))[:12]


def _candidate_files(root: Path, files: list[str], keywords: list[str]) -> list[str]:
    scored: list[tuple[int, str]] = []
    for rel in files:
        score = sum(2 for keyword in keywords if keyword in rel.lower())
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="ignore")[:8000].lower()
        except OSError:
            text = ""
        score += sum(1 for keyword in keywords if keyword in text)
        if _is_test_file(rel):
            score -= 1
        if score > 0:
            scored.append((score, rel))
    if not scored:
        scored = [(1, rel) for rel in files[:20] if not _is_test_file(rel)]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [rel for _, rel in scored]


def _is_test_file(path: str) -> bool:
    lowered = path.lower()
    return (
        "/test" in lowered
        or lowered.startswith("test")
        or ".test." in lowered
        or "_test." in lowered
    )


def _test_commands(candidate_files: list[str], test_files: list[str]) -> list[str]:
    commands = [
        "python -m pytest -q",
        "python -m ruff check .",
        "python -m mypy negotium tests",
    ]
    if any(
        path.startswith("frontend/") or path.endswith((".ts", ".tsx"))
        for path in candidate_files + test_files
    ):
        commands.append("npm run build --prefix frontend")
    return commands


def _issue_memory_md(
    clusters: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
) -> str:
    cluster_md = (
        "\n".join(
            f"- [{item.get('severity', 'medium')}] {item.get('title')} ({item.get('id')})"
            for item in clusters[:5]
        )
        or "- 관련 issue cluster 없음"
    )
    candidate_md = (
        "\n".join(
            f"- [{item.get('risk_level', 'medium')}] {item.get('title')} ({item.get('id')})"
            for item in candidates[:5]
        )
        or "- 관련 patch candidate 없음"
    )
    requirement_md = (
        "\n".join(
            f"- [{item.get('priority', 'medium')}] {item.get('title')}: "
            f"Given {item.get('given')} / When {item.get('when')} / Then {item.get('then')}"
            for item in requirements[:8]
        )
        or "- 관련 test requirement 없음"
    )
    return "\n\n".join(
        [
            "### Issue Clusters\n" + cluster_md,
            "### Patch Candidates\n" + candidate_md,
            "### Test Requirements\n" + requirement_md,
        ]
    )


def _load_json(raw: str) -> Any | None:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start_obj = text.find("{")
    start_arr = text.find("[")
    starts = [idx for idx in (start_obj, start_arr) if idx >= 0]
    if starts:
        start = min(starts)
        end = text.rfind("}" if start == start_obj else "]")
        if end > start:
            text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
