"""Patch Note setup recommendation catalog."""

from __future__ import annotations

from typing import Any

from negotium.app.schemas.core import CompanyProfilePayload

PACKAGE_BY_SIZE = {
    "solo": "Patch Note Solo",
    "startup": "Patch Note Team",
    "smb": "Patch Note Business",
    "mid_market": "Patch Note Business",
    "enterprise_public": "Patch Note Enterprise",
}

DEPARTMENT_AGENT_PACKS: dict[str, dict[str, Any]] = {
    "executive": {
        "id": "executive",
        "name": "CEO 브리핑 에이전트",
        "description": "전사 패치 노트, KPI 이슈, 의사결정 로그를 요약합니다.",
    },
    "hr": {
        "id": "hr",
        "name": "HR 에이전트",
        "description": "채용공고, 면접 질문, 온보딩 체크리스트, 인사 규정 Q&A를 지원합니다.",
    },
    "finance": {
        "id": "finance",
        "name": "재무/회계 에이전트",
        "description": "월말 보고, 비용 정리, 예산 초과 알림, 감사 대응 폴더를 제안합니다.",
    },
    "sales": {
        "id": "sales",
        "name": "영업 에이전트",
        "description": "고객 미팅 요약, 제안서 초안, CRM 업데이트와 파이프라인 요약을 지원합니다.",
    },
    "marketing": {
        "id": "marketing",
        "name": "마케팅 에이전트",
        "description": "캠페인 기획, 콘텐츠 작성, 리뷰 분석, 브랜드 톤 유지를 지원합니다.",
    },
    "cs": {
        "id": "cs",
        "name": "CS 에이전트",
        "description": "문의 분류, 답변 초안, FAQ 업데이트, 장애 보고를 지원합니다.",
    },
    "product_dev_it": {
        "id": "product_dev_it",
        "name": "제품/개발/IT 에이전트",
        "description": "PRD, 릴리즈 노트, 버그 리포트, 장애 포스트모템을 생성합니다.",
    },
    "legal": {
        "id": "legal",
        "name": "법무/컴플라이언스 보조 에이전트",
        "description": "계약 요약, 표준 조항 비교, 규정 Q&A를 사람 검토 전제로 보조합니다.",
    },
    "ops_procurement": {
        "id": "ops_procurement",
        "name": "운영/구매 에이전트",
        "description": "구매요청, 공급업체 비교, 운영 리포트, 작업지시서를 지원합니다.",
    },
}

INDUSTRY_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "it_saas": [
        {"id": "release_notes", "name": "제품 릴리즈 노트", "priority": "p0"},
        {"id": "prd", "name": "PRD/로드맵", "priority": "p0"},
        {"id": "incident_postmortem", "name": "장애 포스트모템", "priority": "p1"},
    ],
    "b2b_sales_cs": [
        {"id": "customer_meeting", "name": "고객 미팅 요약", "priority": "p0"},
        {"id": "proposal", "name": "제안서 초안", "priority": "p0"},
        {"id": "weekly_sales_report", "name": "주간 영업 리포트", "priority": "p1"},
    ],
    "professional_services": [
        {"id": "client_intake", "name": "고객 인테이크", "priority": "p0"},
        {"id": "consulting_report", "name": "컨설팅 보고서", "priority": "p0"},
        {"id": "change_history", "name": "산출물 변경 이력", "priority": "p1"},
    ],
    "manufacturing": [
        {"id": "sop", "name": "생산 SOP", "priority": "p0"},
        {"id": "quality_report", "name": "품질 이슈 리포트", "priority": "p0"},
        {"id": "equipment_check", "name": "설비점검 기록", "priority": "p1"},
    ],
    "construction": [
        {"id": "daily_construction_report", "name": "일일 공사일보", "priority": "p0"},
        {"id": "safety_check", "name": "안전관리 체크리스트", "priority": "p0"},
        {"id": "rfi_log", "name": "RFI/설계 변경 로그", "priority": "p1"},
    ],
    "finance": [
        {"id": "audit_brief", "name": "감사 대응 브리프", "priority": "p0"},
        {"id": "risk_review", "name": "리스크 검토 메모", "priority": "p0"},
    ],
    "healthcare": [
        {"id": "care_admin_summary", "name": "행정/케어 기록 요약", "priority": "p0"},
        {"id": "privacy_check", "name": "민감정보 보호 체크리스트", "priority": "p0"},
    ],
    "public": [
        {"id": "official_document", "name": "공문/보고서", "priority": "p0"},
        {"id": "civil_complaint_summary", "name": "민원 요약", "priority": "p0"},
    ],
}

