"""Shared helpers for the frontend API routers.

Extracted verbatim from the former monolithic negotium.app.api module; the
domain routers under negotium/app/api/*.py import from here.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import HTTPException, status

from negotium.adapters.llm.anthropic_adapter import AnthropicProvider
from negotium.adapters.llm.catalog import (
    default_base_url,
    model_supports_audio,
    model_supports_vision,
    provider_payload,
)
from negotium.adapters.llm.gateway import LlmGateway
from negotium.adapters.llm.gemini_adapter import GeminiProvider
from negotium.adapters.llm.openai_adapter import OpenAiProvider
from negotium.adapters.llm.vllm_adapter import VllmConnectionError, VllmProvider
from negotium.adapters.llm.vllm_embedded_adapter import VllmEmbeddedError
from negotium.app.container import Container
from negotium.app.initial_setup import ParsedSetupFile
from negotium.app.schemas.core import (
    AiJobStatusPayload,
    ChatRequest,
    ChatResponse,
    CompanyProfilePayload,
    DiscordChannelBindingPayload,
    DiscordConnectorPayload,
    DocumentReadPayload,
    GeneratedDocumentPayload,
    GitHubConnectorPayload,
    HiringRequest,
    InitialOfficeSetupResult,
    IntegrationConfigPayload,
    IntegrationStatusPayload,
    LocalLlmStatusPayload,
    PatchRecordDetailPayload,
    PatchRecordPayload,
    ProcessPlanPayload,
    ReadableContextBundlePayload,
    ReadableContextPreviewRequest,
    ReadableContextSourcePayload,
    TokenLimitPayload,
    TokenLimitStatusPayload,
    TokenUsageEntryPayload,
    TokenUsageSummaryPayload,
    VolatileMemoryPayload,
)
from negotium.app.services.attachment_service import extract_attachment
from negotium.app.services.context_firewall_service import (
    load_context_firewall_policy,
    record_firewall_audit,
    sanitize_llm_messages,
    sanitize_llm_response,
)
from negotium.app.services.document_output import (
    resolve_output_format,
    write_generated_doc,
)
from negotium.app.services.setup_catalog import (
    recommend_patchnote_setup,
    render_recommendation_markdown,
)
from negotium.app.services.skill_registry import (
    get_skill,
    get_skills,
)
from negotium.app.services.skill_runtime import SkillError, run_skill
from negotium.archive.access_control import ALL_PERMISSIONS
from negotium.archive.ai_jobs import AiJobRecord
from negotium.archive.integration_config import (
    DiscordChannelBindingConfig,
    DiscordConnectorConfig,
    GitHubConnectorConfig,
    IntegrationConfig,
)
from negotium.archive.llm_runtime import LlmProviderName, LlmRuntimeConfig, LlmTaskRoute
from negotium.archive.patch_records import PatchRecord
from negotium.archive.patch_runs import PatchRun
from negotium.archive.process_plans import ProcessPlan
from negotium.archive.schema import parse_front_matter
from negotium.archive.secret_store import ApiKeyRecord
from negotium.archive.token_usage import (
    TokenLimitExceededError,
)
from negotium.archive.volatile_memory import VolatileMemory
from negotium.archive.work_memory import WorkScheduleItem
from negotium.domain.entities import LlmRoute
from negotium.domain.ports import (
    LlmMessage,
    LlmResponse,
    audio_part,
    flatten_message_text,
    image_part,
    text_part,
)
from negotium.prompts import render as render_prompt

_PRELOAD_TASKS: set[asyncio.Task[None]] = set()


def _selected_upload_records(
    records: list[dict[str, str]], upload_ids: list[str]
) -> list[dict[str, str]]:
    if not upload_ids:
        return records[:5]
    wanted = {item.strip() for item in upload_ids if item.strip()}
    return [record for record in records if str(record.get("id") or "") in wanted]


def _initial_office_setup_prompt(
    *,
    message: str,
    intent: str,
    parsed_files: list[ParsedSetupFile],
    company_profile: CompanyProfilePayload | None = None,
) -> str:
    file_blocks = "\n\n".join(file.to_prompt_block() for file in parsed_files)
    profile = company_profile or CompanyProfilePayload()
    return render_prompt(
        "office/initial_office_setup.md.j2",
        intent=intent,
        message=message,
        file_blocks=file_blocks,
        company_profile=profile.model_dump(),
        market_positioning=render_prompt("catalogs/patchnote_market.md.j2").strip(),
    ).strip()


def _parse_initial_setup_result(
    raw: str,
    *,
    parsed_files: list[ParsedSetupFile],
    company_profile: CompanyProfilePayload | None = None,
) -> InitialOfficeSetupResult:
    profile = company_profile or CompanyProfilePayload()
    recommendation = recommend_patchnote_setup(
        profile,
        sensitive_hint=any(file.sensitive_hint for file in parsed_files),
    )
    operations_seed = recommendation.pop("operations_memory_seed", {}) or {}
    work_seed = recommendation.pop("work_memory_seed", {}) or {}
    data = _try_load_json_object(raw)
    if data is None:
        data = {
            "operations_memory": _fallback_operations_memory(parsed_files),
            "work_memory": {
                "goals": "초기 오피스 환경 세팅",
                "current_focus": "업로드 파일 검토와 조직/사용자 명세 정리",
                "next_actions": "AI 분석 결과를 검토한 뒤 적용하세요.",
            },
            "roles": [],
            "users": _fallback_users(parsed_files),
            "notes": ["LLM 응답을 JSON으로 파싱하지 못해 파일 기반 기본 초안을 만들었습니다."],
            "warnings": [],
            "questions": ["회사명, 부서 구조, 직함별 권한을 최종 확인하세요."],
        }
    for key, value in recommendation.items():
        data.setdefault(key, value)
    operations_memory = dict(data.get("operations_memory") or {})
    for key, value in operations_seed.items():
        if value and not str(operations_memory.get(key) or "").strip():
            operations_memory[key] = value
    data["operations_memory"] = operations_memory
    work_memory = dict(data.get("work_memory") or {})
    for key, value in work_seed.items():
        if value and not str(work_memory.get(key) or "").strip():
            work_memory[key] = value
    data["work_memory"] = work_memory
    data.setdefault("sensitive_hint", any(file.sensitive_hint for file in parsed_files))
    if data.get("sensitive_hint"):
        warnings = list(data.get("warnings") or [])
        warnings.append("민감정보가 포함될 수 있으므로 로컬 에이전트 서버 사용을 권장합니다.")
        data["warnings"] = list(dict.fromkeys(str(item) for item in warnings))
    return InitialOfficeSetupResult.model_validate(data)


def _initial_setup_memories_with_recommendations(
    payload: InitialOfficeSetupResult,
) -> tuple[dict[str, Any], dict[str, Any]]:
    operations_memory = dict(payload.operations_memory)
    work_memory = dict(payload.work_memory)
    has_recommendations = any(
        [
            payload.agent_packs,
            payload.templates,
            payload.workflows,
            payload.security_defaults,
            payload.integration_priorities,
            payload.first_14_days,
        ]
    )
    if not has_recommendations:
        return operations_memory, work_memory

    recommendation_md = render_recommendation_markdown(payload.model_dump())
    operations_memory.setdefault(
        "office_project",
        f"{payload.recommended_package or 'Patch Note Team'} 계정 맞춤 도입",
    )
    operations_memory.setdefault("active_plan", "계정 맞춤 Patch Note 조립안 검토 및 적용")
    operations_memory["key_workflows"] = _join_markdown_blocks(
        str(operations_memory.get("key_workflows") or ""),
        recommendation_md,
    )
    security_lines = [
        str(item.get("name") or item.get("id") or "")
        for item in payload.security_defaults
        if item.get("enabled", True)
    ]
    if security_lines:
        operations_memory["sensitive_policy"] = _join_markdown_blocks(
            str(operations_memory.get("sensitive_policy") or ""),
            "초기 보안 기본값:\n" + "\n".join(f"- {line}" for line in security_lines if line),
        )

    work_memory.setdefault("goals", "첫 30일 동안 Patch Note 기반 AI 업무 운영 레이어 정착")
    work_memory["active_projects"] = _join_markdown_blocks(
        str(work_memory.get("active_projects") or ""),
        _items_to_lines("에이전트 팩", payload.agent_packs),
        _items_to_lines("템플릿", payload.templates),
    )
    work_memory["next_actions"] = _join_markdown_blocks(
        str(work_memory.get("next_actions") or ""),
        "\n".join(f"- {item}" for item in payload.first_14_days),
    )
    if payload.human_review_required:
        work_memory["risks"] = _join_markdown_blocks(
            str(work_memory.get("risks") or ""),
            "사람 검토 필수 업무:\n"
            + "\n".join(f"- {item}" for item in payload.human_review_required),
        )
    return operations_memory, work_memory


def _apply_initial_setup_llm_routes(
    container: Container,
    routes: dict[str, dict[str, str]],
) -> None:
    runtime = container.llm_runtime.read()
    merged = dict(runtime.task_routes or {})
    for task, route in routes.items():
        if isinstance(route, dict):
            merged[str(task)] = LlmTaskRoute.from_mapping(route, fallback=runtime)
    container.llm_runtime.write(
        LlmRuntimeConfig(
            local_enabled=runtime.local_enabled,
            api_enabled=runtime.api_enabled,
            default_route=runtime.default_route,
            default_provider=runtime.default_provider,
            local_model=runtime.local_model,
            task_routes=merged or None,
        )
    )


def _join_markdown_blocks(*blocks: str) -> str:
    return "\n\n".join(block.strip() for block in blocks if block.strip())


def _items_to_lines(title: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    lines = [f"{title}:"]
    for item in items:
        name = item.get("name") or item.get("id")
        description = item.get("description") or item.get("reason") or item.get("priority") or ""
        lines.append(f"- {name}: {description}".rstrip(": "))
    return "\n".join(lines)


def _try_load_json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _fallback_operations_memory(parsed_files: list[ParsedSetupFile]) -> dict[str, str]:
    departments: list[str] = []
    roles: list[str] = []
    for file in parsed_files:
        for row in file.rows[:50]:
            departments.extend(
                value for key, value in row.items() if "부서" in key or "department" in key.lower()
            )
            roles.extend(
                value for key, value in row.items() if "직함" in key or "title" in key.lower()
            )
    return {
        "company_name": "",
        "organization": "\n".join(file.filename for file in parsed_files),
        "departments": ", ".join(sorted({item for item in departments if item})),
        "roles": ", ".join(sorted({item for item in roles if item})),
        "key_workflows": "초기 업로드 파일을 기반으로 업무 흐름을 정리하세요.",
        "sensitive_policy": "민감한 파일은 로컬 에이전트 서버에서 처리하는 것을 권장합니다.",
    }


def _fallback_users(parsed_files: list[ParsedSetupFile]) -> list[dict[str, object]]:
    users: list[dict[str, object]] = []
    for file in parsed_files:
        for row in file.rows[:100]:
            name = _first_value(row, ("이름", "성명", "name", "employee"))
            title = _first_value(row, ("직함", "직급", "title", "role"))
            if not name:
                continue
            user_id = _safe_user_id(_first_value(row, ("id", "email", "이메일")) or name)
            users.append(
                {
                    "id": user_id,
                    "display_name": name,
                    "title": title,
                    "role_id": _role_for_title(title),
                    "active": True,
                },
            )
    return users


def _first_value(row: dict[str, str], keys: tuple[str, ...]) -> str:
    for key, value in row.items():
        low = key.lower()
        if any(target.lower() in low for target in keys):
            return value.strip()
    return ""


def _safe_user_id(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    return cleaned.strip("_")[:64] or "user"


def _role_for_title(title: str) -> str:
    if any(token in title for token in ("대표", "관리자", "CEO", "ceo")):
        return "owner"
    if any(token in title for token in ("팀장", "매니저", "manager", "Manager")):
        return "manager"
    return "staff"


def _recent_chat_turns(container: Container, user_id: str, *, limit: int) -> list[LlmMessage]:
    """Return the most recent persisted chat turns (chronological) for ``user_id``."""

    if limit <= 0:
        return []
    records = container.conversations.list_recent(user_id=user_id, limit=limit)
    turns: list[LlmMessage] = []
    for record in reversed(records):  # list_recent is newest-first; replay oldest-first
        role = str(record.get("role") or "")
        content = str(record.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        turns.append(LlmMessage(role, content))
    return turns


def _build_chat_messages(
    container: Container,
    user_message: str,
    *,
    user_id: str = "default",
    history_limit: int = 8,
    media_parts: list[dict[str, Any]] | None = None,
) -> tuple[list[LlmMessage], int]:
    """Build chat messages with persistent memory, recent history, and media.

    Returns ``(messages, used_history_turns)``.
    """

    memory = container.operations_memory.read().to_markdown()
    work_memory = container.work_memory.read().to_markdown()
    volatile_user = container.volatile_memory.read(scope="user", key=user_id).to_markdown()
    volatile_global = container.volatile_memory.read(scope="global", key="default").to_markdown()
    compressed = container.compressed_context.read(scope="user", key=user_id).to_markdown()
    permanent = container.permanent_memory.search(user_message, limit=5)
    permanent_md = "\n".join(
        f"- [{source.get('kind')}] {source.get('path')}: {source.get('title')}"
        for source in permanent
    )
    status_md = container.archive.status.read()
    recent = _recent_logs(container.settings.archive_dir, limit=5)
    recent_md = "\n".join(
        f"- {entry.get('created', '')} {entry.get('repo', '')} #{entry.get('external_id', '')} "
        f"status={entry.get('status', '')}"
        for entry in recent
    )
    system = render_prompt("office/chat_system.md.j2").strip()
    context = render_prompt(
        "office/chat_context.md.j2",
        memory=memory,
        work_memory=work_memory,
        permanent_md=permanent_md,
        compressed=compressed,
        volatile_user=volatile_user,
        volatile_global=volatile_global,
        status_md=status_md,
        recent_md=recent_md,
    ).strip()
    history = _recent_chat_turns(container, user_id, limit=history_limit)
    if media_parts:
        user_content: str | list[dict[str, Any]] = [text_part(user_message.strip()), *media_parts]
    else:
        user_content = user_message.strip()
    messages: list[LlmMessage] = [
        LlmMessage("system", system),
        LlmMessage("system", context),
        *history,
        LlmMessage("user", user_content),
    ]
    return messages, len(history)


_SLASH_KV_RE = re.compile(r"(\w+)=(\"[^\"]*\"|'[^']*'|\S+)")


def _is_slash_command(message: str) -> bool:
    return message.lstrip().startswith("/")


def _chat_slash_help(container: Container) -> str:
    """Markdown help listing slash-invokable skills."""

    skills = get_skills()
    lines = ["사용 가능한 슬래시 스킬:", ""]
    if not skills:
        lines.append("- (등록된 스킬이 없습니다)")
    for skill in skills.values():
        input_names = ", ".join(item.name for item in skill.inputs) or "(없음)"
        lines.append(f"- `/{skill.id}` — {skill.description} · 입력: {input_names}")
    lines.append("")
    lines.append("예: `/office.document_draft title=주간보고 회의 내용을 정리해줘`")
    return "\n".join(lines)


def _parse_chat_slash(message: str) -> tuple[str, dict[str, Any]]:
    """Parse ``/skill_id key=value ... free text`` into ``(skill_id, inputs)``.

    Free (non key=value) text is exposed under several common input names so that
    both prompt and tool skills receive it regardless of their schema.
    """

    body = message.lstrip()[1:].strip()
    if not body:
        return "", {}
    head, _, rest = body.partition(" ")
    skill_id = head.strip()
    rest = rest.strip()
    inputs: dict[str, Any] = {}
    consumed_spans: list[tuple[int, int]] = []
    for match in _SLASH_KV_RE.finditer(rest):
        key = match.group(1)
        raw = match.group(2).strip("\"'")
        inputs[key] = raw
        consumed_spans.append(match.span())
    free_text = rest
    for start, end in reversed(consumed_spans):
        free_text = free_text[:start] + free_text[end:]
    free_text = free_text.strip()
    if free_text:
        for default_key in ("text", "title", "source_text", "query", "message"):
            inputs.setdefault(default_key, free_text)
    return skill_id, inputs


def _format_skill_answer(skill_id: str, result: Any) -> str:
    parts = [f"`/{skill_id}` 실행 완료 ({result.status})."]
    if str(result.output_text or "").strip():
        parts.append(str(result.output_text).strip())
    if result.output_path:
        parts.append(f"저장 위치: {result.output_path}")
    if result.tool_result:
        parts.append(
            "```json\n" + json.dumps(result.tool_result, ensure_ascii=False, indent=2) + "\n```"
        )
    for note in result.notes:
        parts.append(f"- {note}")
    return "\n\n".join(parts)


async def _chat_run_slash(
    container: Container,
    payload: ChatRequest,
    actor: str,
    *,
    route: Literal["local", "api"],
    provider: LlmProviderName,
) -> ChatResponse:
    message = payload.message.strip()
    skill_id, inputs = _parse_chat_slash(message)
    if skill_id in {"", "skills", "help", "?"}:
        answer = _chat_slash_help(container)
        container.conversations.append_pair(
            user_id=actor,
            user_message=message,
            assistant_message=answer,
            provider=provider,
            model="slash",
            route=route,
            source_refs=[],
        )
        return ChatResponse(
            answer=answer,
            route=route,
            provider=provider,
            model="slash",
            prompt_tokens=0,
            completion_tokens=0,
        )
    skill = get_skill(skill_id)
    if skill is None:
        answer = f"`/{skill_id}` 스킬을 찾을 수 없습니다. `/skills`로 목록을 확인하세요."
        container.conversations.append_pair(
            user_id=actor,
            user_message=message,
            assistant_message=answer,
            provider=provider,
            model="slash",
            route=route,
            source_refs=[],
        )
        return ChatResponse(
            answer=answer,
            route=route,
            provider=provider,
            model="slash",
            prompt_tokens=0,
            completion_tokens=0,
        )
    if not container.access_control.has_permission(actor, skill.required_permission or "work:read"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"permission required: {skill.required_permission or 'work:read'}",
        )

    async def _completion(prompt: str, image_parts: list[dict[str, Any]] | None) -> str:
        return await _complete_office_task(
            container, prompt, task=skill.task, image_parts=image_parts
        )

    job = _start_ai_job(container, task=f"skill:{skill_id}", actor=actor, input_summary=message)
    try:
        result = await run_skill(container, skill_id, inputs, actor=actor, completion=_completion)
        job = _finish_ai_job(container, job, status="succeeded")
    except SkillError as exc:
        _finish_ai_job(container, job, status="failed", error=str(exc))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        _finish_ai_job(container, job, status="failed", error=str(exc))
        raise
    answer = _format_skill_answer(skill_id, result)
    container.conversations.append_pair(
        user_id=actor,
        user_message=message,
        assistant_message=answer,
        provider=provider,
        model=f"skill:{skill_id}",
        route=route,
        source_refs=[],
    )
    return ChatResponse(
        answer=answer,
        route=route,
        provider=provider,
        model=f"skill:{skill_id}",
        prompt_tokens=0,
        completion_tokens=0,
        ai_job=_ai_job_payload(job).model_dump(),
        skill_id=skill_id,
        skill_result=result.to_dict(),
    )


async def _chat_complete(container: Container, payload: ChatRequest, actor: str) -> ChatResponse:
    """Shared chat pipeline used by both the JSON and streaming endpoints."""

    runtime = container.llm_runtime.read()
    task_route = runtime.route_for(payload.task or "chat")
    route = payload.route or task_route.route
    provider = payload.provider or task_route.provider
    if route == "local" and not runtime.local_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="local LLM route is disabled")
    if route == "local":
        _sync_local_llm_state(container, enabled=True)
    if route == "api" and not runtime.api_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="API LLM route is disabled")
    llm_route: LlmRoute = "local" if route == "local" else "cloud"
    if _is_slash_command(payload.message):
        return await _chat_run_slash(container, payload, actor, route=route, provider=provider)
    model = _resolve_task_model(container, payload.task or "chat", provider, llm_route)
    vision = model_supports_vision(provider, model)
    audio = model_supports_audio(provider, model)
    attachment_context, media_parts, attachment_notes = _resolve_document_attachments(
        container, payload.attachment_ids, vision_enabled=vision, audio_enabled=audio
    )
    user_message = payload.message
    if attachment_context:
        user_message = f"{payload.message}\n\n[첨부 자료]\n{attachment_context}"
    messages, used_history = _build_chat_messages(
        container,
        user_message,
        user_id=actor,
        history_limit=payload.history_limit,
        media_parts=media_parts,
    )
    job = _start_ai_job(
        container, task=payload.task or "chat", actor=actor, input_summary=payload.message
    )
    try:
        response = await _complete_with_provider(
            container,
            messages,
            provider=provider,
            route=llm_route,
            temperature=0.2,
            max_tokens=1024,
            task=payload.task or "chat",
            actor=actor,
            model=model,
        )
        job = _finish_ai_job(container, job, status="succeeded")
    except Exception as exc:
        _finish_ai_job(container, job, status="failed", error=str(exc))
        raise
    container.metrics.record(
        agent="chat",
        route=response.route,
        tokens_in=response.prompt_tokens,
        tokens_out=response.completion_tokens,
        latency_ms=0,
    )
    container.conversations.append_pair(
        user_id=actor,
        user_message=payload.message,
        assistant_message=response.text,
        provider=provider,
        model=response.model,
        route=route,
        source_refs=[],
    )
    _update_user_volatile_memory_after_chat(
        container, actor=actor, user_message=payload.message, answer=response.text
    )
    return ChatResponse(
        answer=response.text,
        route=route,
        provider=provider,
        model=response.model,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        ai_job=_ai_job_payload(job).model_dump(),
        attachment_notes=attachment_notes,
        used_history=used_history,
    )


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chunk_text(text: str, size: int = 24) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _require(container: Container, credential: str | None, permission: str) -> str:
    user_id = _resolve_authenticated_user(container, credential)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="login required")
    if not container.access_control.has_permission(user_id, permission):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"permission required: {permission}",
        )
    return user_id


def _ensure_acl_keeps_admin_access(
    acl: dict[str, Any],
    *,
    users_override: list[dict[str, object]] | None = None,
    roles_override: list[dict[str, object]] | None = None,
    delete_user_id: str = "",
    delete_role_id: str = "",
) -> None:
    users = [dict(user) for user in acl.get("users", []) if isinstance(user, dict)]
    roles = [dict(role) for role in acl.get("roles", []) if isinstance(role, dict)]
    if users_override:
        for override in users_override:
            user_id = str(override.get("id") or "")
            users = [user for user in users if str(user.get("id") or "") != user_id]
            users.append(dict(override))
    if roles_override:
        for override in roles_override:
            role_id = str(override.get("id") or "")
            roles = [role for role in roles if str(role.get("id") or "") != role_id]
            roles.append(dict(override))
    if delete_user_id:
        users = [user for user in users if str(user.get("id") or "") != delete_user_id]
    if delete_role_id:
        roles = [role for role in roles if str(role.get("id") or "") != delete_role_id]
    admin_role_ids = {
        str(role.get("id") or "")
        for role in roles
        if "*" in [str(permission) for permission in role.get("permissions", [])]
        or "admin:users" in [str(permission) for permission in role.get("permissions", [])]
    }
    has_admin = any(
        bool(user.get("active", True)) and str(user.get("role_id") or "") in admin_role_ids
        for user in users
    )
    if not has_admin:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="At least one active administrator with admin:users permission is required.",
        )


def _ensure_role_exists(acl: dict[str, Any], role_id: str) -> None:
    if not role_id:
        return
    role_ids = {
        str(role.get("id") or "") for role in acl.get("roles", []) if isinstance(role, dict)
    }
    if role_id not in role_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"unknown role: {role_id}")


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


def _user_display_name(container: Container, user_id: str) -> str:
    acl = container.access_control.read()
    user = next((entry for entry in acl["users"] if entry["id"] == user_id), None)
    if user is None:
        return user_id
    return str(user.get("display_name") or user_id)


_DEPARTMENT_BRANCH_RANK = 40
_COMPANY_WIDE_RANK = 80


def _position_rank(container: Container, user_id: str | None) -> int:
    if not user_id:
        return 0
    acl = container.access_control.read()
    user = next((entry for entry in acl["users"] if entry["id"] == user_id), None)
    if user is None:
        return 0
    position = next(
        (entry for entry in acl["positions"] if entry.get("id") == user.get("position_id")),
        None,
    )
    if not position:
        return 0
    raw_rank = position.get("display_order") or position.get("level")
    return _as_int(raw_rank)


def _descendant_department_ids(departments: list[dict[str, object]], roots: set[str]) -> set[str]:
    children: dict[str, list[str]] = {}
    for dept in departments:
        parent = str(dept.get("parent_id") or "")
        if parent:
            children.setdefault(parent, []).append(str(dept.get("id") or ""))
    result: set[str] = set()
    queue = list(roots)
    while queue:
        current = queue.pop()
        if not current or current in result:
            continue
        result.add(current)
        queue.extend(children.get(current, []))
    return result


def _assignment_scope(container: Container, user_id: str | None) -> dict[str, Any]:
    acl = container.access_control.read()
    departments = acl["departments"]
    users = acl["users"]
    rank = _position_rank(container, user_id)
    actor = next((entry for entry in users if entry["id"] == user_id), None)
    actor_dept = str(actor.get("department") or "") if actor else ""
    if rank >= _COMPANY_WIDE_RANK:
        scope = "all"
        dept_ids = [str(dept.get("id")) for dept in departments]
        assignable = [user for user in users if user.get("active", True)]
        scoped_departments = list(departments)
    elif rank >= _DEPARTMENT_BRANCH_RANK and actor_dept:
        scope = "department"
        allowed = _descendant_department_ids(departments, {actor_dept})
        dept_ids = sorted(allowed)
        assignable = [
            user
            for user in users
            if user.get("active", True) and str(user.get("department") or "") in allowed
        ]
        scoped_departments = [dept for dept in departments if str(dept.get("id")) in allowed]
    else:
        scope = "none"
        dept_ids = []
        assignable = []
        scoped_departments = []
    return {
        "can_assign": scope != "none",
        "scope": scope,
        "level": rank,
        "position_rank": rank,
        "department_ids": dept_ids,
        "departments": scoped_departments,
        "assignable_users": assignable,
    }


def _resolve_user_ref(container: Container, ref: str) -> tuple[str, str]:
    """Resolve a user id-or-display-name into a (user_id, display_name) pair."""

    ref = (ref or "").strip()
    if not ref:
        return "", ""
    acl = container.access_control.read()
    match = next(
        (
            user
            for user in acl["users"]
            if str(user.get("id") or "").lower() == ref.lower()
            or str(user.get("display_name") or "").lower() == ref.lower()
        ),
        None,
    )
    if match is not None:
        return str(match.get("id")), str(match.get("display_name") or match.get("id"))
    return "", ref


def _collect_owner_activity(container: Container, owner: str, *, limit: int = 30) -> str:
    """Gather what a departing owner did so the handover LLM can build tasks."""

    owner_id, owner_name = _resolve_user_ref(container, owner)
    if not owner_name:
        return ""
    keys = {key.lower() for key in {owner_id, owner_name} if key}
    lines: list[str] = []

    items = [
        entry
        for entry in container.work_schedule.list()
        if str(entry.get("owner_id") or "").lower() in keys
        or str(entry.get("owner_name") or "").lower() in keys
    ]
    if items:
        lines.append("### 담당 작업/스케줄")
        for entry in items[:limit]:
            suffix = f" (마감 {entry.get('due_date')})" if entry.get("due_date") else ""
            note = f" — 메모: {entry.get('notes')}" if entry.get("notes") else ""
            lines.append(f"- [{entry.get('status')}] {entry.get('title')}{suffix}{note}")

    try:
        jobs = [
            _ai_job_payload(record).model_dump() for record in container.ai_jobs.recent(limit=200)
        ]
    except Exception:
        jobs = []
    owner_jobs = [job for job in jobs if str(job.get("actor") or "").lower() in keys]
    if owner_jobs:
        lines.append("\n### 최근 AI 작업 실행")
        for job in owner_jobs[:limit]:
            lines.append(
                f"- [{job.get('status')}] {job.get('task')}: {job.get('input_summary')} "
                f"({job.get('created_at')})"
            )

    try:
        audits = container.audit_log.list_recent(limit=500)
    except Exception:
        audits = []
    owner_audits = [entry for entry in audits if str(entry.get("actor") or "").lower() in keys]
    if owner_audits:
        lines.append("\n### 최근 활동 로그")
        for entry in owner_audits[:limit]:
            lines.append(
                f"- {entry.get('created_at')} · {entry.get('action')} "
                f"→ {entry.get('target')}/{entry.get('target_id')}"
            )

    if not lines:
        return ""
    return f"기존 담당자({owner_name}) 활동 요약:\n" + "\n".join(lines)


def _hr_evaluation_context(
    container: Container, *, user_id: str, work_item_ids: list[str] | None = None
) -> dict[str, object]:
    acl = container.access_control.read()
    user = next((entry for entry in acl["users"] if entry.get("id") == user_id), None)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="employee not found")
    departments = {str(entry.get("id")): entry for entry in acl["departments"]}
    positions = {str(entry.get("id")): entry for entry in acl["positions"]}
    position = positions.get(str(user.get("position_id") or ""))
    selected_ids = set(work_item_ids or [])
    related_work = [
        item
        for item in container.work_schedule.list()
        if (selected_ids and str(item.get("id") or "") in selected_ids)
        or str(item.get("owner_name") or "")
        in {str(user.get("id") or ""), str(user.get("display_name") or "")}
        or str(item.get("owner_id") or "") == user_id
        or str(item.get("assignee_id") or "") == user_id
    ][:30]
    conversations = [
        entry
        for entry in container.conversations.list_recent(user_id=user_id, limit=20)
        if isinstance(entry.get("content"), str)
    ]
    audit_logs = [
        entry
        for entry in container.audit_log.list_recent(limit=100)
        if str(entry.get("actor") or "") == user_id or str(entry.get("target_id") or "") == user_id
    ][:20]
    source_refs = [f"work_schedule:{item.get('id')}" for item in related_work if item.get("id")]
    return {
        "employee": user,
        "department": departments.get(str(user.get("department") or ""), {}),
        "position": position or {},
        "work_items": related_work,
        "conversation_logs": conversations,
        "audit_logs": audit_logs,
        "source_refs": source_refs,
    }


def _hr_evaluation_markdown(record: Any, *, context: dict[str, object]) -> str:
    employee_raw = context.get("employee")
    employee: dict[str, Any] = employee_raw if isinstance(employee_raw, dict) else {}
    department_raw = context.get("department")
    department: dict[str, Any] = department_raw if isinstance(department_raw, dict) else {}
    position_raw = context.get("position")
    position: dict[str, Any] = position_raw if isinstance(position_raw, dict) else {}
    work_items_raw = context.get("work_items")
    work_items: list[Any] = work_items_raw if isinstance(work_items_raw, list) else []
    employee_name = str(employee.get("display_name") or record.user_id)
    department_name = str(department.get("name") or employee.get("department") or "미배정")
    position_name = str(position.get("name") or employee.get("position_id") or "미지정")
    work_lines = [
        f"- [{item.get('status', '')}] {item.get('title', '')} ({item.get('id', '')})"
        for item in work_items
        if isinstance(item, dict)
    ]
    return "\n".join(
        [
            f"# 인사평가 기록 - {employee_name}",
            "",
            f"- 평가 ID: `{record.id}`",
            f"- 평가 대상: {employee_name} (`{record.user_id}`)",
            f"- 부서/직급: {department_name} / {position_name}",
            f"- 평가 기간: {record.period or '(미지정)'}",
            f"- 작성자: {record.created_by}",
            f"- 작성 시각: {record.created_at}",
            "",
            "## 최종 평가",
            record.final_text.strip() or "(내용 없음)",
            "",
            "## 관리자 근거/메모",
            record.evidence.strip() or "(없음)",
            "",
            "## 관련 업무",
            *(work_lines or ["- 관련 업무 없음"]),
            "",
            "## 원본 AI 초안",
            record.draft.strip() or "(초안 없음)",
            "",
            "## 출처",
            *[f"- {ref}" for ref in record.source_refs],
            "",
        ]
    )


def _ensure_owner_in_scope(container: Container, actor: str, owner_id: str) -> None:
    if not owner_id:
        return
    scope = _assignment_scope(container, actor)
    if scope["scope"] == "all":
        return
    assignable_ids = {str(user.get("id")) for user in scope["assignable_users"]}
    if owner_id not in assignable_ids:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="이 사원에게 업무를 배정할 권한이 없습니다. 담당 부서 범위를 벗어났습니다.",
        )


def _user_payload(container: Container, user_id: str) -> dict[str, object]:
    acl = container.access_control.read()
    user = next((entry for entry in acl["users"] if entry["id"] == user_id), None)
    if user is None:
        return {"id": user_id, "display_name": user_id, "role_id": "viewer", "permissions": []}
    role = next((entry for entry in acl["roles"] if entry["id"] == user["role_id"]), None)
    permissions = role["permissions"] if role else []
    return {**user, "permissions": permissions}


def _access_control_payload(container: Container) -> dict[str, Any]:
    return {**container.access_control.read(), "permissions": ALL_PERMISSIONS}


def _patch_artifact_relative_path(patch_id: str, artifact_path: str) -> str:
    cleaned = artifact_path.strip().lstrip("/")
    prefix = f"patch_ops/workspaces/{patch_id}/"
    if cleaned.startswith(prefix):
        return cleaned[len(prefix) :]
    return cleaned


def _readable_source_payload(
    source: dict[str, object],
    *,
    selected: bool,
    order: int,
) -> ReadableContextSourcePayload:
    return ReadableContextSourcePayload(
        id=str(source.get("id") or source.get("path") or ""),
        kind=str(source.get("kind") or "unknown"),
        path=str(source.get("path") or source.get("id") or ""),
        title=str(source.get("title") or source.get("path") or "Untitled source"),
        excerpt=str(source.get("excerpt") or "")[:1200],
        content=str(source.get("content") or ""),
        selected=selected,
        order=order,
        sensitivity=str(source.get("sensitivity") or "internal"),
        origin=str(source.get("origin") or "archive"),
        updated_at=str(source.get("updated_at") or ""),
    )


def _readable_context_bundle(
    container: Container,
    payload: ReadableContextPreviewRequest,
) -> ReadableContextBundlePayload:
    limit = max(1, min(payload.source_limit, 50))
    warnings: list[str] = []
    sources = container.permanent_memory.resolve_sources(
        query=payload.query,
        limit=limit,
        source_ids=payload.source_ids if payload.source_ids else None,
    )
    if not sources:
        sources = container.permanent_memory.search(payload.query, limit=limit)
    used_sources: list[ReadableContextSourcePayload] = []
    for order, source in enumerate(sources):
        source_id = str(source.get("id") or source.get("path") or "")
        try:
            detailed = container.permanent_memory.read_source(source_id, max_chars=8000)
        except Exception as exc:
            detailed = source
            warnings.append(f"{source_id}: {exc}")
        used_sources.append(_readable_source_payload(detailed, selected=True, order=order))
    volatile_payloads: list[VolatileMemoryPayload] = []
    if payload.include_volatile:
        for raw in container.volatile_memory.list():
            if isinstance(raw, dict):
                volatile_payloads.append(
                    VolatileMemoryPayload.from_memory(VolatileMemory.from_mapping(raw))
                )
    markdown = _render_readable_context_markdown(
        query=payload.query,
        sources=used_sources,
        volatile_memories=volatile_payloads,
        token_budget=payload.token_budget,
    )
    return ReadableContextBundlePayload(
        query=payload.query,
        used_sources=used_sources,
        volatile_memories=volatile_payloads,
        estimated_tokens=_estimate_tokens(markdown),
        warnings=warnings,
        markdown=markdown,
    )


def _render_readable_context_markdown(
    *,
    query: str,
    sources: list[ReadableContextSourcePayload],
    volatile_memories: list[VolatileMemoryPayload],
    token_budget: int,
) -> str:
    lines = [
        "# AI 가독 정보 번들",
        "",
        f"- Query: {query or '(없음)'}",
        f"- Token budget: {token_budget}",
        f"- Sources: {len(sources)}",
        f"- Volatile memories: {len(volatile_memories)}",
        "",
    ]
    for source in sources:
        content = source.content or source.excerpt
        lines.extend(
            [
                f"## Source {source.order + 1}: {source.title}",
                f"- kind: {source.kind}",
                f"- path: {source.path}",
                "",
                content[:8000],
                "",
            ]
        )
    if volatile_memories:
        lines.append("## Volatile memories")
        lines.append("")
        for memory in volatile_memories:
            lines.extend(
                [
                    f"### {memory.scope}:{memory.key}",
                    f"- 요약: {memory.summary or '(없음)'}",
                    f"- 현재 의도: {memory.current_intent or '(없음)'}",
                    f"- 원천 참조: {', '.join(memory.relevant_sources) or '(없음)'}",
                    "",
                ]
            )
    return "\n".join(lines).strip()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def _ai_job_payload(record: AiJobRecord) -> AiJobStatusPayload:
    return AiJobStatusPayload(**record.to_dict())


def _start_ai_job(
    container: Container,
    *,
    task: str,
    actor: str = "system",
    input_summary: str = "",
    used_sources: list[str] | None = None,
) -> AiJobRecord:
    job = container.ai_jobs.create(
        task=task,
        actor=actor,
        input_summary=input_summary,
        used_sources=used_sources,
    )
    running = job.with_status("running")
    return container.ai_jobs.update(running)


def _finish_ai_job(
    container: Container,
    job: AiJobRecord,
    *,
    status: Literal["succeeded", "failed"],
    result_path: str = "",
    error: str = "",
    used_sources: list[str] | None = None,
) -> AiJobRecord:
    return container.ai_jobs.update(
        job.with_status(
            status,
            result_path=result_path,
            error=error,
            used_sources=used_sources,
        )
    )


def _settings_api_key(container: Container, provider: str) -> str:
    if provider == "openai":
        return container.settings.llm.openai_api_key
    if provider == "anthropic":
        return container.settings.llm.anthropic_api_key
    if provider == "gemini":
        return container.settings.llm.gemini_api_key
    if provider == "together":
        return container.settings.llm.together_api_key
    if provider == "solar":
        return container.settings.llm.solar_api_key
    return ""


def _audit(
    container: Container,
    *,
    actor: str = "system",
    action: str,
    target: str,
    target_id: str = "",
    details: dict[str, object] | None = None,
) -> None:
    container.audit_log.record(
        actor=actor,
        action=action,
        target=target,
        target_id=target_id,
        details=details,
    )


def _memory_refresh_prompt(query: str, sources: list[dict[str, object]]) -> str:
    source_md = "\n\n".join(
        f"### {source.get('path')}\n{source.get('excerpt', '')}" for source in sources
    )
    return render_prompt("office/memory_refresh.md.j2", query=query, source_md=source_md).strip()


def _context_compression_prompt(
    query: str,
    token_budget: int,
    sources: list[dict[str, object]],
    *,
    volatile_appendix: str = "",
) -> str:
    source_md = "\n\n".join(
        f"### {source.get('path')}\n{source.get('excerpt', '')}" for source in sources
    )
    return render_prompt(
        "office/context_compression.md.j2",
        query=query,
        token_budget=token_budget,
        source_md=source_md,
        volatile_appendix=volatile_appendix,
    ).strip()


def _volatile_memories_markdown(container: Container) -> str:
    chunks: list[str] = []
    for raw in container.volatile_memory.list(scope=None):
        try:
            vm = VolatileMemory.from_mapping(raw)
            chunks.append(vm.to_markdown())
        except Exception:
            continue
    joined = "\n\n".join(chunks)
    return joined[:8000]


def _lines_from_markdown(markdown: str, *, prefix: str = "-") -> list[str]:
    lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            lines.append(stripped.lstrip(prefix).strip())
    return lines[:20]


def _agent_plan_steps(
    objective: str, schedule_refs: list[str], memory_refs: list[str]
) -> list[dict[str, object]]:
    return [
        {
            "id": "review-memory",
            "title": "영구 메모리와 압축 컨텍스트 검토",
            "requires_approval": False,
            "memory_refs": memory_refs,
        },
        {
            "id": "split-work",
            "title": f"작업 분할: {objective}",
            "requires_approval": True,
            "schedule_refs": schedule_refs,
        },
        {
            "id": "execute-approved",
            "title": "승인된 작업 실행",
            "requires_approval": True,
            "external_effects": ["files", "llm"],
        },
    ]


def _update_user_volatile_memory_after_chat(
    container: Container,
    *,
    actor: str,
    user_message: str,
    answer: str,
) -> None:
    existing = container.volatile_memory.read(scope="user", key=actor)
    summary = "\n".join(
        part
        for part in [
            existing.summary,
            f"최근 대화: 사용자={user_message[:240]} / 응답={answer[:240]}",
        ]
        if part
    )[-2000:]
    container.volatile_memory.write(
        VolatileMemory(
            scope="user",
            key=actor,
            summary=summary,
            current_intent=user_message[:500],
            active_context=existing.active_context,
            preferences=existing.preferences,
            open_questions=existing.open_questions,
            next_actions=existing.next_actions,
            relevant_sources=existing.relevant_sources,
        )
    )


def _masked_provider_payload(container: Container) -> list[dict[str, object]]:
    providers = container.secret_store.list_masked()
    metadata = {
        item["provider"]: item
        for item in provider_payload(vllm_base_url=container.settings.llm.vllm_base_url)
    }
    for provider in providers:
        provider_id = str(provider["provider"])
        provider["label"] = metadata.get(provider_id, {}).get("label", provider_id)
        provider["base_url"] = _default_base_url(container, provider_id)
        provider["base_url_source"] = "system"
    return providers


def _default_base_url(container: Container, provider: str) -> str:
    if provider == "together":
        return container.settings.llm.together_base_url.rstrip("/")
    if provider == "solar":
        return container.settings.llm.solar_base_url.rstrip("/")
    return default_base_url(provider, vllm_base_url=container.settings.llm.vllm_base_url)


def _sync_local_llm_state(container: Container, *, enabled: bool) -> None:
    provider = container.embedded_vllm()
    if provider is None:
        return
    runtime = container.llm_runtime.read()
    provider.configure_model(runtime.local_model or container.settings.llm.vllm_model)
    if enabled:
        if provider.status()["state"] not in {"loading", "running"}:
            task = asyncio.create_task(provider.preload(), name="vllm-local-preload")
            _PRELOAD_TASKS.add(task)
            task.add_done_callback(_PRELOAD_TASKS.discard)
    else:
        provider.unload()


def _local_llm_status(container: Container) -> LocalLlmStatusPayload:
    runtime = container.llm_runtime.read()
    model = runtime.local_model or container.settings.llm.vllm_model
    if not runtime.local_enabled:
        return LocalLlmStatusPayload(
            enabled=False,
            mode=container.settings.llm.vllm_mode,
            state="disabled",
            model=model,
            loaded=False,
            message="로컬 LLM이 OFF 상태입니다. Local ON을 누르면 모델 로딩을 시작합니다.",
        )
    provider = container.embedded_vllm()
    if provider is None:
        return LocalLlmStatusPayload(
            enabled=True,
            mode=container.settings.llm.vllm_mode,
            state="unavailable",
            model=model,
            loaded=False,
            message=(
                "현재 백엔드는 로컬 GPU 임베드 모드가 아닙니다. Docker 백엔드에서는 모델을 직접 "
                "올릴 수 없으니 호스트에서 NG_VLLM_MODE=embedded 로 실행하세요."
            ),
        )
    raw = provider.status()
    state = str(raw["state"])
    messages = {
        "offline": "로컬 LLM이 아직 올라오지 않았습니다. Local ON을 누르면 GPU에 모델을 올립니다.",
        "loading": "로컬 LLM을 GPU에 올리는 중입니다. 첫 로딩은 수십 초에서 수 분 걸릴 수 있습니다.",
        "running": "로컬 LLM이 GPU 상에서 가동 중입니다!",
        "error": "로컬 LLM 로딩에 실패했습니다. 서버 로그의 vLLM 오류를 확인하세요.",
    }
    return LocalLlmStatusPayload(
        enabled=True,
        mode=str(raw["mode"]),
        state=state,
        model=str(raw["model"]),
        loaded=bool(raw["loaded"]),
        message=messages.get(state, "로컬 LLM 상태를 확인 중입니다."),
        error=str(raw["error"]),
        started_at=str(raw["started_at"]),
        ready_at=str(raw["ready_at"]),
    )


async def _generate_hiring_document(
    container: Container,
    payload: HiringRequest,
    *,
    actor: str = "system",
    kind: str,
    instruction: str,
) -> GeneratedDocumentPayload:
    target_context = _hiring_target_context(container, payload)
    workload_context = (
        _hiring_workload_context(container, payload)
        if payload.include_workload
        else "업무량 컨텍스트 제외"
    )
    prompt = render_prompt(
        "office/hiring_document.md.j2",
        context=_office_context(container),
        role_title=payload.role_title,
        business_need=payload.business_need,
        priority=payload.priority,
        target_context=target_context,
        workload_context=workload_context,
        candidate_name=payload.candidate_name,
        candidate_profile=payload.candidate_profile,
        interview_stage=payload.interview_stage,
        instruction=instruction,
    ).strip()
    job = _start_ai_job(
        container,
        task=f"hiring.{kind}",
        actor=actor,
        input_summary=f"{payload.role_title}: {payload.business_need}",
    )
    try:
        markdown = await _complete_office_task(container, prompt, task="hiring")
        path = _write_generated_doc(
            container.settings.archive_dir,
            folder="hr/interview_kits",
            slug=f"{kind}_{payload.role_title}",
            markdown=markdown,
        )
        job = _finish_ai_job(container, job, status="succeeded", result_path=path)
    except Exception as exc:
        _finish_ai_job(container, job, status="failed", error=str(exc))
        raise
    return GeneratedDocumentPayload(
        title=payload.role_title,
        markdown=markdown,
        path=path,
        ai_job=_ai_job_payload(job).model_dump(),
    )


def _hiring_target_context(container: Container, payload: HiringRequest) -> str:
    acl = container.access_control.read()
    dept = next(
        (
            item
            for item in acl.get("departments", [])
            if str(item.get("id")) == payload.department_id
        ),
        None,
    )
    position = next(
        (item for item in acl.get("positions", []) if str(item.get("id")) == payload.position_id),
        None,
    )
    lines = [
        f"- 대상 부서: {dept.get('name') if dept else '(미지정)'}",
        f"- 대상 직급/등급: {position.get('name') if position else '(미지정)'}",
    ]
    if dept and dept.get("description"):
        lines.append(f"- 부서 업무 범위: {dept.get('description')}")
    if position and position.get("description"):
        lines.append(f"- 직급 설명: {position.get('description')}")
    if payload.candidate_name:
        lines.append(f"- 후보자/신입 이름: {payload.candidate_name}")
    if payload.interview_stage:
        lines.append(f"- 채용 단계: {payload.interview_stage}")
    if payload.candidate_profile:
        lines.append(f"- 후보자 신원/경력 메모: {payload.candidate_profile}")
    return "\n".join(lines)


def _hiring_workload_context(container: Container, payload: HiringRequest) -> str:
    acl = container.access_control.read()
    dept = next(
        (
            item
            for item in acl.get("departments", [])
            if str(item.get("id")) == payload.department_id
        ),
        None,
    )
    dept_name = str(dept.get("name") or "") if dept else ""
    dept_user_ids = {
        str(user.get("id"))
        for user in acl.get("users", [])
        if payload.department_id and str(user.get("department") or "") == payload.department_id
    }
    items = container.work_schedule.list()
    if payload.department_id:
        items = [
            item
            for item in items
            if str(item.get("owner_id") or "") in dept_user_ids
            or payload.department_id.lower()
            in f"{item.get('title') or ''} {item.get('notes') or ''}".lower()
            or (
                dept_name
                and dept_name.lower()
                in f"{item.get('title') or ''} {item.get('notes') or ''}".lower()
            )
        ]
    if not items:
        return "- 현재 연결된 업무 스케줄 항목이 없습니다. work_memory와 조직 메모리를 기준으로 판단하세요."
    priority_rank = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    ordered = sorted(
        items,
        key=lambda item: (
            priority_rank.get(str(item.get("priority") or "normal"), 2),
            str(item.get("due_date") or ""),
        ),
    )
    lines = ["현재 업무량/스케줄 신호:"]
    for item in ordered[:20]:
        lines.append(
            "- "
            f"{item.get('title')} · owner={item.get('owner_name') or item.get('owner_id') or '미지정'} "
            f"· status={item.get('status') or '-'} · priority={item.get('priority') or '-'} "
            f"· due={item.get('due_date') or '-'}"
        )
        if item.get("notes"):
            lines.append(f"  - notes: {str(item.get('notes'))[:220]}")
    return "\n".join(lines)


def _resolve_runtime_task(container: Container, task: str) -> tuple[LlmProviderName, LlmRoute]:
    runtime = container.llm_runtime.read()
    task_route = runtime.route_for(task)
    if task_route.route == "local" and not runtime.local_enabled:
        task_route = runtime.route_for("chat")
    if task_route.route == "api" and not runtime.api_enabled:
        task_route = runtime.route_for("chat")
    route: LlmRoute = "local" if task_route.route == "local" else "cloud"
    return task_route.provider, route


def _resolve_runtime_model(container: Container, provider: LlmProviderName, route: LlmRoute) -> str:
    """Default model for a provider/route when no per-task override is set."""

    runtime = container.llm_runtime.read()
    llm = container.settings.llm
    defaults: dict[str, str] = {
        "solar": llm.solar_model,
        "openai": llm.openai_model,
        "anthropic": llm.anthropic_model,
        "gemini": llm.gemini_model,
        "together": llm.together_model,
        "vllm": llm.vllm_model,
    }
    if route == "local" or provider == "vllm":
        return (runtime.local_model or llm.vllm_model or defaults.get("vllm", "")).strip()
    saved = container.secret_store.read(provider)
    if saved and saved.model:
        return saved.model.strip()
    return defaults.get(provider, "")


def _resolve_task_model(
    container: Container,
    task: str,
    provider: LlmProviderName,
    route: LlmRoute,
) -> str:
    """Effective model for a task: per-task override first, then provider defaults."""

    runtime = container.llm_runtime.read()
    routes = runtime.task_routes or {}
    task_route = routes.get(task)
    if task_route and str(task_route.model or "").strip():
        # Only honor the per-task model override when it matches the provider/route
        # actually used. Otherwise (e.g. the chat route is overridden to api/openai
        # in the UI while the task is configured for a local model) the local model
        # name would be sent to a cloud provider, producing "invalid model ID".
        same_provider = str(task_route.provider) == str(provider)
        task_is_local = str(task_route.route) == "local"
        if same_provider and task_is_local == (route == "local"):
            return str(task_route.model).strip()
    return _resolve_runtime_model(container, provider, route)


def _effective_provider_model(
    container: Container,
    provider: LlmProviderName,
    *,
    model: str,
    route: LlmRoute,
) -> str:
    """Resolve the model string passed to a provider adapter."""

    chosen = (model or "").strip()
    if chosen:
        return chosen
    return _resolve_runtime_model(container, provider, route)


def _sync_embedded_model(container: Container, model: str) -> None:
    """Ensure the in-process vLLM engine matches the requested model."""

    embedded = container.embedded_vllm()
    if embedded is None:
        return
    effective = (model or "").strip()
    if effective:
        embedded.configure_model(effective)


async def _complete_office_task(
    container: Container,
    prompt: str,
    *,
    task: str = "document_generation",
    image_parts: list[dict[str, Any]] | None = None,
) -> str:
    provider, route = _resolve_runtime_task(container, task)
    model = _resolve_task_model(container, task, provider, route)
    if image_parts:
        user_content: str | list[dict[str, Any]] = [text_part(prompt), *image_parts]
    else:
        user_content = prompt
    messages = [
        LlmMessage(
            "system",
            render_prompt("office/office_task_system.md.j2").strip(),
        ),
        LlmMessage("user", user_content),
    ]
    response = await _complete_with_provider(
        container,
        messages,
        provider=provider,
        route=route,
        temperature=0.2,
        max_tokens=1600,
        task=task,
        model=model,
    )
    text = response.text.strip()
    if text:
        return text
    try:
        retry = await _complete_with_provider(
            container,
            messages,
            provider=provider,
            route=route,
            temperature=0.2,
            max_tokens=6000,
            task=task,
            model=model,
        )
        retry_text = retry.text.strip()
        if retry_text:
            return retry_text
        diagnostic = (
            f"provider={provider}, route={route}, model={retry.model or response.model}, "
            f"prompt_tokens={response.prompt_tokens}+{retry.prompt_tokens}, "
            f"completion_tokens={response.completion_tokens}+{retry.completion_tokens}"
        )
    except HTTPException as exc:
        if exc.status_code != status.HTTP_429_TOO_MANY_REQUESTS:
            raise
        diagnostic = (
            f"provider={provider}, route={route}, model={response.model}, "
            f"first_completion_tokens={response.completion_tokens}, retry=rate_limited"
        )
    return _fallback_office_task_markdown(prompt, task=task, diagnostic=diagnostic)


async def _run_step_skill(
    container: Container, skill_id: str, *, item: Any, actor: str
) -> tuple[str, str]:
    """Run a skill bound to a work-schedule step; return ``(result_path, markdown)``."""

    async def _completion(prompt: str, image_parts: list[dict[str, Any]] | None) -> str:
        return await _complete_office_task(
            container, prompt, task="document_generation", image_parts=image_parts
        )

    inputs: dict[str, Any] = {
        "title": item.title,
        "source_text": item.notes,
        "audience": item.owner_name,
        "query": item.title,
    }
    run_result = await run_skill(container, skill_id, inputs, actor=actor, completion=_completion)
    markdown = run_result.output_text or json.dumps(
        run_result.tool_result, ensure_ascii=False, indent=2
    )
    result_path = run_result.output_path
    if not result_path:
        result_path = _write_generated_doc(
            container.settings.archive_dir,
            folder="work_architecture",
            slug=f"skill_{skill_id}_{item.title}",
            markdown=markdown,
        )
    return result_path, markdown


async def _complete_patchops_task(
    container: Container, prompt: str, *, task: str = "patch_planning"
) -> str:
    provider, route = _resolve_runtime_task(container, task)
    model = _resolve_task_model(container, task, provider, route)
    messages = [
        LlmMessage(
            "system",
            (
                "당신은 코딩 에이전트 계획서 작성 도우미입니다. Negotium 안에서 직접 코드를 적용하지 않고, "
                "Cursor나 Claude Code가 읽을 수 있는 plan.md를 명확하고 실행 가능하게 작성합니다. "
                "민감정보와 secret은 절대 노출하지 마세요."
            ),
        ),
        LlmMessage("user", prompt),
    ]
    response = await _complete_with_provider(
        container,
        messages,
        provider=provider,
        route=route,
        temperature=0.1,
        max_tokens=2200,
        task=task,
        model=model,
    )
    return response.text.strip()


def _collect_plan_source_files(
    container: Container, source_refs: list[str] | None
) -> list[dict[str, object]]:
    """Resolve archive-relative refs (memory sources or documents) into readable files.

    Each ref is the archive-relative path/id used across permanent memory and the
    document index. Unreadable refs are skipped so a bad selection never aborts the
    whole synthesis request.
    """

    sources: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in source_refs or []:
        ref = str(raw or "").strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        try:
            source = container.permanent_memory.read_source(ref, max_chars=8000)
        except (FileNotFoundError, ValueError):
            continue
        sources.append(source)
    return sources


def _render_plan_sources_md(sources: list[dict[str, object]]) -> str:
    blocks: list[str] = []
    for index, source in enumerate(sources, start=1):
        title = str(source.get("title") or source.get("path") or f"파일 {index}")
        path = str(source.get("path") or source.get("id") or "")
        content = str(source.get("content") or "").strip()
        header = f"### 파일 {index}: {title}"
        if path:
            header += f" ({path})"
        blocks.append(f"{header}\n```\n{content}\n```")
    return "\n\n".join(blocks)


async def _revise_patch_plan_markdown(
    container: Container,
    *,
    run: PatchRun,
    current: str,
    instruction: str,
    sources: list[dict[str, object]] | None = None,
) -> str:
    sources = sources or []
    if sources:
        prompt = "\n".join(
            [
                "아래 참고 파일들과 사용자의 지시를 종합해, 코딩 에이전트(Cursor·Claude Code 등)에게",
                "그대로 넘길 수 있는 plan.md 한 개를 작성하세요. 비개발자가 작성한 지시를 개발자가",
                "바로 따라할 수 있도록 목표·범위·관련 파일·단계별 체크리스트·검증 방법을 포함하세요.",
                "출력은 반드시 plan.md 본문(Markdown)만 반환하세요. 설명, 코드펜스, JSON은 추가하지 마세요.",
                "",
                f"작업 요청: {run.request}",
                f"저장소: {run.repo_id}",
                "",
                "## 사용자 지시",
                instruction.strip() or "(별도 지시 없음 — 참고 파일을 바탕으로 합리적으로 작성)",
                "",
                "## 참고 파일",
                _render_plan_sources_md(sources),
                "",
                "## 현재 plan.md (있다면 이어서 보완)",
                current.strip() or "(아직 plan.md가 없습니다. 새로 작성하세요.)",
            ]
        )
    else:
        prompt = "\n".join(
            [
                "아래 현재 plan.md를 사용자의 요청에 맞게 다시 작성하세요.",
                "출력은 반드시 수정된 plan.md 본문만 반환하세요. 설명, 코드펜스, JSON은 추가하지 마세요.",
                "",
                f"작업 요청: {run.request}",
                f"저장소: {run.repo_id}",
                "",
                "## 사용자 수정 요청",
                instruction.strip(),
                "",
                "## 현재 plan.md",
                current.strip() or "(아직 plan.md가 없습니다. 새로 작성하세요.)",
            ]
        )
    revised = await _complete_patchops_task(container, prompt, task="patch_planning")
    return (
        revised.strip() or current.strip() or f"# 코딩 에이전트 계획서\n\n## 요청\n{run.request}\n"
    )


async def _complete_with_provider(
    container: Container,
    messages: list[LlmMessage],
    *,
    provider: LlmProviderName,
    route: LlmRoute,
    temperature: float,
    max_tokens: int,
    task: str = "chat",
    actor: str = "",
    model: str = "",
) -> LlmResponse:
    effective_model = _effective_provider_model(container, provider, model=model, route=route)
    if route == "local" and provider == "vllm":
        _sync_embedded_model(container, effective_model)
    destination = _firewall_destination(provider=provider, route=route)
    policy = load_context_firewall_policy(container.settings.workspace_dir)
    messages, firewall_result = sanitize_llm_messages(
        messages,
        destination=destination,
        task_type=str(provider),
        policy=policy,
    )
    firewall_result = record_firewall_audit(
        container,
        firewall_result,
        destination=destination,
        task_type=str(provider),
    )
    if destination in {"frontier_llm", "cloud_llm", "api_llm", "openai", "anthropic", "gemini"}:
        if firewall_result.decision == "block":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Context Firewall blocked outbound frontier LLM context.",
            )
        if firewall_result.decision == "local_only":
            route = "local"
    try:
        container.token_usage.check_limits(attempted_tokens=max(0, int(max_tokens or 0)))
    except TokenLimitExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    try:
        response: LlmResponse
        sanitized: LlmResponse
        if container.settings.llm.gateway_url:
            response = await _complete_via_gateway(
                container,
                messages,
                provider=provider,
                route=route,
                temperature=temperature,
                max_tokens=max_tokens,
                model=effective_model,
            )
            sanitized = sanitize_llm_response(
                response, destination=destination, task_type=str(provider)
            )
            _record_token_usage(
                container,
                provider=provider,
                model=sanitized.model,
                task=task,
                actor=actor,
                response=sanitized,
            )
            return sanitized
        saved = container.secret_store.read(provider)
        if saved and saved.api_key and provider == "openai" and route != "local":
            response = await OpenAiProvider(
                api_key=saved.api_key,
                model=effective_model or saved.model or container.settings.llm.openai_model,
                base_url=default_base_url("openai"),
            ).complete(messages, route=route, temperature=temperature, max_tokens=max_tokens)
            sanitized = sanitize_llm_response(
                response, destination=destination, task_type=str(provider)
            )
            _record_token_usage(
                container,
                provider=provider,
                model=sanitized.model,
                task=task,
                actor=actor,
                response=sanitized,
            )
            return sanitized
        if saved and saved.api_key and provider == "anthropic" and route != "local":
            response = await AnthropicProvider(
                api_key=saved.api_key,
                model=effective_model or saved.model or container.settings.llm.anthropic_model,
                base_url=default_base_url("anthropic"),
            ).complete(messages, route=route, temperature=temperature, max_tokens=max_tokens)
            sanitized = sanitize_llm_response(
                response, destination=destination, task_type=str(provider)
            )
            _record_token_usage(
                container,
                provider=provider,
                model=sanitized.model,
                task=task,
                actor=actor,
                response=sanitized,
            )
            return sanitized
        if saved and saved.api_key and provider == "gemini" and route != "local":
            response = await GeminiProvider(
                api_key=saved.api_key,
                model=effective_model or saved.model or container.settings.llm.gemini_model,
                base_url=default_base_url("gemini"),
            ).complete(messages, route=route, temperature=temperature, max_tokens=max_tokens)
            sanitized = sanitize_llm_response(
                response, destination=destination, task_type=str(provider)
            )
            _record_token_usage(
                container,
                provider=provider,
                model=sanitized.model,
                task=task,
                actor=actor,
                response=sanitized,
            )
            return sanitized
        if saved and saved.api_key and provider == "solar" and route != "local":
            response = await OpenAiProvider(
                api_key=saved.api_key,
                model=effective_model or saved.model or container.settings.llm.solar_model,
                base_url=saved.base_url or container.settings.llm.solar_base_url,
            ).complete(messages, route=route, temperature=temperature, max_tokens=max_tokens)
            sanitized = sanitize_llm_response(
                response, destination=destination, task_type=str(provider)
            )
            _record_token_usage(
                container,
                provider=provider,
                model=sanitized.model,
                task=task,
                actor=actor,
                response=sanitized,
            )
            return sanitized
        if saved and saved.api_key and provider == "together" and route != "local":
            response = await OpenAiProvider(
                api_key=saved.api_key,
                model=effective_model or saved.model or container.settings.llm.together_model,
                base_url=saved.base_url or container.settings.llm.together_base_url,
            ).complete(messages, route=route, temperature=temperature, max_tokens=max_tokens)
            sanitized = sanitize_llm_response(
                response, destination=destination, task_type=str(provider)
            )
            _record_token_usage(
                container,
                provider=provider,
                model=sanitized.model,
                task=task,
                actor=actor,
                response=sanitized,
            )
            return sanitized
        if saved and provider == "vllm" and container.settings.llm.vllm_mode != "embedded":
            response = await VllmProvider(
                base_url=saved.base_url or container.settings.llm.vllm_base_url,
                model=effective_model or saved.model or container.settings.llm.vllm_model,
                api_key=saved.api_key or "EMPTY",
            ).complete(messages, route=route, temperature=temperature, max_tokens=max_tokens)
            sanitized = sanitize_llm_response(
                response, destination="local_llm", task_type=str(provider)
            )
            _record_token_usage(
                container,
                provider=provider,
                model=sanitized.model,
                task=task,
                actor=actor,
                response=sanitized,
            )
            return sanitized
        if isinstance(container.llm, LlmGateway):
            response = await container.llm.complete_with_provider(
                messages,
                provider_name=provider,
                route=route,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            sanitized = sanitize_llm_response(
                response, destination=destination, task_type=str(provider)
            )
            _record_token_usage(
                container,
                provider=provider,
                model=sanitized.model,
                task=task,
                actor=actor,
                response=sanitized,
            )
            return sanitized
        response = await container.llm.complete(
            messages,
            route=route,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        sanitized = sanitize_llm_response(
            response, destination=destination, task_type=str(provider)
        )
        _record_token_usage(
            container,
            provider=provider,
            model=sanitized.model,
            task=task,
            actor=actor,
            response=sanitized,
        )
        return sanitized
    except VllmConnectionError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except VllmEmbeddedError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise _llm_provider_http_error(provider, exc) from exc


def _record_token_usage(
    container: Container,
    *,
    provider: LlmProviderName,
    model: str,
    task: str,
    actor: str,
    response: LlmResponse,
) -> None:
    try:
        container.token_usage.record(
            provider=str(provider),
            model=model,
            task=task,
            actor=actor,
            prompt_tokens=int(getattr(response, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(response, "completion_tokens", 0) or 0),
        )
    except Exception:
        return


def _llm_provider_http_error(provider: LlmProviderName, exc: Exception) -> HTTPException:
    """Convert a third-party LLM client error into a user-friendly HTTPException."""

    status_code = getattr(exc, "status_code", None)
    detail = str(exc) or exc.__class__.__name__
    if isinstance(status_code, int):
        if status_code in {400, 401, 403, 404, 422}:
            hint = ""
            low = detail.lower()
            if "model" in low and (
                "invalid" in low or "not found" in low or "does not exist" in low
            ):
                hint = (
                    " — 설정된 모델 ID가 올바르지 않습니다. 'API 키·로컬 에이전트' 관리에서"
                    " 해당 제공자의 모델을 유효한 값으로 변경하세요."
                )
            elif status_code in {401, 403}:
                hint = " — API 키를 확인하세요."
            return HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"{provider} 요청이 거절되었습니다: {detail}{hint}",
            )
        if status_code in {408, 429, 500, 502, 503, 504}:
            return HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"{provider} 서비스 응답 실패: {detail}",
            )
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY,
        detail=f"{provider} 호출 중 오류: {detail}",
    )


def _firewall_destination(*, provider: LlmProviderName, route: LlmRoute) -> str:
    if route == "local" or provider in {"vllm", "fake"}:
        return "local_llm"
    if provider in {"solar", "openai", "anthropic", "gemini", "together"}:
        return "frontier_llm"
    return "cloud_llm"


def _fallback_office_task_markdown(prompt: str, *, task: str, diagnostic: str = "") -> str:
    title = (
        _extract_prompt_field(prompt, ("제목", "목표", "Objective", "Title")) or "자동 생성 초안"
    )
    source = (
        _extract_prompt_field(prompt, ("원문/메모", "원문", "메모", "Source", "source_text"))
        or prompt[:600]
    )
    return "\n".join(
        [
            f"# {title}",
            "",
            "> 외부 LLM이 빈 응답을 반환해 로컬 fallback 초안을 생성했습니다.",
            f"> task: `{task}`",
            *([f"> diagnostic: `{diagnostic}`"] if diagnostic else []),
            "",
            "## 핵심 요약",
            f"- 입력 주제: {title}",
            f"- 참고 내용: {source[:240]}",
            "",
            "## 초안",
            "- 배경과 목적을 확인합니다.",
            "- 현재 입력된 원문/메모를 기준으로 주요 논점을 정리합니다.",
            "- 담당자와 다음 액션을 분리해 후속 작업으로 넘깁니다.",
            "",
            "## 다음 액션",
            "- 담당자는 초안을 검토하고 누락된 결정사항을 보완합니다.",
            "- 필요한 경우 LLM 설정의 출력 토큰 예산 또는 모델을 조정한 뒤 다시 생성합니다.",
        ]
    )


def _extract_prompt_field(prompt: str, labels: tuple[str, ...]) -> str:
    lines = prompt.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        for label in labels:
            if stripped.startswith(f"{label}:"):
                inline = stripped.split(":", 1)[-1].strip()
                if inline:
                    return inline[:120]
                if index + 1 < len(lines):
                    return lines[index + 1].strip()[:120]
            if stripped.rstrip(":") == label and index + 1 < len(lines):
                return lines[index + 1].strip()[:120]
    return ""


async def _complete_via_gateway(
    container: Container,
    messages: list[LlmMessage],
    *,
    provider: LlmProviderName,
    route: LlmRoute,
    temperature: float,
    max_tokens: int,
    model: str = "",
) -> LlmResponse:
    payload: dict[str, Any] = {
        "provider": provider,
        "route": route,
        "messages": [
            {"role": message.role, "content": flatten_message_text(message.content)}
            for message in messages
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if model.strip():
        payload["model"] = model.strip()
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{container.settings.llm.gateway_url.rstrip('/')}/v1/chat/completions",
            json=payload,
        )
        response.raise_for_status()
    data = response.json()
    return LlmResponse(
        text=str(data.get("text") or ""),
        prompt_tokens=int(data.get("prompt_tokens") or 0),
        completion_tokens=int(data.get("completion_tokens") or 0),
        route=route,
        model=str(data.get("model") or provider),
    )


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _org_roster_markdown(container: Container) -> str:
    acl = container.access_control.read()
    users = acl.get("users", [])
    departments = acl.get("departments", [])
    roles_by_id = {
        str(role.get("id")): str(role.get("name") or role.get("id"))
        for role in acl.get("roles", [])
    }
    positions = acl.get("positions", [])
    positions_by_id = {
        str(position.get("id")): str(position.get("name") or position.get("id"))
        for position in positions
    }
    lines: list[str] = []
    if departments:
        children_by_parent: dict[str, list[dict[str, Any]]] = {}
        dept_ids = {str(dept.get("id")) for dept in departments}
        for dept in departments:
            parent_id = str(dept.get("parent_id") or "")
            # Treat references to missing parents as roots.
            key = parent_id if parent_id in dept_ids else ""
            children_by_parent.setdefault(key, []).append(dept)

        def _render(dept: dict[str, Any], depth: int) -> None:
            dept_id = str(dept.get("id"))
            members = [
                str(user.get("display_name") or user.get("id"))
                for user in users
                if str(user.get("department") or "") == dept_id
            ]
            lead_id = str(dept.get("lead_user_id") or "")
            lead = next(
                (
                    str(user.get("display_name") or user.get("id"))
                    for user in users
                    if str(user.get("id")) == lead_id
                ),
                "",
            )
            member_text = ", ".join(members) if members else "구성원 미지정"
            lead_text = f" · 리드 {lead}" if lead else ""
            indent = "  " * depth
            lines.append(f"{indent}- {dept.get('name')}{lead_text}: {member_text}")
            for child in children_by_parent.get(dept_id, []):
                _render(child, depth + 1)

        lines.append("부서(조직도):")
        for root in children_by_parent.get("", []):
            _render(root, 0)
    else:
        lines.append("부서: 등록된 부서 없음")
    if positions:
        ordered = sorted(positions, key=lambda item: _as_int(item.get("level")), reverse=True)
        lines.append("직급:")
        for position in ordered:
            lines.append(f"- {position.get('name')} (level {_as_int(position.get('level'))})")
    active_users = [user for user in users if user.get("active", True)]
    lines.append("사원:")
    if active_users:
        for user in active_users:
            dept_id = str(user.get("department") or "")
            dept_name = next(
                (str(dept.get("name")) for dept in departments if str(dept.get("id")) == dept_id),
                "부서 미배정",
            )
            role_name = roles_by_id.get(
                str(user.get("role_id") or ""), str(user.get("role_id") or "")
            )
            position_name = positions_by_id.get(str(user.get("position_id") or ""), "")
            position_text = f" · 직급 {position_name}" if position_name else ""
            title = str(user.get("title") or "")
            title_text = f" ({title})" if title else ""
            lines.append(
                f"- {user.get('display_name')}{title_text} · {dept_name}{position_text} · 권한 {role_name}"
            )
    else:
        lines.append("- 등록된 사원 없음")
    return "\n".join(lines)


def _office_context(container: Container) -> str:
    recent = _recent_logs(container.settings.archive_dir, limit=8)
    permanent = container.permanent_memory.recent(limit=8)
    permanent_md = "\n".join(
        f"- [{source.get('kind')}] {source.get('path')}: {source.get('title')}"
        for source in permanent
    )
    compressed = container.compressed_context.read(scope="global", key="default").to_markdown()
    volatile = container.volatile_memory.read(scope="global", key="default").to_markdown()
    recent_md = "\n".join(
        f"- {entry.get('repo', '')} #{entry.get('external_id', '')} status={entry.get('status', '')} path={entry.get('path', '')}"
        for entry in recent
    )
    org_md = _org_roster_markdown(container)
    return f"""
