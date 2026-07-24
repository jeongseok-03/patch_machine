"""Contributor-facing website routes."""

from __future__ import annotations

from html import escape
from typing import Annotated

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from negotium.archive.operations_memory import OperationsMemory, OperationsMemoryStore

_CSS = """
:root {
  color-scheme: dark;
  --bg: #0d1117;
  --panel: #151b23;
  --panel-soft: #1f2937;
  --text: #f0f6fc;
  --muted: #9aa4b2;
  --accent: #3fb950;
  --accent-strong: #56d364;
  --line: rgba(255, 255, 255, 0.12);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background:
    radial-gradient(circle at top left, rgba(63, 185, 80, 0.25), transparent 28rem),
    radial-gradient(circle at bottom right, rgba(88, 166, 255, 0.16), transparent 24rem),
    var(--bg);
  color: var(--text);
  font-family:
    ui-sans-serif,
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    sans-serif;
  line-height: 1.6;
}

a {
  color: var(--accent-strong);
}

.shell {
  width: min(1120px, calc(100% - 40px));
  margin: 0 auto;
}

.hero {
  padding: 72px 0 48px;
}

.eyebrow {
  color: var(--accent-strong);
  font-size: 0.9rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

h1 {
  max-width: 820px;
  margin: 18px 0;
  font-size: clamp(2.5rem, 8vw, 5.8rem);
  line-height: 0.95;
}

.lede {
  max-width: 720px;
  color: var(--muted);
  font-size: clamp(1.08rem, 2vw, 1.32rem);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 32px;
}

.button {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 12px 18px;
  color: var(--text);
  font-weight: 700;
  text-decoration: none;
}

.button.primary {
  border-color: transparent;
  background: var(--accent);
  color: #07120a;
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  padding-bottom: 56px;
}

.card {
  min-height: 230px;
  border: 1px solid var(--line);
  border-radius: 28px;
  background: color-mix(in srgb, var(--panel) 88%, transparent);
  padding: 26px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.22);
}

.card.featured {
  background: linear-gradient(135deg, rgba(63, 185, 80, 0.24), var(--panel));
}

.card h2 {
  margin: 0 0 12px;
  font-size: 1.35rem;
}

.card p,
.card li {
  color: var(--muted);
}

.card ul {
  margin: 0;
  padding-left: 1.1rem;
}

.steps {
  display: grid;
  gap: 12px;
  padding: 0 0 72px;
}

.step {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 18px;
  align-items: start;
  border: 1px solid var(--line);
  border-radius: 24px;
  background: rgba(13, 17, 23, 0.72);
  padding: 22px;
}

.step strong {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: var(--panel-soft);
  color: var(--accent-strong);
}

.step h2 {
  margin: 0 0 6px;
}

.step p {
  margin: 0;
  color: var(--muted);
}

form {
  display: grid;
  gap: 18px;
  padding-bottom: 72px;
}

label {
  display: grid;
  gap: 8px;
  color: var(--text);
  font-weight: 700;
}

input,
textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(13, 17, 23, 0.82);
  color: var(--text);
  font: inherit;
  padding: 14px 16px;
}

textarea {
  min-height: 140px;
  resize: vertical;
}

.notice {
  display: inline-flex;
  width: fit-content;
  border: 1px solid rgba(63, 185, 80, 0.38);
  border-radius: 999px;
  background: rgba(63, 185, 80, 0.12);
  color: var(--accent-strong);
  padding: 8px 12px;
  font-weight: 700;
}

footer {
  border-top: 1px solid var(--line);
  padding: 24px 0 40px;
  color: var(--muted);
}

@media (max-width: 820px) {
  .hero {
    padding-top: 48px;
  }

  .grid {
    grid-template-columns: 1fr;
  }

  .step {
    grid-template-columns: 1fr;
  }
}
""".strip()

_HOME_HTML = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Negotium | 외부 참여</title>
  <meta
    name="description"
    content="Negotium에 버그 리포트, 코드 리뷰, 검증 자료로 참여하는 방법을 안내합니다."
  >
  <link rel="stylesheet" href="/site.css">
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="eyebrow">Open Collaboration</div>
      <h1>네고티움은 외부 기여와 함께 더 똑똑해집니다.</h1>
      <p class="lede">
        GitHub Issue와 Discord 제보만으로 문제를 수집하고, PM / Developer / Reviewer
        에이전트가 패치 제안까지 이어가는 자동 SI/SE 실험에 참여하세요.
      </p>
      <div class="actions">
        <a class="button primary" href="/join">참여 방법 보기</a>
        <a class="button" href="/operations">운영 메모리 설정</a>
        <a class="button" href="/docs">API 문서 열기</a>
        <a class="button" href="/health">상태 확인</a>
      </div>
    </section>

    <section class="grid" aria-label="참여 영역">
      <article class="card featured">
        <h2>버그 리포트</h2>
        <p>
          재현 단계, 기대 동작, 실제 동작을 Issue나 Discord 메시지로 남기면
          네고티움이 분석 큐에 올립니다.
        </p>
      </article>
      <article class="card">
        <h2>패치 검증</h2>
        <p>
          제안된 Diff에 대해 테스트 결과, 반례, 운영상 위험을 덧붙여 자동 리뷰 품질을 높입니다.
        </p>
      </article>
      <article class="card">
        <h2>지식 축적</h2>
        <p>
          결정 근거와 컨텍스트는 Markdown archive로 남아 다음 이슈 처리에 재사용됩니다.
        </p>
      </article>
    </section>
  </main>
  <footer>
    <div class="shell">Negotium runs as a FastAPI service and is Docker-ready.</div>
  </footer>