GOAL_WORKFLOWS: dict[str, dict[str, Any]] = {
    "meeting_notes": {
        "id": "meeting_notes",
        "name": "회의 자동 기록",
        "description": "회의록에서 결정사항, 반대 의견, 담당자, 기한을 추출합니다.",
    },
    "action_items": {
        "id": "action_items",
        "name": "액션아이템 자동 생성",
        "description": "회의/문서/메시지에서 할 일, 담당자, 마감일을 만듭니다.",
    },
    "weekly_patch_notes": {
        "id": "weekly_patch_notes",
        "name": "팀 패치 노트",
        "description": "팀의 완료 작업, 이슈, 결정사항, 다음 주 계획을 자동 정리합니다.",
    },
    "release_notes": {
        "id": "release_notes",
        "name": "릴리즈 노트 자동화",
        "description": "GitHub/Jira 변경사항을 고객용/내부용 릴리즈 노트로 정리합니다.",
    },
    "integrated_search": {
        "id": "integrated_search",
        "name": "권한 기반 통합 검색",
        "description": "문서, 회의록, 채팅, 파일을 권한 인식 RAG로 검색합니다.",
    },
    "customer_memory": {
        "id": "customer_memory",
        "name": "고객/프로젝트 메모리",
        "description": "고객별 히스토리, 결정사항, 담당자 맥락을 기억합니다.",
    },
    "proposal_docs": {
        "id": "proposal_docs",
        "name": "제안서/보고서 자동화",
        "description": "고객 요구사항과 회의록을 바탕으로 제안서와 보고서를 만듭니다.",
    },
}

SENSITIVE_VALUES = {
    "customer_info",
    "hr_info",
    "finance_info",
    "medical_info",
    "trade_secret",
}


def recommend_patchnote_setup(
    profile: CompanyProfilePayload, *, sensitive_hint: bool = False
) -> dict[str, Any]:
    industries = profile.industries or ["it_saas"]
    departments = profile.departments or ["product_dev_it", "cs"]
    goals = profile.primary_goals or ["weekly_patch_notes", "integrated_search"]
    sensitivities = set(profile.data_sensitivity or ["general"])
    local_required = (
        bool(sensitivities & SENSITIVE_VALUES)
        or sensitive_hint
        or profile.deployment_preference == "private_required"
    )

    agent_packs = _unique_by_id(DEPARTMENT_AGENT_PACKS.get(item) for item in departments)
    templates = _unique_by_id(
        template for industry in industries for template in INDUSTRY_TEMPLATES.get(industry, [])
    )
    workflows = _unique_by_id(GOAL_WORKFLOWS.get(item) for item in goals)
    integrations = _integration_priorities(industries, departments, goals)
    integrations = _augment_integrations_from_profile(integrations, profile)
    security_defaults = _security_defaults(profile, local_required=local_required)

    return {
        "workspace_profile": profile.model_dump(),
        "recommended_package": PACKAGE_BY_SIZE.get(profile.organization_size, "Patch Note Team"),
        "agent_packs": agent_packs,
        "templates": templates,
        "workflows": workflows,
        "security_defaults": security_defaults,
        "integration_priorities": integrations,
        "llm_task_routes": _llm_task_routes(local_required=local_required),
        "first_14_days": _first_14_days(goals, industries, profile=profile),
        "human_review_required": _human_review_required(departments, sensitivities),
        "operations_memory_seed": _operations_memory_seed(profile),
        "work_memory_seed": _work_memory_seed(profile),
    }


def render_recommendation_markdown(recommendation: dict[str, Any]) -> str:
    sections = [
        f"추천 패키지: {recommendation.get('recommended_package', 'Patch Note Team')}",
        _items_markdown("에이전트 팩", recommendation.get("agent_packs", [])),
        _items_markdown("템플릿", recommendation.get("templates", [])),
        _items_markdown("워크플로우", recommendation.get("workflows", [])),
        _items_markdown("연동 우선순위", recommendation.get("integration_priorities", [])),
        _items_markdown("보안 기본값", recommendation.get("security_defaults", [])),
        _lines_markdown("첫 14일 실행", recommendation.get("first_14_days", [])),
    ]
    return "\n\n".join(section for section in sections if section.strip())


def _unique_by_id(items: Any) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or item.get("name") or "")
        if item_id and item_id not in unique:
            unique[item_id] = dict(item)
    return list(unique.values())


