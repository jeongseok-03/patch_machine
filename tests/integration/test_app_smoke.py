"""Smoke test: FastAPI app factory + /health returns bus metrics."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from negotium.adapters.llm.fake_adapter import FakeLlmProvider, ScriptedResponse
from negotium.app.container import Container
from negotium.app.main import create_app
from negotium.app.settings import Settings
from negotium.archive.access_control import UserRecord
from negotium.archive.llm_runtime import LlmRuntimeConfig
from negotium.archive.operations_memory import OperationsMemory
from negotium.archive.patch_runs import PatchRun


def test_health_endpoint_reports_queue_state() -> None:
    container = Container.build()
    app = create_app(container)
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["queue_capacity"] == container.bus.capacity
        assert "metrics" in payload


def test_contributor_site_routes_are_served(tmp_path: Path) -> None:
    container = Container.build(
        Settings(
            env="test", archive_dir=tmp_path / "archive", workspace_dir=tmp_path / "workspaces"
        )
    )
    app = create_app(container)
    with TestClient(app) as client:
        home = client.get("/")
        join = client.get("/join")
        operations = client.get("/operations")
        styles = client.get("/site.css")

    assert home.status_code == 200
    assert "네고티움은 외부 기여와 함께 더 똑똑해집니다" in home.text
    assert join.status_code == 200
    assert "좋은 제보 하나가 자동 패치의 출발점입니다" in join.text
    assert operations.status_code == 200
    assert "네고티움이 지금 운영할 회사를 기억하게 합니다" in operations.text
    assert styles.status_code == 200
    assert "text/css" in styles.headers["content-type"]


def test_operations_memory_can_be_saved_from_ui(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    container = Container.build(
        Settings(env="test", archive_dir=archive_dir, workspace_dir=tmp_path / "workspaces")
    )
    app = create_app(container)

    with TestClient(app) as client:
        response = client.post(
            "/operations",
            data={
                "company_name": "Acme Retail",
                "office_project": "환불 자동화",
                "active_plan": "중복 환불 방지 계획",
            },
            follow_redirects=False,
        )
        saved = client.get("/operations")

    assert response.status_code == 303
    assert container.operations_memory.read().company_name == "Acme Retail"
    assert "Acme Retail" in saved.text
    assert (archive_dir / "operations_memory.json").exists()


def test_operations_memory_api_round_trips(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    container = Container.build(
        Settings(env="test", archive_dir=archive_dir, workspace_dir=tmp_path / "workspaces")
    )
    headers = _auth_headers(container)
    app = create_app(container)

    with TestClient(app) as client:
        empty = client.get("/api/operations-memory")
        saved = client.put(
            "/api/operations-memory",
            headers=headers,
            json={
                "company_name": "Acme Retail",
                "office_project": "오피스 운영",
                "active_plan": "프론트엔드 로컬 검증",
            },
        )
        status = client.get("/api/status")

    assert empty.status_code == 200
    assert empty.json()["company_name"] == ""
    assert saved.status_code == 200
    assert saved.json()["company_name"] == "Acme Retail"
    assert container.operations_memory.read().active_plan == "프론트엔드 로컬 검증"
    assert status.status_code == 200
    assert status.json()["operations_memory_configured"] is True


def test_llm_chat_uses_operations_memory_context(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    container = Container.build(
        Settings(env="test", archive_dir=archive_dir, workspace_dir=tmp_path / "workspaces")
    )
    fake = FakeLlmProvider(responses=[ScriptedResponse(text="청우식품 문서 자동화 상태입니다.")])
    container.llm = fake
    headers = _auth_headers(container)
    container.operations_memory.write(
        OperationsMemory(
            company_name="청우식품",
            office_project="회사 서류 자동화 시스템",
            active_plan="입력받는 디스코드 문서를 자동화한다.",
        )
    )
    app = create_app(container)

    with TestClient(app) as client:
        runtime = client.get("/api/llm/runtime")
        response = client.post(
            "/api/llm/chat",
            headers=headers,
            json={"message": "현재 업무 요약해줘", "route": "api", "provider": "fake"},
        )

    assert runtime.status_code == 200
    assert response.status_code == 200
    assert "청우식품" in response.json()["answer"]
    assert any("청우식품" in message.content for call in fake.calls for message in call)


def test_chat_replays_history_and_supports_slash_and_stream(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    container = Container.build(
        Settings(env="test", archive_dir=archive_dir, workspace_dir=tmp_path / "workspaces")
    )
    fake = FakeLlmProvider(
        responses=[
            ScriptedResponse(text="첫 번째 응답입니다."),
            ScriptedResponse(text="두 번째 응답입니다."),
            ScriptedResponse(text="<!-- negotium:format=markdown -->\n슬래시 초안 본문"),
            ScriptedResponse(text="스트리밍 응답 본문"),
        ]
    )
    container.llm = fake
    container.llm_runtime.write(
        LlmRuntimeConfig(
            default_route="api", default_provider="fake", local_enabled=True, api_enabled=True
        )
    )
    headers = _auth_headers(container)
    app = create_app(container)

    with TestClient(app) as client:
        first = client.post(
            "/api/llm/chat",
            headers=headers,
            json={"message": "내 이름은 지호야", "route": "api", "provider": "fake"},
        )
        second = client.post(
            "/api/llm/chat",
            headers=headers,
            json={"message": "방금 뭐라고 했지?", "route": "api", "provider": "fake"},
        )
        skills_help = client.post(
            "/api/llm/chat",
            headers=headers,
            json={"message": "/skills", "route": "api", "provider": "fake"},
        )
        slash_run = client.post(
            "/api/llm/chat",
            headers=headers,
            json={
                "message": "/office.document_draft title=주간보고 이번 주 업무 정리",
                "route": "api",
                "provider": "fake",
            },
        )
        stream = client.post(
            "/api/llm/chat/stream",
            headers=headers,
            json={"message": "스트리밍 테스트", "route": "api", "provider": "fake"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    # The second call must replay the first turn (user + assistant) into the prompt.
    second_call_messages = fake.calls[1]
    replayed = "\n".join(
        message.content for message in second_call_messages if isinstance(message.content, str)
    )
    assert "내 이름은 지호야" in replayed
    assert "첫 번째 응답입니다." in replayed
    assert second.json()["used_history"] >= 2

    # /skills returns help without invoking the LLM.
    assert skills_help.status_code == 200
    assert "office.document_draft" in skills_help.json()["answer"]

    # Slash command dispatches the skill and reports the result.
    assert slash_run.status_code == 200
    slash_body = slash_run.json()
    assert slash_body["skill_id"] == "office.document_draft"
    assert slash_body["skill_result"]["status"] == "succeeded"

    # Streaming endpoint emits SSE delta + done events.
    assert stream.status_code == 200
    assert "text/event-stream" in stream.headers["content-type"]
    assert "event: delta" in stream.text
    assert "event: done" in stream.text
    assert "스트리밍 응답 본문" in stream.text


def test_progress_and_integrations_degrade_without_external_config(tmp_path: Path) -> None:
    container = Container.build(
        Settings(
            env="test", archive_dir=tmp_path / "archive", workspace_dir=tmp_path / "workspaces"
        )
    )
    headers = _auth_headers(container)
    app = create_app(container)

    with TestClient(app) as client:
        progress = client.get("/api/progress")
        work_items = client.get("/api/work-items", headers=headers)
        github = client.get("/api/integrations/github")
        discord = client.get("/api/integrations/discord")

    assert progress.status_code == 200
    assert "current_status" in progress.json()["current_status_md"]
    assert work_items.status_code == 200
    assert github.status_code == 200
    assert github.json()["configured"] is False
    assert discord.status_code == 200
    assert discord.json()["configured"] is False


def test_patchops_execution_router_endpoints_shape(tmp_path: Path) -> None:
    container = Container.build(
        Settings(env="test", archive_dir=tmp_path / "archive", workspace_dir=tmp_path)
    )
    headers = _auth_headers(container)
    run = container.patch_runs.create(
        PatchRun.create(
            repo_id="local",
            request="Fix UI copy",
            approved_by="owner",
            artifacts={
                "diff_draft": """diff --git a/frontend/src/App.tsx b/frontend/src/App.tsx