회사 메모리:
{container.operations_memory.read().to_markdown()}

조직/인사 체계:
{org_md}

현재 작업 메모리:
{container.work_memory.read().to_markdown()}

영구 원천 기록:
{permanent_md or "- 없음"}

압축 컨텍스트:
{compressed}

휘발성 메모리:
{volatile}

현재 상태:
{container.archive.status.read()}

최근 업무 로그:
{recent_md or "- 없음"}
""".strip()


def _resolve_document_attachments(
    container: Container,
    attachment_ids: list[str],
    *,
    vision_enabled: bool,
    audio_enabled: bool = False,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Resolve upload ids into prompt text, media parts, and human-readable notes.

    Returns ``(attachment_context_markdown, media_parts, notes)``. Text-extractable
    attachments are flattened into ``attachment_context``; images/audio are passed
    through as multimodal parts only when a capable model is active, otherwise text
    (OCR for images) is used and a note explains the fallback.
    """

    if not attachment_ids:
        return "", [], []
    records = {record["id"]: record for record in container.uploads.list()}
    archive_dir = container.settings.archive_dir
    blocks: list[str] = []
    media_parts: list[dict[str, Any]] = []
    notes: list[str] = []
    for attachment_id in attachment_ids:
        record = records.get(attachment_id)
        if record is None:
            notes.append(f"첨부 {attachment_id}: 업로드를 찾을 수 없습니다.")
            continue
        path = archive_dir / str(record.get("path") or "")
        extracted = extract_attachment(path, archive_root=archive_dir)
        if extracted.has_audio:
            if audio_enabled:
                media_parts.append(
                    audio_part(
                        mime=extracted.mime,
                        data=extracted.audio_b64,
                        fmt=extracted.audio_format,
                    )
                )
                notes.append(f"{extracted.filename}: 오디오 지원 모델에 오디오로 전달했습니다.")
            else:
                notes.append(
                    f"{extracted.filename}: 오디오 지원 모델이 없어 오디오 첨부를 건너뛰었습니다."
                )
            continue
        if extracted.has_image and vision_enabled:
            media_parts.append(image_part(mime=extracted.mime, data=extracted.image_b64))
            notes.append(f"{extracted.filename}: 비전 모델에 이미지로 전달했습니다.")
            if extracted.has_text:
                blocks.append(extracted.to_prompt_block())
            continue
        if extracted.has_image and not vision_enabled:
            if extracted.has_text:
                blocks.append(extracted.to_prompt_block())
                notes.append(f"{extracted.filename}: 비전 모델이 없어 OCR 텍스트로 처리했습니다.")
            else:
                notes.append(
                    f"{extracted.filename}: 비전 모델이 없고 OCR 텍스트도 없어 이미지를 건너뛰었습니다."
                )
            continue
        if extracted.has_text:
            blocks.append(extracted.to_prompt_block())
        if extracted.note:
            notes.append(f"{extracted.filename}: {extracted.note}")
    return "\n\n".join(blocks), media_parts, notes