def _integration_priorities(
    industries: list[str], departments: list[str], goals: list[str]
) -> list[dict[str, Any]]:
    priorities: list[dict[str, Any]] = [
        {"id": "slack", "name": "Slack", "reason": "회의/메시지 기반 액션 추출"},
        {"id": "notion", "name": "Notion", "reason": "위키와 문서 지식베이스 연결"},
    ]
    if "it_saas" in industries or "product_dev_it" in departments or "release_notes" in goals:
        priorities.extend(
            [
                {"id": "github", "name": "GitHub", "reason": "PR/이슈 기반 릴리즈 노트 자동화"},
                {"id": "jira", "name": "Jira/Linear", "reason": "제품 요구사항과 작업 보드 연결"},
            ]
        )
    if "sales" in departments or "cs" in departments or "customer_memory" in goals:
        priorities.extend(
            [
                {"id": "hubspot", "name": "HubSpot/Salesforce", "reason": "CRM 고객 메모리 연결"},
                {
                    "id": "zendesk",
                    "name": "Zendesk/Intercom",
                    "reason": "CS 문의 분류와 FAQ 업데이트",
                },
            ]
        )
    if any(item in industries for item in ("finance", "manufacturing", "construction")):
        priorities.append({"id": "erp", "name": "ERP/회계툴", "reason": "레거시 업무 데이터 연결"})
    return _unique_by_id(priorities)


def _security_defaults(
    profile: CompanyProfilePayload, *, local_required: bool
) -> list[dict[str, Any]]:
    defaults = [
        {"id": "source_citation", "name": "AI 답변 출처 표시", "enabled": True},
        {"id": "audit_log", "name": "검색/생성/승인 감사로그", "enabled": True},
        {"id": "pii_detection", "name": "민감정보 감지와 마스킹", "enabled": True},
        {"id": "human_approval", "name": "고위험 업무 사람 검토 필수", "enabled": True},
    ]
    defaults.append(
        {
            "id": "local_model_routing",
            "name": "민감 업무 로컬 에이전트 라우팅",
            "enabled": local_required,
            "reason": "민감정보 또는 private 배포 요구"
            if local_required
            else "일반 업무는 API 모델 허용 가능",
        }
    )
    if profile.organization_size == "enterprise_public":
        defaults.extend(
            [
                {"id": "retention_policy", "name": "데이터 보존 정책", "enabled": True},
                {"id": "agent_governance", "name": "AI 에이전트 등록/승인/폐기", "enabled": True},
            ]
        )
    return defaults


def _llm_task_routes(*, local_required: bool) -> dict[str, dict[str, str]]:
    if local_required:
        return {
            task: {"route": "local", "provider": "vllm", "model": "Qwen/Qwen3-4B"}
            for task in ("memory_summary", "document_generation", "chat", "hiring", "handover")
        }
    return {
        "memory_summary": {"route": "local", "provider": "vllm", "model": "Qwen/Qwen3-4B"},
        "chat": {"route": "local", "provider": "vllm", "model": "Qwen/Qwen3-4B"},
    }


def _first_14_days(
    goals: list[str],
    industries: list[str],
    *,
    profile: CompanyProfilePayload | None = None,
) -> list[str]:
    actions = [
        "1일차: 회사 파일과 핵심 업무 문서를 업로드하고 권한 범위를 확인합니다.",
        "3일차: 회의록에서 결정사항과 액션아이템을 자동 추출해 팀 패치 노트를 만듭니다.",
        "7일차: 주간 패치 노트를 대표/팀장용 요약으로 발행합니다.",
    ]
    if "release_notes" in goals or "it_saas" in industries:
        actions.append("10일차: GitHub/Jira 변경사항으로 제품 릴리즈 노트 자동화를 연결합니다.")
    if profile is not None:
        priority_text = (profile.automation_priorities or "").strip()
        if priority_text:
            actions.append(
                f"5일차: 사용자가 지정한 우선 자동화 대상부터 적용합니다 — {priority_text}"
            )
        recurring = (profile.recurring_workflows or "").strip()
        if recurring:
            actions.append(f"7일차: 반복 업무/회의에 운영 템플릿을 연결합니다 — {recurring}")
        change_needs = (profile.change_management_needs or "").strip()
        if change_needs:
            actions.append(f"9일차: 변경사항 누락 이슈를 패치 노트로 해결합니다 — {change_needs}")
    actions.append("14일차: 에이전트 팩, 템플릿, 보안 정책의 실제 사용 결과를 검토합니다.")
    return actions


