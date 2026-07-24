"""Unit tests for MCP patch/agent tools."""

from __future__ import annotations

from pathlib import Path

from negotium.app.container import Container
from negotium.app.services.mcp_hub_service import call_tool
from negotium.app.settings import Settings


def test_agent_generate_plan_tool(tmp_path: Path) -> None:
    container = Container.build(
        Settings(env="test", archive_dir=tmp_path / "archive", workspace_dir=tmp_path / "work")
    )
    result = call_tool(
        container,
        "agent.generate_plan",
        {"objective": "주간 보고서 정리", "title": "주간 보고"},
    )
    assert result.result["ok"] is True
    assert result.result["plan"]["objective"] == "주간 보고서 정리"
    assert len(result.result["plan"]["steps"]) >= 2


def test_patch_create_run_tool(tmp_path: Path) -> None:
    container = Container.build(
        Settings(env="test", archive_dir=tmp_path / "archive", workspace_dir=tmp_path / "work")
    )
    result = call_tool(
        container,
        "patch.create_run",
        {"request": "로그인 버튼 문구 수정", "repo_id": "local"},
    )
    assert result.result["ok"] is True
    assert result.result["patch_run"]["request"] == "로그인 버튼 문구 수정"


def test_patch_apply_diff_defaults_to_dry_policy_check(tmp_path: Path) -> None:
    container = Container.build(
        Settings(env="test", archive_dir=tmp_path / "archive", workspace_dir=tmp_path / "work")
    )
    created = call_tool(
        container,
        "patch.create_run",
        {"request": "테스트 패치", "repo_id": "local"},
    )
    run_id = created.result["patch_run"]["id"]
    result = call_tool(container, "patch.apply_diff", {"patch_run_id": run_id})
    assert result.result["ok"] is True
    assert result.result["apply"] is False


def test_hf_recommended_and_set_local_model_tools(tmp_path: Path) -> None:
    container = Container.build(
        Settings(env="test", archive_dir=tmp_path / "archive", workspace_dir=tmp_path / "work")
    )
    recommended = call_tool(container, "hf.list_recommended_models", {})
    assert recommended.result["ok"] is True
    assert recommended.required_permission == "work:read"

    updated = call_tool(container, "hf.set_local_model", {"model_id": "Qwen/Qwen3-8B"})
    assert updated.result["local_model"] == "Qwen/Qwen3-8B"
    assert container.llm_runtime.read().local_model == "Qwen/Qwen3-8B"


def test_public_reference_capture_search_and_summary(tmp_path: Path) -> None:
    container = Container.build(
        Settings(env="test", archive_dir=tmp_path / "archive", workspace_dir=tmp_path / "work")
    )
    captured = call_tool(
        container,
        "public_reference.capture_case",
        {
            "title": "제조업 문서 자동화",
            "industry": "manufacturing",
            "department": "quality",
            "organization_size": "mid_market",
            "summary": "품질팀 승인 문서 자동화 사례",
            "content": "검수 기록과 승인 문서를 자동으로 요약합니다.",
        },
    )
    assert captured.result["ok"] is True

    searched = call_tool(container, "public_reference.search_cases", {"query": "품질팀 자동화"})
    assert len(searched.result["cases"]) == 1
    summarized = call_tool(container, "public_reference.summarize_case", {"query": "제조업"})
    assert summarized.result["summaries"][0]["title"] == "제조업 문서 자동화"