_resolve_output_format = resolve_output_format
_write_generated_doc = write_generated_doc


_STEPS_JSON_RE = re.compile(r"```json\s*(\{.*?\"steps\".*?\})\s*```", re.DOTALL)


def _extract_process_steps(markdown: str) -> tuple[str, list[dict[str, str]]]:
    """Split the trailing machine-readable JSON steps block from the human markdown.

    Returns the markdown with the JSON block removed and the ordered step list.
    Falls back to an empty list when no parseable block is present.
    """

    matches = list(_STEPS_JSON_RE.finditer(markdown))
    if not matches:
        return markdown.strip(), []
    match = matches[-1]
    steps: list[dict[str, str]] = []
    try:
        parsed = json.loads(match.group(1))
        raw_steps = parsed.get("steps") if isinstance(parsed, dict) else None
        if isinstance(raw_steps, list):
            for entry in raw_steps:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name") or "").strip()
                if not name:
                    continue
                steps.append(
                    {
                        "name": name,
                        "automation": str(entry.get("automation") or "").strip(),
                        "reviewer": str(entry.get("reviewer") or "").strip(),
                        "output": str(entry.get("output") or "").strip(),
                    }
                )
    except (json.JSONDecodeError, AttributeError):
        return markdown.strip(), []
    clean = (markdown[: match.start()] + markdown[match.end() :]).strip()
    return clean, steps


