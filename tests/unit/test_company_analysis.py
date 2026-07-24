"""Tests for the batched company-analysis engine."""

from __future__ import annotations

import json
from pathlib import Path

from negotium.app.company_analysis import analyze_company_documents
from negotium.app.initial_setup import ParsedSetupFile
from negotium.archive.company_knowledge import CompanyKnowledgeStore


def _make_file(tmp_path: Path, name: str, text: str) -> ParsedSetupFile:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return ParsedSetupFile(path=str(path), filename=name, kind="txt", text=text)


def _profile_payload() -> dict[str, object]:
    return {
        "company_name": "든든식품",
        "organization": "반찬을 제조해 마트에 납품하는 식품 제조 회사로 보입니다.",
        "departments": "생산팀, 영업팀",
        "roles": "생산팀장",
        "key_workflows": "발주 → 생산 → 품질검사 → 납품",
        "sensitive_policy": "급여 정보는 로컬에서만 처리",
        "questions": ["회사 이름이 정확한가요?"],
    }


async def test_analysis_summarizes_then_synthesizes(tmp_path: Path) -> None:
    files = [
        _make_file(tmp_path, "생산일지.txt", "1라인 진미채볶음 배합 3회전"),
        _make_file(tmp_path, "납품처.txt", "한마트 성남점 주 3회 납품"),
    ]
    store = CompanyKnowledgeStore(tmp_path / "archive")
    calls: list[str] = []

    async def complete(prompt: str, max_tokens: int) -> str:
        calls.append(prompt)
        if "문서 요약:" in prompt:
            return json.dumps(_profile_payload(), ensure_ascii=False)
        return json.dumps(
            {item.path: f"{item.filename} 요약" for item in files}, ensure_ascii=False
        )

    result = await analyze_company_documents(files, store=store, complete=complete)
    assert result.summarized_files == 2
    assert result.cached_files == 0
    assert result.profile["organization"].startswith("반찬을 제조해")
    assert result.profile["questions"] == ["회사 이름이 정확한가요?"]
    assert len(calls) == 2  # one batch + one synthesis
    assert store.company_profile()["company_name"] == "든든식품"


async def test_analysis_reuses_cached_summaries(tmp_path: Path) -> None:
    files = [_make_file(tmp_path, "회의록.txt", "주간회의 내용")]
    store = CompanyKnowledgeStore(tmp_path / "archive")
    call_count = 0

    async def complete(prompt: str, max_tokens: int) -> str:
        nonlocal call_count
        call_count += 1
        if "문서 요약:" in prompt:
            return json.dumps(_profile_payload(), ensure_ascii=False)
        return json.dumps({files[0].path: "회의록 요약"}, ensure_ascii=False)

    await analyze_company_documents(files, store=store, complete=complete)
    first_run_calls = call_count
    result = await analyze_company_documents(files, store=store, complete=complete)
    assert first_run_calls == 2
    assert call_count == 3  # second run: synthesis only, no batch call
    assert result.cached_files == 1
    assert result.summarized_files == 0


async def test_analysis_survives_unparseable_batch(tmp_path: Path) -> None:
    files = [_make_file(tmp_path, "메모.txt", "내용")]
    store = CompanyKnowledgeStore(tmp_path / "archive")

    async def complete(prompt: str, max_tokens: int) -> str:
        return "죄송하지만 JSON이 아닙니다"

    result = await analyze_company_documents(files, store=store, complete=complete)
    assert result.failed_batches == 1
    assert result.profile == {}
    assert result.notes


async def test_analysis_defers_batches_over_cap(tmp_path: Path) -> None:
    files = [_make_file(tmp_path, f"문서{i}.txt", f"내용 {i}") for i in range(6)]
    store = CompanyKnowledgeStore(tmp_path / "archive")

    async def complete(prompt: str, max_tokens: int) -> str:
        if "문서 요약:" in prompt:
            return json.dumps(_profile_payload(), ensure_ascii=False)
        return json.dumps(
            {item.path: "요약" for item in files if item.path in prompt}, ensure_ascii=False
        )

    result = await analyze_company_documents(
        files, store=store, complete=complete, batch_size=2, max_batches=2
    )
    assert result.summarized_files == 4
    assert result.deferred_files == 2
    assert any("이어서" in note for note in result.notes)
