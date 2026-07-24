"""Batched (map-reduce) company analysis over scanned documents.

One giant prompt asking a reasoning model for a huge JSON blob fails in
practice: the hidden reasoning eats the whole token budget and the body comes
back empty. Instead we make many small calls:

1. map    — documents go to the LLM in small batches; each call returns a short
            factual summary per file (JSON keyed by path).
2. cache  — summaries are stored with an mtime/size fingerprint, so a re-run
            (or a weekly report later) only pays for changed files.
3. reduce — one final small call turns the summaries into the company profile
            (what the company does, departments, workflows, open questions).

Every LLM interaction goes through a caller-provided ``complete`` coroutine so
this module stays independent of provider wiring and is trivially testable.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from negotium.app.initial_setup import ParsedSetupFile
from negotium.archive.company_knowledge import CompanyKnowledgeStore

CompleteFn = Callable[[str, int], Awaitable[str]]

BATCH_SIZE = 8
BATCH_MAX_TOKENS = 6000
SYNTHESIS_MAX_TOKENS = 8000
MAX_BATCHES_PER_RUN = 40


@dataclass
class CompanyAnalysis:
    profile: dict[str, Any] = field(default_factory=dict)
    summarized_files: int = 0
    cached_files: int = 0
    failed_batches: int = 0
    deferred_files: int = 0
    notes: list[str] = field(default_factory=list)


def _batch_prompt(files: list[ParsedSetupFile]) -> str:
    blocks = []
    for item in files:
        text = item.text[:2500]
        rows = "\n".join(
            "- " + ", ".join(f"{k}={v}" for k, v in row.items() if v) for row in item.rows[:15]
        )
        blocks.append(f"### {item.path}\n{text}\n{rows}".strip())
    joined = "\n\n".join(blocks)
    return (
        "다음은 한 회사의 내부 문서들입니다. 각 문서에서 회사에 대해 알 수 있는 사실만 짧게 요약하세요.\n"
        "- 무엇을 만들거나 파는지, 누구와 거래하는지, 어떤 업무/부서/직책이 보이는지 위주로.\n"
        "- 추측하지 말고 문서에 있는 내용만 쓰세요.\n"
        '- JSON 객체로만 답하세요. 형식: {"<문서 경로>": "<요약 2~3문장>", ...}\n\n'
        f"{joined}"
    )


def _synthesis_prompt(summaries: dict[str, str], extra_request: str) -> str:
    lines = "\n".join(f"- {path}: {summary}" for path, summary in summaries.items())
    extra = f"\n추가 요청: {extra_request}\n" if extra_request.strip() else ""
    return (
        "아래는 한 회사의 내부 문서들을 요약한 것입니다. 이것만 근거로 이 회사를 파악하세요.\n"
        "JSON 객체로만 답하세요. 형식:\n"
        "{\n"
        '  "company_name": "문서에서 찾은 회사 이름 (없으면 빈 문자열)",\n'
        '  "organization": "이 회사는 ~을 하는 회사로 보입니다 형태로 2~3문장. 무엇을 만들어 누구에게 파는지 구체적으로. 근거 문서 이름 언급",\n'
        '  "departments": "문서에 실제로 등장한 부서를 쉼표로",\n'
        '  "roles": "문서에 등장한 직책/담당자를 쉼표로",\n'
        '  "key_workflows": "문서에서 확인되는 반복 업무 흐름 (발주, 생산, 검사, 납품, 결재, 회의 등)",\n'
        '  "sensitive_policy": "문서에서 발견한 민감정보 유형과 취급 원칙",\n'
        '  "questions": ["문서만으로 확신할 수 없어 관리자 확인이 필요한 것"]\n'
        "}\n"
        f"{extra}\n"
        f"문서 요약:\n{lines}"
    )


def _parse_json_object(raw: str) -> dict[str, Any] | None:
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


def _summary_for(parsed: dict[str, Any], item: ParsedSetupFile) -> str | None:
    """Find this file's summary even when the LLM shortened the path key."""

    for key in (item.path, item.filename):
        value = parsed.get(key)
        if value:
            return str(value)
    basename = Path(item.path).name
    for key, value in parsed.items():
        if not value:
            continue
        key_name = Path(str(key)).name
        if key_name == basename or key_name.endswith(item.filename):
            return str(value)
        if item.path.endswith(str(key)) or basename.endswith(key_name):
            return str(value)
    return None


def _fingerprint(item: ParsedSetupFile) -> tuple[float, int]:
    try:
        stat = Path(item.path).stat()
        return (stat.st_mtime, stat.st_size)
    except OSError:
        return (0.0, len(item.text))


