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
import re
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
    profile: dict[str, Any],
    summaries: dict[str, str],
    changed_paths: list[str],
    resolved_items: list[str] | None = None,
) -> str:
    lines = "\n".join(f"- {path}: {summary}" for path, summary in summaries.items())
    changed = "\n".join(f"- {path}" for path in changed_paths) or "(이번에 바뀐 문서 없음)"
    organization = str(profile.get("organization") or "")
    resolved = "\n".join(f"- {item}" for item in (resolved_items or []))
    resolved_block = (
        f"\n관리자가 이미 처리했거나 무시하기로 한 항목 (다시 언급하지 마세요):\n{resolved}\n"
        if resolved
        else ""
    )
    return (
        "당신은 이 회사의 경영 보좌 AI입니다. 아래 문서 요약을 근거로 관리자가 읽을 현황 리포트를 만드세요.\n"
        f"회사 소개: {organization}\n\n"
        'JSON 객체로만 답하세요. 각 항목은 {"text": "짧은 한국어 문장", "sources": ["근거 문서 경로"]} 객체이며, '
        "근거 문서가 있는 내용만 씁니다. sources에는 위 요약 목록에 있는 문서 경로를 그대로 씁니다.\n"
        "{\n"
        '  "progressed": [{"text": "진행되거나 완료된 일", "sources": ["문서 경로"]}],\n'
        '  "attention": [{"text": "문제, 지연, 재고 부족, 품질 이슈 등 신경 쓸 일", "sources": []}],\n'
        '  "quiet": [{"text": "이전 문서에는 있었는데 최근 소식이 없는 일", "sources": []}],\n'
        '  "people": [{"text": "부서별 인력 상황, 채용이 필요해 보이는 신호", "sources": []}],\n'
        '  "money": [{"text": "비용, 단가, 매출, 자금 관련 언급", "sources": []}]\n'
        "}\n"
        f"{resolved_block}\n"
        f"이번에 새로 생기거나 바뀐 문서:\n{changed}\n\n"
        f"전체 문서 요약:\n{lines}"
    )


async def generate_company_report(
    files: list[ParsedSetupFile],
    *,
    store: CompanyKnowledgeStore,
    complete: CompleteFn,
    resolved_items: list[str] | None = None,
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
        _report_prompt(store.company_profile(), summaries, changed, resolved_items),
        REPORT_MAX_TOKENS,
    )
    parsed_report = _parse_json_object(raw)
    if parsed_report is None:
        return None
    report: dict[str, Any] = {}
    for key in ("progressed", "attention", "quiet", "people", "money"):
        items: list[dict[str, Any]] = []
        value = parsed_report.get(key)
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict) and entry.get("text"):
                    sources = entry.get("sources")
                    items.append(
                        {
                            "text": str(entry["text"]),
                            "sources": [str(s) for s in sources]
                            if isinstance(sources, list)
                            else [],
                        }
                    )
                elif isinstance(entry, str) and entry.strip():
                    items.append({"text": entry.strip(), "sources": []})
        report[key] = items
    report["read_files"] = len(summaries)
    report["changed_files"] = len(changed)
    return report


ANSWER_MAX_TOKENS = 8000
DRAFT_MAX_TOKENS = 9000

ReadFileFn = Callable[[str], "ParsedSetupFile | None"]


def rank_files_by_query(summaries: dict[str, str], query: str, *, top: int = 6) -> list[str]:
    """Score cached summaries by token overlap with the query."""

    tokens = [t.lower() for t in re.split(r"[\s,./()\[\]{}:;'\"!?~·-]+", query) if len(t) >= 2]
    if not tokens:
        return []
    scored: list[tuple[int, str]] = []
    for path, summary in summaries.items():
        haystack = f"{Path(path).name} {summary}".lower()
        score = sum(haystack.count(token) for token in tokens)
        if score:
            scored.append((score, path))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [path for _, path in scored[:top]]


def _doc_blocks(files: list[ParsedSetupFile], *, per_file_chars: int = 3000) -> str:
    return "\n\n".join(f"### {item.path}\n{item.text[:per_file_chars]}" for item in files)