def _coerce_steps(raw_steps: object) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    if not isinstance(raw_steps, list):
        return steps
    for entry in raw_steps:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        steps.append(
            {
                "name": name,
                "automation": str(entry.get("automation") or "").strip(),
                "reviewer": str(entry.get("reviewer") or "").strip(),
                "output": str(entry.get("output") or "").strip(),
            }
        )
    return steps


def _parse_steps_payload(text: str) -> list[dict[str, str]]:
    """Robustly extract a steps array from a (possibly noisy) LLM JSON response."""

    candidate = text.strip()
    if not candidate:
        return []
    fenced = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        return _coerce_steps(parsed.get("steps"))
    if isinstance(parsed, list):
        return _coerce_steps(parsed)
    return []


async def _create_handover_tasks(
    container: Container,
    *,
    work_title: str,
    incoming_owner: str,
    handover_markdown: str,
    activity_log: str,
    source_path: str,
) -> list[str]:
    """Derive follow-up tasks from the handover brief and register them for the
    incoming owner as work-schedule items."""

    owner_id, owner_name = _resolve_user_ref(container, incoming_owner)
    basis = handover_markdown
    if activity_log:
        basis = f"{handover_markdown}\n\n{activity_log}"
    try:
        steps = await _generate_process_steps(
            container,
            objective=f"{work_title} 인수인계 후속 업무",
            scope=owner_name or incoming_owner,
            markdown=basis,
        )
    except HTTPException:
        steps = []
    created: list[str] = []
    for step in steps:
        title = str(step.get("name") or step.get("title") or "").strip()
        if not title:
            continue
        note_parts = [
            str(step.get("automation") or "").strip(),
            str(step.get("output") or "").strip(),
        ]
        notes = " / ".join(part for part in note_parts if part)
        notes = (
            f"{notes}\n인수인계 출처: {source_path}" if notes else f"인수인계 출처: {source_path}"
        )
        item = container.work_schedule.upsert(
            WorkScheduleItem.create(
                title=title,
                owner_id=owner_id,
                owner_name=owner_name,
                priority="normal",
                notes=notes,
                assignee_kind="human",
                source_architecture_id=source_path,
            )
        )
        created.append(item.title)
    return created