</body>
</html>
""".strip()

_JOIN_HTML = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Negotium | 참여 방법</title>
  <meta
    name="description"
    content="Negotium 외부 참여자가 좋은 제보와 검증 피드백을 남기는 절차입니다."
  >
  <link rel="stylesheet" href="/site.css">
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="eyebrow">How to Join</div>
      <h1>좋은 제보 하나가 자동 패치의 출발점입니다.</h1>
      <p class="lede">
        지금은 GitHub Issue와 Discord를 중심으로 참여를 받습니다. 민감한 정보는 제거하고,
        재현 가능한 맥락을 남기는 것이 가장 큰 도움이 됩니다.
      </p>
      <div class="actions">
        <a class="button primary" href="/">홈으로 돌아가기</a>
        <a class="button" href="/operations">운영 메모리 설정</a>
        <a class="button" href="/docs">Webhook/API 확인</a>
      </div>
    </section>

    <section class="steps" aria-label="참여 절차">
      <article class="step">
        <strong>1</strong>
        <div>
          <h2>문제를 짧게 정의합니다</h2>
          <p>영향받는 기능, 발생 빈도, 사용자 영향도를 먼저 적어주세요.</p>
        </div>
      </article>
      <article class="step">
        <strong>2</strong>
        <div>
          <h2>재현 정보를 붙입니다</h2>
          <p>입력값, 로그 일부, 기대 결과와 실제 결과를 분리해 남기면 에이전트가 더 정확히 분석합니다.</p>
        </div>
      </article>
      <article class="step">
        <strong>3</strong>
        <div>
          <h2>패치 제안을 검토합니다</h2>
          <p>자동 생성된 Diff는 사람이 검증합니다. 테스트 결과와 반례를 댓글로 남겨주세요.</p>
        </div>
      </article>
      <article class="step">
        <strong>4</strong>
        <div>
          <h2>민감 정보는 올리지 않습니다</h2>
          <p>토큰, 고객 정보, 사내 URL은 제거하거나 마스킹한 뒤 공유해주세요.</p>
        </div>
      </article>
    </section>
  </main>
  <footer>
    <div class="shell">Public routes: <a href="/">/</a>, <a href="/join">/join</a>, <a href="/operations">/operations</a>, <a href="/health">/health</a>.</div>
  </footer>
</body>
</html>
""".strip()


def create_contributor_site_router(memory_store: OperationsMemoryStore) -> APIRouter:
    router = APIRouter(tags=["contributor-site"])

    @router.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def home() -> HTMLResponse:
        """Render the contributor landing page."""
        return HTMLResponse(_HOME_HTML)

    @router.get("/join", response_class=HTMLResponse, include_in_schema=False)
    async def join() -> HTMLResponse:
        """Render the contributor onboarding page."""
        return HTMLResponse(_JOIN_HTML)

    @router.get("/operations", response_class=HTMLResponse, include_in_schema=False)
    async def operations(saved: bool = False) -> HTMLResponse:
        """Render the operations memory form."""
        return HTMLResponse(_render_operations(memory_store.read(), saved=saved))

    @router.post("/operations", include_in_schema=False)
    async def save_operations(
        company_name: Annotated[str, Form()] = "",
        office_project: Annotated[str, Form()] = "",
        active_plan: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """Persist operations memory from the UI form."""
        memory_store.write(
            OperationsMemory(
                company_name=company_name.strip(),
                office_project=office_project.strip(),
                active_plan=active_plan.strip(),
            )
        )
        return RedirectResponse("/operations?saved=true", status_code=303)

    @router.get("/site.css", response_class=PlainTextResponse, include_in_schema=False)
    async def stylesheet() -> PlainTextResponse:
        """Serve the small built-in stylesheet for the contributor site."""
        return PlainTextResponse(_CSS, media_type="text/css")

    return router


def _render_operations(memory: OperationsMemory, *, saved: bool = False) -> str:
    saved_notice = '<p class="notice">운영 메모리를 저장했습니다.</p>' if saved else ""
    return f"""
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Negotium | 운영 메모리</title>
  <meta
    name="description"
    content="Negotium 에이전트가 참고할 운영 회사, 프로젝트, 계획 메모리를 설정합니다."
  >
  <link rel="stylesheet" href="/site.css">
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="eyebrow">Operations Memory</div>
      <h1>네고티움이 지금 운영할 회사를 기억하게 합니다.</h1>
      <p class="lede">
        이 값은 처음에는 비어 있으며, 저장 후 PM / Developer / Reviewer 에이전트 프롬프트에
        함께 전달됩니다.
      </p>
      <div class="actions">
        <a class="button" href="/">홈으로 돌아가기</a>
        <a class="button" href="/join">참여 방법 보기</a>
      </div>
    </section>

    {saved_notice}

    <form method="post" action="/operations">
      <label>
        현재 운영하려는 회사 이름
        <input
          name="company_name"
          value="{escape(memory.company_name, quote=True)}"
          placeholder="예: Acme Retail"
          autocomplete="organization"
        >
      </label>

      <label>
        오피스 프로젝트
        <input
          name="office_project"
          value="{escape(memory.office_project, quote=True)}"
          placeholder="예: 결제/환불 운영 자동화"
        >
      </label>

      <label>
        진행 중인 계획
        <textarea
          name="active_plan"
          placeholder="예: 이번 달은 고객 환불 중복 처리와 운영 로그 정리를 우선한다."
        >{escape(memory.active_plan)}</textarea>
      </label>

      <button class="button primary" type="submit">운영 메모리 저장</button>
    </form>
  </main>
  <footer>
    <div class="shell">저장 위치: <code>archive/operations_memory.json</code></div>
  </footer>
</body>
</html>
""".strip()
