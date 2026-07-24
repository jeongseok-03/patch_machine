from negotium.app.initial_setup import ParsedSetupFile
from negotium.app.schemas import CompanyProfilePayload, InitialOfficeAnalyzeRequest
from negotium.app.services.office_setup_service import parse_initial_setup_result
from negotium.app.services.setup_catalog import recommend_patchnote_setup
from negotium.prompts import render


def test_prompt_store_renders_context_compression_prompt() -> None:
    prompt = render(
        "office/context_compression.md.j2",
        query="고객 인수인계",
        token_budget=1200,
        source_md="### memory/customer.md\n계약 상태",
        volatile_appendix="최근 통화 요약",
    )

    assert "1200" in prompt
    assert "고객 인수인계" in prompt
    assert "최근 통화 요약" in prompt


def test_initial_setup_parser_falls_back_from_non_json() -> None:
    parsed_files = [
        ParsedSetupFile(
            path="uploads/users.csv",
            filename="users.csv",
            kind="csv",
            text="이름,직함,부서",
            rows=[{"이름": "홍길동", "직함": "팀장", "부서": "운영"}],
            sensitive_hint=True,
        )
    ]

    result = parse_initial_setup_result("not json", parsed_files=parsed_files)

    assert result.sensitive_hint is True
    assert result.users[0].id
    assert any("로컬 에이전트 서버" in warning for warning in result.warnings)


def test_initial_setup_request_accepts_company_profile() -> None:
    payload = InitialOfficeAnalyzeRequest(
        company_profile={
            "organization_size": "startup",
            "industries": ["it_saas"],
            "departments": ["product_dev_it", "cs"],
            "primary_goals": ["release_notes", "weekly_patch_notes"],
            "data_sensitivity": ["customer_info"],
            "deployment_preference": "local_recommended",
        }
    )

    assert payload.company_profile.organization_size == "startup"
    assert "release_notes" in payload.company_profile.primary_goals


def test_patchnote_catalog_recommends_dev_release_note_setup() -> None:
    recommendation = recommend_patchnote_setup(
        CompanyProfilePayload(
            organization_size="startup",
            industries=["it_saas"],
            departments=["product_dev_it", "cs"],
            primary_goals=["release_notes", "integrated_search"],
            data_sensitivity=["customer_info"],
        )
    )

    assert recommendation["recommended_package"] == "Patch Note Team"
    assert any(item["id"] == "product_dev_it" for item in recommendation["agent_packs"])
    assert any(item["id"] == "release_notes" for item in recommendation["templates"])
    assert recommendation["llm_task_routes"]["memory_summary"]["route"] == "local"


def test_initial_setup_prompt_includes_profile_and_market_positioning() -> None:
    prompt = render(
        "office/initial_office_setup.md.j2",
        intent="initial_office_setup",
        message="릴리즈 노트 중심으로 조립",
        file_blocks="(업로드 파일 없음)",
        company_profile={"organization_size": "startup", "industries": ["it_saas"]},
        market_positioning="초기 집중 기능은 AI 회의록, 액션아이템 추출, 팀 패치 노트입니다.",
    )

    assert "workspace_profile" in prompt
    assert "it_saas" in prompt
    assert "팀 패치 노트" in prompt