async def _generate_process_steps(
    container: Container,
    *,
    objective: str,
    scope: str,
    markdown: str,
) -> list[dict[str, str]]:
    """Generate ordered process steps via a dedicated structured LLM call.

    Falls back to heuristic markdown parsing and finally a single review step so
    the queue is never left empty when a process design exists.
    """

    provider, route = _resolve_runtime_task(container, "document_generation")
    model = _resolve_task_model(container, "document_generation", provider, route)
    base_prompt = render_prompt(
        "office/work_process_steps_json.md.j2",
        objective=objective,
        scope=scope,
        markdown=markdown,
    ).strip()
    system = LlmMessage(
        "system",
        "당신은 업무 프로세스를 실행 가능한 단계로 분해하는 분석가입니다. "
        "반드시 순수 JSON만 출력하고, 설명이나 코드펜스를 추가하지 마세요.",
    )
    attempts = [
        base_prompt,
        base_prompt
        + "\n\n중요: 직전 출력이 형식에 맞지 않았습니다. 오직 JSON 객체 하나만 출력하세요.",
    ]
    for prompt in attempts:
        try:
            response = await _complete_with_provider(
                container,
                [system, LlmMessage("user", prompt)],
                provider=provider,
                route=route,
                temperature=0.1,
                max_tokens=1400,
                task="document_generation",
                model=model,
            )
        except HTTPException:
            break
        steps = _parse_steps_payload(response.text)
        if steps:
            return steps
    # Heuristic fallback: any inline JSON block left in the human markdown.
    _, heuristic_steps = _extract_process_steps(markdown)
    if heuristic_steps:
        return heuristic_steps
    objective_label = objective.strip() or "프로세스"
    return [
        {
            "name": f"{objective_label} 설계 검토 및 실행 준비",
            "automation": "설계 문서 요약 및 실행 항목 도출",
            "reviewer": "",
            "output": "검토 결과 및 다음 단계 정의",
        }
    ]