async def analyze_company_documents(
    files: list[ParsedSetupFile],
    *,
    store: CompanyKnowledgeStore,
    complete: CompleteFn,
    extra_request: str = "",
    batch_size: int = BATCH_SIZE,
    max_batches: int = MAX_BATCHES_PER_RUN,
) -> CompanyAnalysis:
    """Summarize documents in small batches (cache-aware), then synthesize."""

    result = CompanyAnalysis()
    summaries: dict[str, str] = {}
    pending: list[ParsedSetupFile] = []

    for item in files:
        mtime, size = _fingerprint(item)
        cached = store.cached_summary(item.path, mtime=mtime, size=size)
        if cached:
            summaries[item.path] = cached
            result.cached_files += 1
        else:
            pending.append(item)

    batches = [pending[i : i + batch_size] for i in range(0, len(pending), batch_size)]
    if len(batches) > max_batches:
        deferred = batches[max_batches:]
        result.deferred_files = sum(len(batch) for batch in deferred)
        batches = batches[:max_batches]
        result.notes.append(
            f"문서가 많아 이번 실행에서는 일부만 읽었습니다. 남은 {result.deferred_files}개는 "
            "다음 분석 때 이어서 읽습니다."
        )

    for batch in batches:
        raw = await complete(_batch_prompt(batch), BATCH_MAX_TOKENS)
        parsed = _parse_json_object(raw)
        if parsed is None:
            result.failed_batches += 1
            continue
        entries: dict[str, dict[str, Any]] = {}
        for item in batch:
            summary = _summary_for(parsed, item)
            if not summary:
                continue
            mtime, size = _fingerprint(item)
            summaries[item.path] = str(summary)
            entries[item.path] = {"mtime": mtime, "size": size, "summary": str(summary)}
            result.summarized_files += 1
        if entries:
            # Persist after every batch so an interrupted run resumes for free.
            store.store_summaries(entries)

    if not summaries:
        result.notes.append("문서에서 요약을 만들지 못했습니다. 폴더 선택을 확인해 주세요.")
        return result

    raw = await complete(_synthesis_prompt(summaries, extra_request), SYNTHESIS_MAX_TOKENS)
    profile = _parse_json_object(raw)
    if profile is None:
        result.notes.append("회사 종합 분석 응답을 해석하지 못했습니다. 다시 시도해 주세요.")
        return result

    questions = profile.pop("questions", [])
    result.profile = {key: str(value) for key, value in profile.items() if value is not None}
    if isinstance(questions, list):
        result.profile["questions"] = [str(item) for item in questions if item]
    store.store_profile(result.profile)
    if result.failed_batches:
        result.notes.append(
            f"문서 묶음 {result.failed_batches}개는 이번에 해석하지 못해 건너뛰었습니다."
        )
    return result


REPORT_MAX_TOKENS = 8000


def _report_prompt(
    profile: dict[str, Any], summaries: dict[str, str], changed_paths: list[str]
) -> str:
    lines = "\n".join(f"- {path}: {summary}" for path, summary in summaries.items())
    changed = "\n".join(f"- {path}" for path in changed_paths) or "(이번에 바뀐 문서 없음)"
    organization = str(profile.get("organization") or "")
    return (
        "당신은 이 회사의 경영 보좌 AI입니다. 아래 문서 요약을 근거로 CEO가 읽을 현황 리포트를 만드세요.\n"
        f"회사 소개: {organization}\n\n"
        "JSON 객체로만 답하세요. 각 항목은 짧은 한국어 문장 배열이며, 근거 문서가 있는 내용만 씁니다.\n"
        "{\n"
        '  "progressed": ["진행되거나 완료된 일"],\n'
        '  "attention": ["문제, 지연, 재고 부족, 품질 이슈 등 신경 쓸 일"],\n'
        '  "quiet": ["이전 문서에는 있었는데 최근 소식이 없는 일"],\n'
        '  "people": ["부서별 인력 상황, 채용이 필요해 보이는 신호"],\n'
        '  "money": ["비용, 단가, 매출, 자금 관련 언급"]\n'
        "}\n\n"
        f"이번에 새로 생기거나 바뀐 문서:\n{changed}\n\n"
        f"전체 문서 요약:\n{lines}"
    )


async def generate_company_report(
    files: list[ParsedSetupFile],
    *,
    store: CompanyKnowledgeStore,
    complete: CompleteFn,
    batch_size: int = BATCH_SIZE,
    max_batches: int = MAX_BATCHES_PER_RUN,
) -> dict[str, Any] | None:
    """Build a CEO status report from cached + freshly changed summaries."""

    summaries: dict[str, str] = {}
    changed: list[str] = []
    pending: list[ParsedSetupFile] = []
    for item in files:
        mtime, size = _fingerprint(item)
        cached = store.cached_summary(item.path, mtime=mtime, size=size)
        if cached:
            summaries[item.path] = cached
        else:
            pending.append(item)

    batches = [pending[i : i + batch_size] for i in range(0, len(pending), batch_size)]
    for batch in batches[:max_batches]:
        raw = await complete(_batch_prompt(batch), BATCH_MAX_TOKENS)
        parsed = _parse_json_object(raw)
        if parsed is None:
            continue
        entries: dict[str, dict[str, Any]] = {}
        for item in batch:
            summary = _summary_for(parsed, item)
            if not summary:
                continue
            mtime, size = _fingerprint(item)
            summaries[item.path] = summary
            changed.append(item.path)
            entries[item.path] = {"mtime": mtime, "size": size, "summary": summary}
        if entries:
            store.store_summaries(entries)

    if not summaries:
        return None
    raw = await complete(
        _report_prompt(store.company_profile(), summaries, changed), REPORT_MAX_TOKENS
    )
    parsed_report = _parse_json_object(raw)
    if parsed_report is None:
        return None
    report: dict[str, Any] = {
        key: [str(item) for item in value] if isinstance(value, list) else []
        for key, value in parsed_report.items()
        if key in {"progressed", "attention", "quiet", "people", "money"}
    }
    report["read_files"] = len(summaries)
    report["changed_files"] = len(changed)
    return report