def _augment_integrations_from_profile(
    integrations: list[dict[str, Any]], profile: CompanyProfilePayload
) -> list[dict[str, Any]]:
    text = (profile.current_tools or "").lower()
    if not text:
        return integrations
    extras: list[dict[str, Any]] = []
    keyword_map = [
        ("slack", {"id": "slack", "name": "Slack", "reason": "사용자가 도구로 지정"}),
        ("notion", {"id": "notion", "name": "Notion", "reason": "사용자가 도구로 지정"}),
        ("jira", {"id": "jira", "name": "Jira/Linear", "reason": "사용자가 도구로 지정"}),
        ("linear", {"id": "jira", "name": "Jira/Linear", "reason": "사용자가 도구로 지정"}),
        ("github", {"id": "github", "name": "GitHub", "reason": "사용자가 도구로 지정"}),
        ("gitlab", {"id": "github", "name": "GitHub/GitLab", "reason": "사용자가 도구로 지정"}),
        (
            "hubspot",
            {"id": "hubspot", "name": "HubSpot/Salesforce", "reason": "사용자가 도구로 지정"},
        ),
        (
            "salesforce",
            {"id": "hubspot", "name": "HubSpot/Salesforce", "reason": "사용자가 도구로 지정"},
        ),
        (
            "zendesk",
            {"id": "zendesk", "name": "Zendesk/Intercom", "reason": "사용자가 도구로 지정"},
        ),
        (
            "intercom",
            {"id": "zendesk", "name": "Zendesk/Intercom", "reason": "사용자가 도구로 지정"},
        ),
        (
            "google",
            {
                "id": "google_workspace",
                "name": "Google Workspace",
                "reason": "사용자가 도구로 지정",
            },
        ),
        (
            "drive",
            {
                "id": "google_workspace",
                "name": "Google Workspace",
                "reason": "사용자가 도구로 지정",
            },
        ),
        (
            "microsoft",
            {"id": "microsoft_365", "name": "Microsoft 365", "reason": "사용자가 도구로 지정"},
        ),
        (
            "office 365",
            {"id": "microsoft_365", "name": "Microsoft 365", "reason": "사용자가 도구로 지정"},
        ),
    ]
    for keyword, payload in keyword_map:
        if keyword in text:
            extras.append(payload)
    return _unique_by_id([*integrations, *extras])


def _operations_memory_seed(profile: CompanyProfilePayload) -> dict[str, str]:
    seed: dict[str, str] = {}
    if profile.company_name.strip():
        seed["company_name"] = profile.company_name.strip()
    if profile.office_project.strip():
        seed["office_project"] = profile.office_project.strip()
    workflow_lines: list[str] = []
    if profile.work_summary.strip():
        workflow_lines.append(f"회사 업무 요약: {profile.work_summary.strip()}")
    if profile.recurring_workflows.strip():
        workflow_lines.append(f"반복 업무/회의: {profile.recurring_workflows.strip()}")
    if profile.change_management_needs.strip():
        workflow_lines.append(f"변경사항 관리 이슈: {profile.change_management_needs.strip()}")
    if workflow_lines:
        seed["key_workflows"] = "\n".join(workflow_lines)
    if profile.current_tools.strip():
        seed["office_tools"] = profile.current_tools.strip()
    return seed


def _work_memory_seed(profile: CompanyProfilePayload) -> dict[str, str]:
    seed: dict[str, str] = {}
    if profile.office_project.strip():
        seed["goals"] = profile.office_project.strip()
    if profile.automation_priorities.strip():
        seed["next_actions"] = profile.automation_priorities.strip()
    if profile.work_summary.strip():
        seed["current_focus"] = profile.work_summary.strip()
    if profile.change_management_needs.strip():
        seed["risks"] = profile.change_management_needs.strip()
    return seed


def _human_review_required(departments: list[str], sensitivities: set[str]) -> list[str]:
    required = ["외부 발송 문서", "고객 공지", "권한/계정 변경"]
    if "hr" in departments or "hr_info" in sensitivities:
        required.extend(["채용 평가", "인사 평가", "급여/개인정보 문서"])
    if "finance" in departments or "finance_info" in sensitivities:
        required.extend(["재무 보고", "신용/거래 리스크 판단"])
    if "legal" in departments:
        required.append("법률/계약 최종 판단")
    if "medical_info" in sensitivities:
        required.append("진단/처방/치료 관련 판단")
    return list(dict.fromkeys(required))


def _items_markdown(title: str, items: Any) -> str:
    if not isinstance(items, list) or not items:
        return ""
    lines = [f"### {title}"]
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("id")
        description = item.get("description") or item.get("reason") or item.get("priority") or ""
        lines.append(f"- {name}: {description}".rstrip(": "))
    return "\n".join(lines)


def _lines_markdown(title: str, lines: Any) -> str:
    if not isinstance(lines, list) or not lines:
        return ""
    return "\n".join([f"### {title}", *(f"- {line}" for line in lines)])