def _coerce_agent_steps(raw_steps: object) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    if not isinstance(raw_steps, list):
        return steps
    for index, entry in enumerate(raw_steps):
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or entry.get("name") or "").strip()
        if not title:
            continue
        steps.append(
            {
                "id": f"step-{index + 1}",
                "title": title,
                "detail": str(entry.get("detail") or "").strip(),
                "requires_approval": bool(entry.get("requires_approval", False)),
            }
        )
    return steps


def _parse_agent_steps_payload(text: str) -> list[dict[str, object]]:
    candidate = text.strip()
    if not candidate:
        return []
    fenced = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        return _coerce_agent_steps(parsed.get("steps"))
    if isinstance(parsed, list):
        return _coerce_agent_steps(parsed)
    return []


async def _generate_agent_plan_steps(
    container: Container,
    *,
    objective: str,
    context: str,
    schedule_refs: list[str],
    memory_refs: list[str],
) -> list[dict[str, object]]:
    """Plan execution steps from the conversation context via a structured LLM call.

    Falls back to the static template when no context is provided or the model
    fails to return usable JSON, so the plan is never left empty.
    """

    if not context.strip():
        return _agent_plan_steps(objective, schedule_refs, memory_refs)
    provider, route = _resolve_runtime_task(container, "chat")
    model = _resolve_task_model(container, "chat", provider, route)
    base_prompt = render_prompt(
        "office/agent_plan_steps_json.md.j2",
        objective=objective,
        context=context,
        schedule_refs=", ".join(schedule_refs),
        memory_refs=", ".join(memory_refs),
    ).strip()
    system = LlmMessage(
        "system",
        "당신은 대화 맥락을 실행 가능한 에이전트 계획 단계로 분해하는 분석가입니다. "
        "반드시 순수 JSON만 출력하고, 설명이나 코드펜스를 추가하지 마세요.",
    )
    attempts = [
        base_prompt,
        base_prompt
        + "\n\n중요: 직전 출력이 형식에 맞지 않았습니다. 오직 JSON 객체 하나만 출력하세요.",
    ]
    for prompt in attempts:
        try:
            response = await _complete_with_provider(
                container,
                [system, LlmMessage("user", prompt)],
                provider=provider,
                route=route,
                temperature=0.2,
                max_tokens=1200,
                task="chat",
                model=model,
            )
        except HTTPException:
            break
        steps = _parse_agent_steps_payload(response.text)
        if steps:
            return steps
    return _agent_plan_steps(objective, schedule_refs, memory_refs)