--- a/frontend/src/App.tsx
+++ b/frontend/src/App.tsx
@@ -1 +1 @@
-old
+new
""",
                "pr_description": "## Summary\n- Fix copy",
            },
        )
    )
    app = create_app(container)

    with TestClient(app) as client:
        applied = client.post(
            f"/api/patch-runs/{run.id}/apply-diff",
            headers=headers,
            json={"arguments": {"apply": False}},
        )
        tested = client.post(
            f"/api/patch-runs/{run.id}/run-tests",
            headers=headers,
            json={"arguments": {"command": "python -m pytest -q", "dry_run": True}},
        )
        drafted = client.post(
            f"/api/patch-runs/{run.id}/draft-pr",
            headers=headers,
            json={"arguments": {}},
        )
        files = client.get(f"/api/patch-runs/{run.id}/files", headers=headers)
        traversal = client.get(
            f"/api/patch-runs/{run.id}/files/%2E%2E/runs/{run.id}.json", headers=headers
        )

    assert applied.status_code == 200
    assert applied.json()["execution"]["policy"]["files"] == ["frontend/src/App.tsx"]
    assert tested.status_code == 200
    assert tested.json()["test_result"]["dry_run"] is True
    assert drafted.status_code == 200
    assert drafted.json()["pr_draft"]["requires_human_approval"] is True
    assert files.status_code == 200
    assert {item["name"] for item in files.json()["files"]} <= {"plan.md"}
    assert traversal.status_code == 400
    assert container.mcp_audit.list(limit=10)


def test_patchops_plan_and_artifact_files_are_created(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("print('hello')\n", encoding="utf-8")
    container = Container.build(
        Settings(env="test", archive_dir=tmp_path / "archive", workspace_dir=workspace)
    )
    container.llm = FakeLlmProvider(
        [
            ScriptedResponse(
                text='[{"question":"수정 범위는?","priority":"high","needs_human":false}]'
            ),
            ScriptedResponse(
                text='{"goal":"문구 수정","target_files":["app.py"],"patch_steps":["app.py 수정"],"risk_level":"low","test_plan":["python -m pytest -q"],"approval_required":true}'
            ),
            ScriptedResponse(
                text='{"diff_draft":"diff --git a/app.py b/app.py\\n--- a/app.py\\n+++ b/app.py\\n@@ -1 +1 @@\\n-print(\\u0027hello\\u0027)\\n+print(\\u0027hi\\u0027)\\n","verification_commands":["python -m pytest -q"]}'
            ),
            ScriptedResponse(
                text='{"pr_description":"## Summary\\n- Update app","internal_patch_note":"# Note","customer_release_note":"Updated."}'
            ),
            ScriptedResponse(
                text='{"test_plan":["python -m pytest -q"],"test_diff_draft":"diff --git a/test_app.py b/test_app.py\\n--- /dev/null\\n+++ b/test_app.py\\n@@ -0,0 +1 @@\\n+def test_app(): pass\\n"}'
            ),
            ScriptedResponse(
                text="# 코딩 에이전트 계획서\n\n## 수정됨\n- 저장 API와 AI 수정 API 확인"
            ),
        ]
    )
    headers = _auth_headers(container)
    app = create_app(container)

    with TestClient(app) as client:
        created = client.post(
            "/api/patch-runs",
            headers=headers,
            json={
                "repo_id": "local",
                "request": "app.py 문구 수정",
                "autonomy_level": "L1",
                "privacy_mode": "hybrid_redacted",
                "target_branch": "main",
            },
        )
        run_id = created.json()["patch_run"]["id"]
        analyzed = client.post(f"/api/patch-runs/{run_id}/analyze", headers=headers)
        drafted = client.post(f"/api/patch-runs/{run_id}/draft-diff", headers=headers)
        files = client.get(f"/api/patch-runs/{run_id}/files", headers=headers)
        plan = client.get(f"/api/patch-runs/{run_id}/files/plan.md", headers=headers)
        saved = client.put(
            f"/api/patch-runs/{run_id}/plan-md",
            headers=headers,
            json={"content": "# 직접 수정한 plan.md\n"},
        )
        revised = client.post(
            f"/api/patch-runs/{run_id}/plan-md/revise",
            headers=headers,
            json={
                "instruction": "체크리스트를 추가해줘",
                "current_content": "# 직접 수정한 plan.md\n",
            },
        )
        memory = client.get("/api/memory/permanent/search?q=PatchOps%20plan", headers=headers)
        docs = client.get("/api/archive/document-index?q=PatchOps&limit=20", headers=headers)

    assert analyzed.status_code == 200
    assert drafted.status_code == 200
    names = {item["name"] for item in files.json()["files"]}
    assert names == {"plan.md"}
    assert "코딩 에이전트 계획서" in plan.json()["file"]["content"]
    assert "## Code Change Draft" in plan.json()["file"]["content"]
    assert "## Test Draft" in plan.json()["file"]["content"]
    assert "## PR Draft" in plan.json()["file"]["content"]
    assert saved.status_code == 200
    assert saved.json()["file"]["content"].startswith("# 직접 수정한 plan.md")
    assert revised.status_code == 200
    assert "## 수정됨" in revised.json()["file"]["content"]
    assert any("patch_ops/workspaces" in source["path"] for source in memory.json()["sources"])
    assert any(item["kind"] == "AI 개발 도우미" for item in docs.json()["documents"])


def test_context_firewall_security_api_redacts_and_audits(tmp_path: Path) -> None:
    container = Container.build(
        Settings(env="test", archive_dir=tmp_path / "archive", workspace_dir=tmp_path)
    )
    headers = _auth_headers(container)
    app = create_app(container)

    with TestClient(app) as client:
        sanitized = client.post(
            "/api/security/context-firewall/sanitize",
            headers=headers,
            json={
                "destination": "frontier_llm",
                "task_type": "manual_security_test",
                "content": "token=secret owner@example.com postgres://admin:pass@10.0.0.2:5432/prod",
            },
        )
        audit = client.get("/api/security/context-firewall/audit", headers=headers)
        policy = client.get("/api/security/context-firewall/policy", headers=headers)

    assert sanitized.status_code == 200
    result = sanitized.json()["result"]
    assert result["decision"] == "block"
    assert "owner@example.com" not in str(result["sanitized"])
    assert audit.status_code == 200
    assert audit.json()["count"] >= 1
    assert policy.status_code == 200
    assert ".env*" in policy.json()["policy"]["blocked_paths"]


def test_ai_office_generation_endpoints_write_archive_docs(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    container = Container.build(
        Settings(env="test", archive_dir=archive_dir, workspace_dir=tmp_path / "workspaces")
    )
    container.llm = FakeLlmProvider(
        responses=[
            ScriptedResponse(text="## 직무 요구사항\n- 문서 자동화 역량"),
            ScriptedResponse(text="## 인수인계\n- 현재 업무 요약"),
            ScriptedResponse(text="## 회의록\n- 결정사항"),
        ]
    )
    container.llm_runtime.write(
        LlmRuntimeConfig(
            default_route="api", default_provider="fake", local_enabled=True, api_enabled=True
        )
    )
    headers = _auth_headers(container)
    container.operations_memory.write(
        OperationsMemory(
            company_name="청우식품",
            office_project="회사 서류 자동화 시스템",
            organization="대표-관리팀",
            office_tools="Discord, Excel",
            sensitive_policy="민감 문서는 로컬 LLM 우선",
        )
    )
    app = create_app(container)

    with TestClient(app) as client:
        hiring = client.post(
            "/api/hr/role-requirements",
            headers=headers,
            json={
                "role_title": "문서 자동화 담당자",
                "business_need": "Discord 문서 자동화",
                "priority": "high",
            },
        )
        handover = client.post(
            "/api/handover/brief",
            headers=headers,
            json={
                "work_title": "Discord 문서 접수 자동화",
                "outgoing_owner": "A",
                "incoming_owner": "B",
                "notes": "분류 규칙 확인 필요",
            },
        )
        document = client.post(
            "/api/documents/generate",
            headers=headers,
            json={
                "document_type": "meeting_minutes",
                "title": "자동화 회의",
                "source_text": "문서 자동화를 도입하기로 함",
                "audience": "대표",
            },
        )

    assert hiring.status_code == 200
    assert hiring.json()["path"].startswith("hr/interview_kits/")
    assert handover.status_code == 200
    assert handover.json()["path"].startswith("handover/")
    assert document.status_code == 200
    assert document.json()["path"].startswith("documents/")
    assert (archive_dir / hiring.json()["path"]).exists()


def test_office_document_generation_falls_back_when_llm_returns_empty(tmp_path: Path) -> None:
    container = Container.build(
        Settings(
            env="test", archive_dir=tmp_path / "archive", workspace_dir=tmp_path / "workspaces"
        )
    )
    container.llm = FakeLlmProvider(responses=[ScriptedResponse(text="", completion_tokens=1600)])
    container.llm_runtime.write(
        LlmRuntimeConfig(
            default_route="api", default_provider="fake", local_enabled=True, api_enabled=True
        )
    )
    headers = _auth_headers(container)
    app = create_app(container)

    with TestClient(app) as client:
        response = client.post(
            "/api/documents/generate",
            headers=headers,
            json={
                "document_type": "meeting_minutes",
                "title": "5월 프로젝트 진행 계획 회의",
                "source_text": "네고티움 원문 개발 문서 자동화",
                "audience": "담당자",
            },
        )

    assert response.status_code == 200
    markdown = response.json()["markdown"]
    assert "LLM 응답 없음" not in markdown
    assert "로컬 fallback 초안" in markdown
    assert "네고티움 원문 개발 문서 자동화" in markdown


def test_document_generation_honors_format_directive_and_attachment(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    container = Container.build(
        Settings(env="test", archive_dir=archive_dir, workspace_dir=tmp_path / "workspaces")
    )
    container.llm = FakeLlmProvider(
        responses=[ScriptedResponse(text="<!-- negotium:format=csv -->\nname,role\nA,dev")]
    )
    container.llm_runtime.write(
        LlmRuntimeConfig(
            default_route="api", default_provider="fake", local_enabled=True, api_enabled=True
        )
    )
    headers = _auth_headers(container)
    app = create_app(container)

    with TestClient(app) as client:
        upload = client.post(
            "/api/uploads",
            headers=headers,
            files={"file": ("notes.md", b"# memo\nsome content", "text/markdown")},
            data={"work_title": "attachment test"},
        )
        assert upload.status_code == 200
        upload_id = upload.json()["upload"]["id"]

        response = client.post(
            "/api/documents/generate",
            headers=headers,
            json={
                "document_type": "report_draft",
                "title": "표 형식 보고",
                "source_text": "표로 정리",
                "audience": "관리팀",
                "attachment_ids": [upload_id],
                "output_format": "auto",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["output_format"] == "csv"
    assert body["path"].endswith(".csv")
    assert "name,role" in body["markdown"]
    assert (archive_dir / body["path"]).exists()


def test_skills_endpoints_list_and_run(tmp_path: Path) -> None:
    container = Container.build(
        Settings(
            env="test", archive_dir=tmp_path / "archive", workspace_dir=tmp_path / "workspaces"
        )
    )
    container.llm = FakeLlmProvider(
        responses=[ScriptedResponse(text="<!-- negotium:format=markdown -->\n초안 본문")]
    )
    container.llm_runtime.write(
        LlmRuntimeConfig(
            default_route="api", default_provider="fake", local_enabled=True, api_enabled=True
        )
    )
    headers = _auth_headers(container)
    app = create_app(container)

    with TestClient(app) as client:
        listing = client.get("/api/skills", headers=headers)
        assert listing.status_code == 200
        skill_ids = {item["id"] for item in listing.json()["skills"]}
        assert "office.document_draft" in skill_ids

        run = client.post(
            "/api/skills/office.document_draft/run",
            headers=headers,
            json={"inputs": {"title": "주간 보고", "source_text": "이번 주 진행"}},
        )
        assert run.status_code == 200
        result = run.json()["result"]
        assert result["status"] == "succeeded"
        assert result["output_path"]

        missing = client.post(
            "/api/skills/does.not.exist/run", headers=headers, json={"inputs": {}}
        )
        assert missing.status_code == 404


def test_work_memory_architecture_and_schedule_endpoints(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    container = Container.build(
        Settings(env="test", archive_dir=archive_dir, workspace_dir=tmp_path / "workspaces")
    )
    container.llm = FakeLlmProvider(
        responses=[
            ScriptedResponse(text="## 업무 아키텍처\n- 접수\n- 분류"),
            ScriptedResponse(text="| 담당자 | 업무 |\n| 관리팀 | 검토 |"),
        ]
    )
    container.llm_runtime.write(
        LlmRuntimeConfig(
            default_route="api", default_provider="fake", local_enabled=True, api_enabled=True
        )
    )
    headers = _auth_headers(container)
    app = create_app(container)

    with TestClient(app) as client:
        memory = client.put(
            "/api/work-memory",
            headers=headers,
            json={"goals": "문서 자동화", "current_focus": "계약서 분류"},
        )
        architecture = client.post(
            "/api/work-architecture/generate",
            headers=headers,
            json={"objective": "계약서 접수 자동화", "scope": "관리팀", "participants": "관리팀"},
        )
        created = client.post(
            "/api/work-schedule/items",
            headers=headers,
            json={"title": "계약서 샘플 수집", "owner_name": "관리팀", "priority": "high"},
        )
        item_id = created.json()["item"]["id"]
        updated = client.put(
            f"/api/work-schedule/items/{item_id}",
            headers=headers,
            json={"title": "계약서 샘플 수집", "owner_name": "관리팀", "status": "in_progress"},
        )
        generated = client.post(
            "/api/work-schedule/generate",
            headers=headers,
            json={"objective": "계약서 접수 자동화", "participants": "관리팀"},
        )
        deleted = client.delete(f"/api/work-schedule/items/{item_id}", headers=headers)

    assert memory.status_code == 200
    assert memory.json()["goals"] == "문서 자동화"
    assert architecture.status_code == 200
    assert architecture.json()["path"].startswith("work_architecture/")
    assert (archive_dir / architecture.json()["path"]).exists()
    assert updated.json()["item"]["status"] == "in_progress"
    assert generated.status_code == 200
    assert deleted.json()["ok"] is True


def test_memory_redesign_endpoints_record_refresh_and_approve(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    container = Container.build(
        Settings(env="test", archive_dir=archive_dir, workspace_dir=tmp_path / "workspaces")
    )
    container.llm = FakeLlmProvider(
        responses=[
            ScriptedResponse(text="채팅 응답"),
            ScriptedResponse(text="- fact\n- decision"),
            ScriptedResponse(text="- compressed fact"),
        ]
    )
    container.llm_runtime.write(
        LlmRuntimeConfig(
            default_route="api", default_provider="fake", local_enabled=True, api_enabled=True
        )
    )
    headers = _auth_headers(container)
    app = create_app(container)

    with TestClient(app) as client:
        chat = client.post(
            "/api/llm/chat",
            headers=headers,
            json={"message": "대화 기록 테스트", "route": "api", "provider": "fake"},
        )
        conversations = client.get("/api/memory/conversations", headers=headers)
        permanent = client.get("/api/memory/permanent/search?q=대화", headers=headers)
        volatile = client.post(
            "/api/memory/volatile/refresh",
            headers=headers,
            json={"scope": "user", "key": "owner", "query": "대화", "source_limit": 5},
        )
        compressed = client.post(
            "/api/memory/context/compress",
            headers=headers,
            json={
                "scope": "user",
                "key": "owner",
                "query": "대화",
                "token_budget": 1000,
                "source_limit": 5,
            },
        )
        proposal = client.post(
            "/api/memory/schema/propose",
            headers=headers,
            json={
                "proposal": {
                    "type_id": "decision",
                    "display_name": "결정 이력",
                    "fields": [{"name": "summary", "type": "text"}],
                }
            },
        )
        approved_schema = client.post(
            f"/api/memory/schema/proposals/{proposal.json()['proposal']['id']}/approve",
            headers=headers,
        )
        deletion = client.post(
            "/api/memory/deletion-requests",
            headers=headers,
            json={
                "target_type": "conversation",
                "target_id": conversations.json()["records"][0]["id"],
                "summary": "테스트 대화",
                "source_path": "conversations/test.jsonl",
                "reason": "테스트",
            },
        )
        approved_delete = client.post(
            f"/api/memory/deletion-requests/{deletion.json()['request']['id']}/approve",
            headers=headers,
        )
        plan = client.post(
            "/api/agent/plans/generate",
            headers=headers,
            json={"objective": "메모리 기반 작업 분할", "mode": "approved_tasks_only"},
        )
        approved_plan = client.post(
            f"/api/agent/plans/{plan.json()['plan']['id']}/approve", headers=headers
        )

    assert chat.status_code == 200
    assert conversations.status_code == 200
    assert conversations.json()["records"][0]["role"] == "assistant"
    assert permanent.status_code == 200
    assert volatile.json()["summary"] == "- fact\n- decision"
    assert compressed.json()["context"]["source_refs"]
    assert approved_schema.json()["schemas"][0]["type_id"] == "decision"
    assert approved_delete.json()["request"]["status"] == "approved"
    assert (archive_dir / "memory" / "tombstones.jsonl").exists()
    assert approved_plan.json()["plan"]["status"] == "approved"


def test_secure_admin_and_upload_endpoints(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    container = Container.build(
        Settings(
            env="test",
            archive_dir=archive_dir,
            workspace_dir=tmp_path / "workspaces",
            secret_key="test-master-key",
        )
    )
    headers = _auth_headers(container)
    app = create_app(container)

    with TestClient(app) as client:
        denied = client.put(
            "/api/admin/api-keys/openai",
            headers={"X-NG-User": "missing"},
            json={"provider": "openai", "api_key": "sk-test-1234567890"},
        )
        saved_key = client.put(
            "/api/admin/api-keys/openai",
            headers=headers,
            json={"provider": "openai", "api_key": "sk-test-1234567890", "model": "gpt-test"},
        )
        together_models = client.get("/api/llm/providers/together/models")
        saved_together_key = client.put(
            "/api/admin/api-keys/together",
            headers=headers,
            json={
                "provider": "together",
                "api_key": "tog-test-1234567890",
                "model": "openai/gpt-oss-20b",
            },
        )
        solar_models = client.get("/api/llm/providers/solar/models")
        saved_solar_key = client.put(
            "/api/admin/api-keys/solar",
            headers=headers,
            json={
                "provider": "solar",
                "api_key": "up-test-1234567890",
                "model": "solar-open2",
            },
        )
        saved_parent_dept = client.post(
            "/api/admin/departments",
            headers=headers,
            json={"id": "eng", "name": "엔지니어링"},
        )
        saved_child_dept = client.post(
            "/api/admin/departments",
            headers=headers,
            json={"id": "backend", "name": "백엔드팀", "parent_id": "eng"},
        )
        cyclic_dept = client.post(
            "/api/admin/departments",
            headers=headers,
            json={"id": "eng", "name": "엔지니어링", "parent_id": "backend"},
        )
        saved_position = client.post(
            "/api/admin/positions",
            headers=headers,
            json={"id": "lead", "name": "팀장", "level": 80},
        )
        saved_synced_position = client.post(
            "/api/admin/positions",
            headers=headers,
            json={
                "id": "synced_lead",
                "name": "리드",
                "permissions": ["users:read"],
                "display_order": 45,
            },
        )
        saved_synced_user = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "id": "lead_user",
                "display_name": "Lead User",
                "role_id": "viewer",
                "department": "backend",
                "position_id": "synced_lead",
                "active": True,
            },
        )
        container.auth_store.create_user(
            user_id="lead_user", display_name="Lead User", password="password-5678"
        )
        lead_token = container.auth_store.authenticate("lead_user", "password-5678")
        assert lead_token is not None
        synced_headers = {"X-NG-User": f"Bearer {lead_token}"}
        scope = client.get("/api/work-schedule/assignment-scope", headers=synced_headers)
        acl = client.get("/api/admin/access-control", headers=headers)
        deleted_position = client.delete("/api/admin/positions/lead", headers=headers)
        uploaded = client.post(
            "/api/uploads",
            headers=headers,
            files={"file": ("hello.txt", b"hello", "text/plain")},
            data={"description": "demo", "tags": "office", "work_title": "test"},
        )
        uploads = client.get("/api/uploads")
        audit = client.get("/api/admin/audit-log", headers=headers)

    assert denied.status_code == 401
    assert saved_key.status_code == 200
    assert (
        next(
            provider
            for provider in saved_key.json()["providers"]
            if provider["provider"] == "openai"
        )["masked_value"]
        == "sk-t...7890"
    )
    assert together_models.status_code == 200
    assert together_models.json()["provider"] == "together"
    assert together_models.json()["source"] == "fallback"
    assert saved_together_key.status_code == 200
    assert any(
        provider["provider"] == "together" and provider["configured"]
        for provider in saved_together_key.json()["providers"]
    )
    assert solar_models.status_code == 200
    assert solar_models.json()["provider"] == "solar"
    assert solar_models.json()["source"] == "fallback"
    assert "solar-open2" in solar_models.json()["models"]
    assert saved_solar_key.status_code == 200
    assert any(
        provider["provider"] == "solar" and provider["configured"]
        for provider in saved_solar_key.json()["providers"]
    )
    assert saved_parent_dept.status_code == 200
    assert saved_child_dept.status_code == 200
    assert cyclic_dept.status_code == 400
    assert saved_position.status_code == 200
    assert "permissions" in saved_position.json()
    assert "documents:read" in saved_position.json()["permissions"]
    assert saved_synced_position.status_code == 200
    assert "permissions" in saved_synced_position.json()
    assert saved_synced_user.status_code == 200
    assert acl.status_code == 200
    assert "owner" in {user["id"] for user in acl.json()["users"]}
    acl_payload = acl.json()
    departments_by_id = {dept["id"]: dept for dept in acl_payload["departments"]}
    assert departments_by_id["backend"]["parent_id"] == "eng"
    assert "lead" in {position["id"] for position in acl_payload["positions"]}
    users_by_id = {user["id"]: user for user in acl_payload["users"]}
    assert users_by_id["lead_user"]["role_id"] == "viewer"
    assert scope.status_code == 200
    assert scope.json()["scope"] == "department"
    assert scope.json()["position_rank"] == 45
    assert "backend" in scope.json()["department_ids"]
    assert deleted_position.status_code == 200
    assert "lead" not in {position["id"] for position in deleted_position.json()["positions"]}
    assert uploaded.status_code == 200
    assert uploads.json()["uploads"][0]["filename"] == "hello.txt"
    assert audit.status_code == 200
    assert {"api_key.upsert", "upload.create"}.issubset(
        {record["action"] for record in audit.json()["records"]}
    )


def test_initial_office_setup_analyze_and_apply(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    container = Container.build(
        Settings(env="test", archive_dir=archive_dir, workspace_dir=tmp_path / "workspaces")
    )
    container.llm = FakeLlmProvider(
        responses=[
            ScriptedResponse(
                text="""{
  "operations_memory": {"company_name": "Acme", "organization": "Ops", "roles": "대표, 매니저"},
  "work_memory": {"goals": "초기 세팅"},
  "roles": [{"id": "ops_manager", "name": "운영 매니저", "level": 70, "permissions": ["work:read"]}],
  "users": [{"id": "alice", "display_name": "Alice", "title": "운영 매니저", "role_id": "ops_manager", "active": true}],
  "notes": ["parsed"],
  "warnings": [],
  "questions": [],
  "sensitive_hint": true
}""",
            ),
        ],
    )
    headers = _auth_headers(container)
    app = create_app(container)

    with TestClient(app) as client:
        uploaded = client.post(
            "/api/uploads",
            headers=headers,
            files={
                "file": (
                    "employees.csv",
                    b"name,title\nAlice,\xec\x9a\xb4\xec\x98\x81 \xeb\xa7\xa4\xeb\x8b\x88\xec\xa0\x80\n",
                    "text/csv",
                )
            },
            data={"work_title": "초기 세팅", "tags": "인사"},
        )
        upload_id = uploaded.json()["upload"]["id"]
        analyzed = client.post(
            "/api/setup/office/analyze",
            headers=headers,
            json={"message": "직원 명단을 기반으로 초기 세팅", "upload_ids": [upload_id]},
        )
        applied = client.post("/api/setup/office/apply", headers=headers, json=analyzed.json())

    assert uploaded.status_code == 200
    assert analyzed.status_code == 200
    assert analyzed.json()["sensitive_hint"] is True
    assert "로컬 에이전트 서버" in "\n".join(analyzed.json()["warnings"])
    assert applied.status_code == 200
    assert container.operations_memory.read().company_name == "Acme"
    users = {user["id"]: user for user in container.access_control.read()["users"]}
    assert users["alice"]["role_id"] == "ops_manager"


def test_hr_evaluation_context_draft_and_save(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    container = Container.build(
        Settings(env="test", archive_dir=archive_dir, workspace_dir=tmp_path / "workspaces")
    )
    container.llm = FakeLlmProvider([ScriptedResponse(text="# 인사평가 초안\n좋은 성과")])
    headers = _auth_headers(container)
    app = create_app(container)

    with TestClient(app) as client:
        client.post(
            "/api/admin/positions",
            headers=headers,
            json={"id": "dev", "name": "개발 담당", "permissions": ["documents:read"]},
        )
        client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "id": "alice",
                "display_name": "Alice",
                "role_id": "staff",
                "position_id": "dev",
                "active": True,
            },
        )
        context = client.get("/api/hr/evaluation/context?user_id=alice", headers=headers)
        draft = client.post(
            "/api/hr/evaluation/draft",
            headers=headers,
            json={"user_id": "alice", "period": "2026 Q2", "criteria": "업무 성과"},
        )
        saved = client.post(
            "/api/hr/evaluation/save",
            headers=headers,
            json={
                "user_id": "alice",
                "period": "2026 Q2",
                "draft": draft.json()["draft"],
                "final_text": "관리자 수정본",
            },
        )
        records = client.get("/api/hr/evaluation/records?user_id=alice", headers=headers)
        document_path = saved.json().get("document_path", "")
        document = client.get(
            f"/api/archive/documents?path={document_path}",
            headers=headers,
        )
        memory = client.get("/api/memory/permanent/search?q=관리자%20수정본", headers=headers)

    assert context.status_code == 200
    assert context.json()["employee"]["display_name"] == "Alice"
    assert draft.status_code == 200
    assert "# 인사평가 초안" in draft.json()["draft"]
    assert saved.status_code == 200
    assert document_path.startswith("hr/evaluations/")
    assert saved.json()["record"]["document_path"] == document_path
    assert document.status_code == 200
    assert "관리자 수정본" in document.json()["markdown"]
    assert any(source["path"] == document_path for source in memory.json()["sources"])
    assert records.json()["records"][0]["final_text"] == "관리자 수정본"


def _auth_headers(
    container: Container, *, user_id: str = "owner", password: str = "password-1234"
) -> dict[str, str]:
    container.auth_store.create_user(user_id=user_id, display_name="Local Owner", password=password)
    container.access_control.upsert_user(
        UserRecord(id=user_id, display_name="Local Owner", title="대표", role_id="owner")
    )
    token = container.auth_store.authenticate(user_id, password)
    assert token is not None
    return {"X-NG-User": f"Bearer {token}"}