async def answer_company_question(
    question: str,
    *,
    store: CompanyKnowledgeStore,
    complete: CompleteFn,
    read_file: ReadFileFn,
) -> dict[str, Any] | None:
    """Answer a question from company documents, citing sources."""

    summaries = {
        path: str(entry.get("summary") or "") for path, entry in store.file_summaries().items()
    }
    ranked = rank_files_by_query(summaries, question)
    if not ranked:
        ranked = list(summaries.keys())[:4]
    files = [item for item in (read_file(path) for path in ranked) if item is not None]
    if not files:
        return None
    profile = store.company_profile()
    prompt = (
        "당신은 이 회사의 문서를 모두 알고 있는 사내 AI입니다.\n"
        f"회사 소개: {profile.get('organization', '')}\n\n"
        "아래 문서 내용만 근거로 질문에 답하세요. 문서에 없는 내용은 지어내지 말고 "
        '"문서에서 찾지 못했습니다"라고 답하세요.\n'
        'JSON 객체로만 답하세요: {"answer": "한국어 답변 (짧고 구체적으로)", "sources": ["실제 근거로 쓴 문서 경로"]}\n\n'
        f"질문: {question}\n\n"
        f"문서:\n{_doc_blocks(files)}"
    )
    parsed = _parse_json_object(await complete(prompt, ANSWER_MAX_TOKENS))
    if parsed is None or not parsed.get("answer"):
        return None
    sources = parsed.get("sources")
    return {
        "answer": str(parsed["answer"]),
        "sources": [str(s) for s in sources] if isinstance(sources, list) else [],
    }


async def draft_weekly_report(
    *,
    author: str,
    recent_files: list[ParsedSetupFile],
    store: CompanyKnowledgeStore,
    complete: CompleteFn,
) -> str | None:
    """Draft a weekly report from documents changed in the last week."""

    if not recent_files:
        return None
    profile = store.company_profile()
    prompt = (
        "당신은 사내 보고서 작성 AI입니다. 아래는 최근 7일 사이에 새로 만들어지거나 수정된 회사 문서입니다.\n"
        f"회사 소개: {profile.get('organization', '')}\n"
        f"작성자: {author}\n\n"
        "이 문서들을 근거로 주간보고 초안을 마크다운으로 작성하세요. 형식:\n"
        "# 주간보고 (작성자 이름)\n"
        "## 이번 주 진행한 일 (문서 근거가 있는 것만, 항목 끝에 근거 문서명 괄호 표기)\n"
        "## 이슈/특이사항\n"
        "## 다음 주 계획 (문서에서 예정된 일이 보이면 채우고, 없으면 '직접 채워주세요')\n"
        "문서에 없는 내용은 지어내지 마세요. 마크다운 본문만 출력하세요.\n\n"
        f"문서:\n{_doc_blocks(recent_files)}"
    )
    text = (await complete(prompt, DRAFT_MAX_TOKENS)).strip()
    return text or None


async def draft_handover(
    *,
    person: str,
    store: CompanyKnowledgeStore,
    complete: CompleteFn,
    read_file: ReadFileFn,
) -> str | None:
    """Draft a handover document for a departing person from folder knowledge."""

    summaries = {
        path: str(entry.get("summary") or "") for path, entry in store.file_summaries().items()
    }
    ranked = rank_files_by_query(summaries, person, top=8)
    if not ranked:
        ranked = list(summaries.keys())[:8]
    files = [item for item in (read_file(path) for path in ranked) if item is not None]
    if not files:
        return None
    profile = store.company_profile()
    prompt = (
        "당신은 사내 인수인계 문서 작성 AI입니다.\n"
        f"회사 소개: {profile.get('organization', '')}\n"
        f"인수인계 대상자: {person}\n\n"
        "아래 문서에서 이 사람과 관련된 업무를 찾아 인수인계 초안을 마크다운으로 작성하세요. 형식:\n"
        f"# {person} 인수인계 문서 (초안)\n"
        "## 담당 업무 요약\n## 진행 중인 일과 현재 상태\n## 관련 거래처/담당자\n"
        "## 주의사항·놓치기 쉬운 것\n## 관련 문서 위치 (경로 목록)\n"
        "문서에 근거가 없는 내용은 쓰지 말고, 관련 정보가 부족한 절에는 '문서에서 확인되지 않음 — 당사자 확인 필요'라고 적으세요.\n\n"
        f"문서:\n{_doc_blocks(files)}"
    )
    text = (await complete(prompt, DRAFT_MAX_TOKENS)).strip()
    return text or None