def _render_agent_plan_markdown(
    *,
    title: str,
    objective: str,
    steps: list[dict[str, object]],
    context: str,
) -> str:
    """Render an agent plan as a Cursor-style plan.md document."""

    lines = [f"# 계획: {title or objective or '제목 없음'}", ""]
    if objective:
        lines += ["## 목표", objective, ""]
    lines += ["## 실행 단계", ""]
    if steps:
        for index, step in enumerate(steps, start=1):
            step_title = str(step.get("title") or step.get("name") or f"단계 {index}")
            approval = " · 승인 필요" if step.get("requires_approval") else ""
            lines.append(f"{index}. [ ] {step_title}{approval}")
            detail = str(step.get("detail") or "").strip()
            if detail:
                lines.append(f"   - {detail}")
    else:
        lines.append("(단계 없음)")
    lines.append("")
    if context.strip():
        lines += ["## 대화 맥락 요약", "", "```", context.strip(), "```", ""]
    return "\n".join(lines).strip() + "\n"


_SKILL_DIRECTIVE_RE = re.compile(r"skill:\s*([A-Za-z0-9_.\-]+)")


def _extract_step_skill_id(notes: str) -> str:
    """Return a ``skill:<id>`` referenced in a step's notes, if it is registered."""

    match = _SKILL_DIRECTIVE_RE.search(notes or "")
    if not match:
        return ""
    candidate = match.group(1)
    return candidate if get_skill(candidate) is not None else ""


