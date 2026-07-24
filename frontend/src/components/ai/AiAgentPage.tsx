import { FormEvent, useEffect, useState } from 'react';

import {
  fetchCurrentUser,
  fetchLlmRuntime,
  fetchLocalLlmStatus,
  sendChatMessage,
  type AiJobStatus,
  type ChatResponse,
  type LocalLlmStatus,
  type LlmProviderName,
  type LlmRuntime,
  type LlmRuntimeRoute,
} from '../../api';
import AiJobStatusBar from '../common/AiJobStatusBar';
import PatchOpsCockpit from './PatchOpsCockpit';

const providerOptions: LlmProviderName[] = ['vllm', 'solar', 'openai', 'anthropic', 'gemini', 'together', 'fake'];

export default function AiAgentPage() {
  const [runtime, setRuntime] = useState<LlmRuntime | null>(null);
  const [localStatus, setLocalStatus] = useState<LocalLlmStatus | null>(null);
  const [message, setMessage] = useState('');
  const [route, setRoute] = useState<LlmRuntimeRoute>('local');
  const [provider, setProvider] = useState<LlmProviderName>('vllm');
  const [history, setHistory] = useState<Array<{ question: string; response: ChatResponse }>>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [chatJob, setChatJob] = useState<AiJobStatus | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);

  async function refreshRuntime() {
    try {
      const [nextRuntime, nextStatus] = await Promise.all([fetchLlmRuntime(), fetchLocalLlmStatus()]);
      setRuntime(nextRuntime);
      setLocalStatus(nextStatus);
      const chatRoute = nextRuntime.task_routes?.chat;
      setRoute(chatRoute?.route || nextRuntime.default_route);
      setProvider(chatRoute?.provider || nextRuntime.default_provider);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '런타임 로드 실패');
    }
  }

  useEffect(() => {
    void refreshRuntime();
    void fetchCurrentUser()
      .then((me) => {
        const perms = me.user?.permissions ?? [];
        setIsAdmin(perms.includes('*') || perms.includes('admin:local_llm'));
      })
      .catch(() => setIsAdmin(false));
  }, []);

  useEffect(() => {
    if (!isAdmin) return undefined;
    if (localStatus?.state !== 'loading' && localStatus?.state !== 'running') {
      return undefined;
    }
    const timer = window.setInterval(() => {
      void fetchLocalLlmStatus().then(setLocalStatus).catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [localStatus?.state, isAdmin]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!message.trim()) return;
    setBusy(true);
    setNotice(null);
    setChatJob({
      job_id: 'local-chat',
      task: 'chat',
      status: 'queued',
      actor: '',
      input_summary: message,
      used_sources: [],
      result_path: '',
      error: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    try {
      setChatJob((current) => current ? { ...current, status: 'running', updated_at: new Date().toISOString() } : current);
      const response = await sendChatMessage(message, route, provider, 'chat');
      setHistory([{ question: message, response }, ...history]);
      setChatJob(response.ai_job ?? null);
      setMessage('');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '테스트 채팅 호출 실패');
      setChatJob((current) =>
        current
          ? {
              ...current,
              status: 'failed',
              error: err instanceof Error ? err.message : '테스트 채팅 호출 실패',
              updated_at: new Date().toISOString(),
            }
          : current,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ai-agent-layout">
      <div className="panel ai-agent-hero">
        <p className="eyebrow">Coding agent brief writer</p>
        <h2>코딩 에이전트 계획서 작성</h2>
        <p className="muted">
          자동으로 코드를 적용하는 모드는 종료했습니다. 이제 저장소를 읽고 Cursor나 Claude Code가 바로 사용할 수 있는
          plan.md, 코드 변경안, 테스트 가이드, PR 초안 파일을 만드는 데 집중합니다.
        </p>
        {isAdmin ? (
          <div className="switch-row">
            <button type="button" className="secondary-button" onClick={() => void refreshRuntime()}>
              LLM 상태 새로고침
            </button>
            <span className="status-pill">Local {localStatus?.state || 'unknown'}</span>
          </div>
        ) : null}
        <p className="muted small">로컬 모델 기동/중지·상태 확인은 관리자 메뉴의 “로컬 에이전트 관리”에서만 수행합니다.</p>
        {isAdmin && runtime ? (
          <p className="muted small">
            기본값: {runtime.default_route} / {runtime.default_provider} · 로컬 모델 {runtime.local_model}
          </p>
        ) : null}
      </div>

      <PatchOpsCockpit onMessage={setNotice} />

      {isAdmin ? (
      <details className="panel ai-test-chat-panel">
        <summary>테스트 채팅 (LLM 연결 확인용)</summary>
        <form className="memory-form" onSubmit={handleSubmit}>
          <label>
            Route
            <select value={route} onChange={(event) => setRoute(event.target.value as LlmRuntimeRoute)}>
              <option value="local">local</option>
              <option value="api">api</option>
            </select>
          </label>
          <label>
            Provider
            <select value={provider} onChange={(event) => setProvider(event.target.value as LlmProviderName)}>
              {providerOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label>
            테스트 질문
            <textarea
              value={message}
              placeholder="예: 다음 실행계획을 어떤 LLM으로 처리하면 좋을지 설명해줘"
              onChange={(event) => setMessage(event.target.value)}
            />
          </label>
          <button disabled={busy} type="submit">
            {busy ? '호출 중...' : '테스트 채팅 보내기'}
          </button>
        </form>
        <AiJobStatusBar job={chatJob} />
        <div className="log-list">
          {history.map((entry, index) => (
            <article className="log-card" key={`${entry.question}-${index}`}>
              <strong>Q. {entry.question}</strong>
              <p>{entry.response.answer || '(빈 응답)'}</p>
              <small>
                {entry.response.route} / {entry.response.provider} / {entry.response.model || 'unknown'}
              </small>
            </article>
          ))}
        </div>
      </details>
      ) : null}

      {notice ? <p className="alert">{notice}</p> : null}
    </section>
  );
}