def _enqueue_process_steps(
    container: Container,
    *,
    architecture_id: str,
    objective: str,
    participants: str,
    steps: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Create ordered, sequentially-dependent schedule items for each step."""

    created: list[dict[str, object]] = []
    previous_id = ""
    for index, step in enumerate(steps, start=1):
        notes_parts = []
        if step.get("automation"):
            notes_parts.append(f"AI 자동화: {step['automation']}")
        if step.get("reviewer"):
            notes_parts.append(f"검토자: {step['reviewer']}")
        if step.get("output"):
            notes_parts.append(f"결과물: {step['output']}")
        notes_parts.append(f"설계 문서: {architecture_id}")
        item = container.work_schedule.upsert(
            WorkScheduleItem.create(
                title=f"[{index}단계] {step['name']}",
                owner_name=participants,
                status="todo",
                priority="high" if index == 1 else "normal",
                dependencies=[previous_id] if previous_id else [],
                notes=" / ".join(notes_parts),
                source_architecture_id=architecture_id,
                queue_order=index,
            )
        )
        previous_id = item.id
        created.append(item.to_dict())
    return created


def _recent_logs(archive_dir: Path, *, limit: int) -> list[dict[str, Any]]:
    candidates = [
        path
        for path in archive_dir.rglob("*.md")
        if path.name != "current_status.md" and "index" not in path.parts
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    logs: list[dict[str, Any]] = []
    for path in candidates[:limit]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        fm = parse_front_matter(text)
        logs.append(
            {
                "path": str(path.relative_to(archive_dir)),
                "title": path.name,
                "repo": fm.get("repo", ""),
                "source": fm.get("source", ""),
                "external_id": fm.get("external_id", ""),
                "status": fm.get("status", ""),
                "created": fm.get("created", ""),
                "llm_route": fm.get("llm_route", ""),
            }
        )
    return logs


def _schedule_to_work_items(
    schedule: list[dict[str, Any]],
    *,
    plan_status_by_step: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Render schedule queue entries as work-item rows with runnable ordering flags."""

    plan_status_by_step = plan_status_by_step or {}
    statuses = {str(entry.get("id")): entry.get("status") for entry in schedule}
    items: list[dict[str, Any]] = []
    for entry in schedule:
        step_id = str(entry.get("id"))
        deps = [str(dep) for dep in entry.get("dependencies", []) if str(dep)]
        blocking = [dep for dep in deps if statuses.get(dep) != "done"]
        item_status = str(entry.get("status") or "todo")
        plan_status = plan_status_by_step.get(step_id)
        gated = step_id in plan_status_by_step and plan_status not in {"approved", "running"}
        if item_status == "done":
            stage_state = "완료"
            runnable = False
        elif gated:
            stage_state = "승인 대기" if plan_status in {None, "draft"} else f"대기({plan_status})"
            runnable = False
        elif blocking:
            stage_state = "대기(이전 단계 진행 중)"
            runnable = False
        else:
            stage_state = "실행 대기(다음 차례)"
            runnable = True
        items.append(
            {
                "path": step_id,
                "id": step_id,
                "title": entry.get("title"),
                "summary": entry.get("title"),
                "status": item_status,
                "stage_state": stage_state,
                "runnable": runnable,
                "queue_order": entry.get("queue_order", 0),
                "kind": "프로세스 단계" if entry.get("source_architecture_id") else "스케줄",
                "source": "queue",
                "source_architecture_id": entry.get("source_architecture_id", ""),
                "notes": entry.get("notes", ""),
                "owner_id": entry.get("owner_id", ""),
                "owner_name": entry.get("owner_name", ""),
                "assignee_kind": entry.get("assignee_kind", "unassigned"),
                "signed_off_by": entry.get("signed_off_by", ""),
                "signed_off_at": entry.get("signed_off_at", ""),
                "completion_record": entry.get("completion_record", ""),
                "priority": entry.get("priority", "normal"),
            }
        )
    return items


def _resequence_plan(
    container: Container, plan: ProcessPlan, ordered_ids: list[str]
) -> ProcessPlan:
    """Reassign queue_order + linear dependencies for a plan's steps and persist."""

    by_id = {str(entry.get("id")): entry for entry in container.work_schedule.list()}
    valid_ids = [sid for sid in ordered_ids if sid in by_id]
    previous_id = ""
    for index, sid in enumerate(valid_ids, start=1):
        entry = by_id[sid]
        container.work_schedule.upsert(
            WorkScheduleItem.create(
                **{
                    **entry,
                    "queue_order": index,
                    "dependencies": [previous_id] if previous_id else [],
                    "source_architecture_id": plan.architecture_path,
                }
            )
        )
        previous_id = sid
    return container.process_plans.upsert(plan.with_steps(valid_ids))


def _require_plan(container: Container, plan_id: str) -> ProcessPlan:
    plan = container.process_plans.get(plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="계획을 찾을 수 없습니다."
        )
    return plan


def _require_editable_plan(container: Container, plan_id: str) -> ProcessPlan:
    plan = _require_plan(container, plan_id)
    if plan.status not in {"draft", "approved", "paused"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="완료/취소된 계획은 단계를 편집할 수 없습니다.",
        )
    return plan


def _plan_status_by_step(container: Container) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for plan in container.process_plans.list():
        status = str(plan.get("status") or "draft")
        step_ids = plan.get("step_ids", [])
        if not isinstance(step_ids, list):
            continue
        for step_id in step_ids:
            mapping[str(step_id)] = status
    return mapping


def _process_plan_payload(
    container: Container,
    plan: ProcessPlan,
    *,
    include_markdown: bool = False,
) -> ProcessPlanPayload:
    schedule = container.work_schedule.list()
    by_id = {str(entry.get("id")): entry for entry in schedule}
    gate = dict.fromkeys(plan.step_ids, plan.status)
    ordered = [by_id[sid] for sid in plan.step_ids if sid in by_id]
    steps = _schedule_to_work_items(ordered, plan_status_by_step=gate)
    step_done = len([row for row in steps if row.get("status") == "done"])
    plan_markdown = ""
    if include_markdown and plan.architecture_path:
        try:
            plan_markdown = _read_archive_document(container, plan.architecture_path).markdown
        except HTTPException:
            plan_markdown = ""
    return ProcessPlanPayload(
        id=plan.id,
        objective=plan.objective,
        architecture_path=plan.architecture_path,
        status=plan.status,
        mode=plan.mode,
        approved_by=plan.approved_by,
        approved_at=plan.approved_at,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        step_total=len(steps),
        step_done=step_done,
        steps=steps,
        plan_markdown=plan_markdown,
    )


def _summarize_queue(queue_items: list[dict[str, Any]]) -> str:
    if not queue_items:
        return ""
    total = len(queue_items)
    done = len([item for item in queue_items if item.get("status") == "done"])
    runnable = [item for item in queue_items if item.get("runnable")]
    lines = [f"프로세스 단계 큐 {total}건 중 완료 {done}건, 남은 단계 {total - done}건입니다."]
    if runnable:
        lines.append(f"다음 실행 차례: {runnable[0].get('title')}")
    elif done < total:
        lines.append("실행 가능한 다음 단계가 없습니다. 진행 중인 단계 완료를 기다리세요.")
    else:
        lines.append("모든 프로세스 단계가 완료되었습니다.")
    return "\n".join(lines)


def _summarize_bottlenecks(items: list[dict[str, Any]]) -> str:
    if not items:
        return "아직 업무 로그가 없어 병목을 판단할 수 없습니다."
    rejected = [item for item in items if item.get("status") in {"rejected", "exhausted"}]
    proposed = [item for item in items if item.get("status") == "proposed"]
    lines = [
        f"최근 업무 {len(items)}건 중 제안 완료 {len(proposed)}건, 재검토/거절 {len(rejected)}건입니다.",
    ]
    if rejected:
        lines.append("우선 확인이 필요한 병목 후보:")
        lines.extend(
            f"- {item.get('summary') or item.get('title')} ({item.get('status')})"
            for item in rejected[:5]
        )
    else:
        lines.append("명시적인 실패 상태는 없습니다. 오래된 진행 항목과 담당자 공백을 확인하세요.")
    return "\n".join(lines)


def _resolve_github_runtime(
    container: Container,
) -> tuple[GitHubConnectorConfig, str, str]:
    config = container.integration_config.read().github
    saved_token = container.secret_store.read("github_app")
    token = (saved_token.api_key if saved_token else "") or container.settings.github.app_token
    trigger_label = config.trigger_label or container.settings.github.trigger_label
    return config, token, trigger_label


def _resolve_discord_runtime(
    container: Container,
) -> tuple[DiscordConnectorConfig, str]:
    config = container.integration_config.read().discord
    saved_token = container.secret_store.read("discord_bot")
    token = (saved_token.api_key if saved_token else "") or container.settings.discord.bot_token
    return config, token


def _save_github_secrets(container: Container, payload: GitHubConnectorPayload) -> None:
    if payload.app_token.strip():
        container.secret_store.upsert(
            ApiKeyRecord(
                provider="github_app",
                api_key=payload.app_token.strip(),
                model="",
                base_url="",
            )
        )
    if payload.webhook_secret.strip():
        container.secret_store.upsert(
            ApiKeyRecord(
                provider="github_webhook",
                api_key=payload.webhook_secret.strip(),
                model="",
                base_url="",
            )
        )


def _save_discord_secrets(container: Container, payload: DiscordConnectorPayload) -> None:
    if payload.bot_token.strip():
        container.secret_store.upsert(
            ApiKeyRecord(
                provider="discord_bot",
                api_key=payload.bot_token.strip(),
                model="",
                base_url="",
            )
        )


def _integration_config_payload(
    container: Container,
    *,
    config: IntegrationConfig | None = None,
) -> IntegrationConfigPayload:
    config = config or container.integration_config.read()
    github = config.github
    discord = config.discord
    return IntegrationConfigPayload(
        github=GitHubConnectorPayload(
            enabled=github.enabled,
            allowed_repos=list(github.allowed_repos),
            trigger_label=github.trigger_label,
            webhook_secret_present=container.secret_store.has_secret("github_webhook"),
            app_token_present=container.secret_store.has_secret("github_app"),
            event_forms=list(github.event_forms),
        ),
        discord=DiscordConnectorPayload(
            enabled=discord.enabled,
            bot_token_present=container.secret_store.has_secret("discord_bot"),
            guild_allowlist=list(discord.guild_allowlist),
            channel_bindings=[
                DiscordChannelBindingPayload(
                    guild_id=binding.guild_id,
                    channel_id=binding.channel_id,
                    channel_name=binding.channel_name,
                    repo=binding.repo,
                )
                for binding in discord.channel_bindings
            ],
            command_forms=list(discord.command_forms),
        ),
    )


def _read_archive_document(container: Container, raw_path: str) -> DocumentReadPayload:
    if not raw_path or not raw_path.strip():
        raise ValueError("path 는 필수입니다.")
    cleaned = raw_path.strip().lstrip("/")
    if "\x00" in cleaned:
        raise ValueError("path 에 잘못된 문자가 포함되어 있습니다.")
    archive_root = container.settings.archive_dir.resolve()
    candidate = (archive_root / cleaned).resolve()
    try:
        candidate.relative_to(archive_root)
    except ValueError as exc:
        raise ValueError("archive 외부 경로는 열람할 수 없습니다.") from exc
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"문서를 찾을 수 없습니다: {cleaned}")
    if candidate.suffix.lower() not in {
        ".md",
        ".markdown",
        ".txt",
        ".json",
        ".jsonl",
        ".patch",
        ".yaml",
        ".yml",
    }:
        raise ValueError("열람 지원 파일 형식이 아닙니다.")
    text = candidate.read_text(encoding="utf-8")
    stat = candidate.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
    return DocumentReadPayload(
        path=str(candidate.relative_to(archive_root)).replace("\\", "/"),
        markdown=text,
        bytes=stat.st_size,
        modified_at=modified,
    )


def _archive_document_index(container: Container, *, q: str, limit: int) -> list[dict[str, object]]:
    archive_root = container.settings.archive_dir.resolve()
    if not archive_root.exists():
        return []
    query_tokens = q.strip().lower().split()
    docs: list[dict[str, object]] = []
    for path in archive_root.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in {
            ".md",
            ".markdown",
            ".txt",
            ".json",
            ".patch",
            ".yaml",
            ".yml",
        }:
            continue
        try:
            rel = path.relative_to(archive_root).as_posix()
        except ValueError:
            continue
        if _is_internal_archive_document(rel):
            continue
        title, excerpt = _archive_document_title_excerpt(path)
        kind = _archive_document_kind(rel)
        haystack = f"{title} {excerpt} {rel} {kind}".lower()
        compact = haystack.replace("_", "").replace("-", "")
        if query_tokens and not all(
            token in haystack or token.replace("_", "").replace("-", "") in compact
            for token in query_tokens
        ):
            continue
        stat = path.stat()
        docs.append(
            {
                "path": rel,
                "title": title,
                "kind": kind,
                "excerpt": excerpt[:220],
                "bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
            }
        )
    docs.sort(key=lambda item: str(item.get("modified_at") or ""), reverse=True)
    return docs[:limit]


def _is_internal_archive_document(rel: str) -> bool:
    return (
        rel == "audit_log.jsonl"
        or rel.startswith("token_usage/")
        or rel.startswith("context_firewall/")
        or rel.startswith("mcp_hub/")
        or rel.startswith("ai_jobs/")
        or rel.startswith("patch_ops/events/")
        or rel.startswith("patch_ops/runs/")
        or rel.startswith("memory/deletion_requests")
        or rel.startswith("memory/tombstones")
    )


def _archive_document_kind(rel: str) -> str:
    first = rel.split("/", 1)[0]
    labels = {
        "documents": "문서 자동화",
        "work_architecture": "업무 아키텍처",
        "hr": "채용/면접",
        "handover": "인수인계",
        "patch_records": "코딩 패치 기록",
        "patch_ops": "AI 개발 도우미",
        "uploads": "업로드",
        "memory": "승격 메모리",
    }
    return labels.get(first, "문서")


def _archive_document_title_excerpt(path: Path) -> tuple[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:2000]
    except OSError:
        return path.stem, ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.stem, text[:500]
    return path.stem.replace("_", " "), text[:500]


def _token_limit_status(container: Container) -> TokenLimitStatusPayload:
    limits = container.token_usage.read_limits()
    summary = container.token_usage.summary()
    return TokenLimitStatusPayload(
        limits=TokenLimitPayload(**limits.to_dict()),
        usage=TokenUsageSummaryPayload(
            daily_total=summary.daily_total,
            monthly_total=summary.monthly_total,
            by_provider=dict(summary.by_provider),
            by_task=dict(summary.by_task),
            by_actor=dict(summary.by_actor),
            recent=[TokenUsageEntryPayload(**entry.to_dict()) for entry in summary.recent],
        ),
    )


def _patch_record_payload(record: PatchRecord) -> PatchRecordPayload:
    return PatchRecordPayload(**record.to_dict())


def _patch_record_detail_payload(record: PatchRecord, markdown: str) -> PatchRecordDetailPayload:
    return PatchRecordDetailPayload(markdown=markdown, **record.to_dict())


async def _fetch_github_status(container: Container) -> IntegrationStatusPayload:
    config, token, trigger_label = _resolve_github_runtime(container)
    if not config.enabled:
        return IntegrationStatusPayload(
            ok=False,
            configured=False,
            reason="GitHub 커넥터가 비활성 상태입니다. 설정 폼에서 활성화하세요.",
            items=[],
        )
    repos = config.allowed_repos or container.settings.github.allowed_repos
    if not repos:
        return IntegrationStatusPayload(
            ok=False,
            configured=False,
            reason="허용된 저장소가 없습니다. GitHub 설정에 repo를 추가하세요.",
            items=[],
        )
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    items: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=10) as client:
        for repo in repos:
            try:
                response = await client.get(
                    f"https://api.github.com/repos/{repo}/issues",
                    headers=headers,
                    params={
                        "state": "open",
                        "labels": trigger_label,
                        "per_page": 10,
                        "sort": "updated",
                    },
                )
                response.raise_for_status()
                issues = response.json()
                items.append(
                    {
                        "repo": repo,
                        "open_issue_count": len(issues) if isinstance(issues, list) else 0,
                        "event_forms": list(config.event_forms),
                        "issues": [
                            {
                                "number": issue.get("number"),
                                "title": issue.get("title"),
                                "url": issue.get("html_url"),
                                "updated_at": issue.get("updated_at"),
                            }
                            for issue in issues
                            if isinstance(issue, dict)
                        ],
                    }
                )
            except Exception as exc:
                items.append({"repo": repo, "error": str(exc)})
    return IntegrationStatusPayload(ok=True, configured=True, items=items)


async def _fetch_discord_status(container: Container) -> IntegrationStatusPayload:
    config, token = _resolve_discord_runtime(container)
    if not config.enabled:
        return IntegrationStatusPayload(
            ok=False,
            configured=False,
            reason="Discord 커넥터가 비활성 상태입니다. 설정 폼에서 활성화하세요.",
            items=[],
        )
    bindings: list[DiscordChannelBindingConfig] = list(config.channel_bindings)
    if not bindings:
        for legacy in container.discord.channel_map.bindings:
            bindings.append(
                DiscordChannelBindingConfig(
                    guild_id=legacy.guild_id,
                    channel_id=legacy.channel_id,
                    channel_name=legacy.channel_name,
                    repo=legacy.repo.full_name,
                )
            )
    if not bindings:
        return IntegrationStatusPayload(
            ok=False,
            configured=False,
            reason="채널 바인딩이 없습니다. Discord 설정 폼에서 채널을 등록하세요.",
            items=[],
        )
    items: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=10) as client:
        for binding in bindings:
            item: dict[str, Any] = {
                "guild_id": binding.guild_id,
                "channel_id": binding.channel_id,
                "channel_name": binding.channel_name,
                "repo": binding.repo,
                "live": False,
                "command_forms": list(config.command_forms),
            }
            if token and binding.channel_id:
                try:
                    response = await client.get(
                        f"https://discord.com/api/v10/channels/{binding.channel_id}",
                        headers={"Authorization": f"Bot {token}"},
                    )
                    response.raise_for_status()
                    data = response.json()
                    item.update({"live": True, "name": data.get("name", binding.channel_name)})
                except Exception as exc:
                    item["error"] = str(exc)
            elif not token:
                item["reason"] = "Discord bot 토큰이 등록되지 않았습니다."
            items.append(item)
    return IntegrationStatusPayload(ok=True, configured=True, items=items)
