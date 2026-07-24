import { DragEvent, FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';

import {
  approveAgentPlan,
  fetchAgentPlans,
  fetchConversations,
  fetchLlmRuntime,
  fetchSkills,
  fetchWorkSchedule,
  generateAgentPlan,
  runAgentPlan,
  streamChatMessage,
  uploadDocument,
  type AgentPlan,
  type ChatResponse,
  type ConversationRecord,
  type LlmProviderName,
  type LlmRuntime,
  type LlmRuntimeRoute,
  type SkillDescriptor,
  type WorkScheduleItem,
} from '../api';

type AssistantMode = 'chat' | 'plan';

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
  meta?: { provider: string; model: string; route: string };
  notes?: string[];
  skillId?: string;
};

type Attachment = { id: string; filename: string };

type ConversationThread = {
  id: string;
  title: string;
  createdAt: string;
  messageCount: number;
  records: ConversationRecord[];
};

type HistoryTab = 'chat' | 'schedule';

function SkillResultView({ skillId, content }: { skillId: string; content: string }) {
  const jsonMatch = content.match(/```json\s*([\s\S]*?)```/);
  let data: Record<string, unknown> | null = null;
  if (jsonMatch) {
    try {
      data = JSON.parse(jsonMatch[1]) as Record<string, unknown>;
    } catch {
      data = null;
    }
  }

  const textBody = content
    .replace(/```json[\s\S]*?```/g, '')
    .replace(new RegExp(`^\\s*\`/${skillId}\`[^\\n]*\\n?`), '')
    .trim();

  if (!data) {
    return <div className="chat-bubble-body">{content}</div>;
  }

  const ok =
    data.ok === true ||
    (typeof data.ok === 'undefined' && !('error' in data) && data.exit_code === 0);
  const command = typeof data.command === 'string' ? data.command : '';
  const exitCode = data.exit_code;
  const excerptRaw =
    (typeof data.output_excerpt === 'string' && data.output_excerpt) ||
    (typeof data.diff === 'string' && data.diff) ||
    (typeof data.output === 'string' && data.output) ||
    (typeof data.stdout === 'string' && data.stdout) ||
    (typeof data.error === 'string' && data.error) ||
    '';
  const excerpt = String(excerptRaw);

  return (
    <div className="skill-result">
      <div className="skill-result-head">
        <span className="chat-skill-tag">/{skillId}</span>
        <span className={`skill-pill ${ok ? 'ok' : 'fail'}`}>{ok ? '성공' : '실패'}</span>
        {typeof exitCode !== 'undefined' ? (
          <span className="muted small">exit {String(exitCode)}</span>
        ) : null}
      </div>
      {command ? <code className="skill-result-cmd">$ {command}</code> : null}
      {textBody ? <p className="skill-result-text">{textBody}</p> : null}
      {excerpt ? (
        <details className="skill-result-details" open={!ok}>
          <summary>출력 보기</summary>
          <pre className="skill-result-pre">{excerpt.slice(0, 6000)}</pre>
        </details>
      ) : null}
      <details className="skill-result-details">
        <summary>원본 JSON</summary>
        <pre className="skill-result-pre">{JSON.stringify(data, null, 2)}</pre>
      </details>
    </div>
  );
}

let messageSeq = 0;
function nextId(): string {
  messageSeq += 1;
  return `m${Date.now()}-${messageSeq}`;
}

export default function LlmChatPage() {
  const [runtime, setRuntime] = useState<LlmRuntime | null>(null);
  const [input, setInput] = useState('');
  const [route, setRoute] = useState<LlmRuntimeRoute>('local');
  const [provider, setProvider] = useState<LlmProviderName>('vllm');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [skills, setSkills] = useState<SkillDescriptor[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [showSlash, setShowSlash] = useState(false);
  const [slashHighlight, setSlashHighlight] = useState(0);
  const [dragActive, setDragActive] = useState(false);
  const [mode, setMode] = useState<AssistantMode>('chat');
  const [plans, setPlans] = useState<AgentPlan[]>([]);
  const [conversationThreads, setConversationThreads] = useState<ConversationThread[]>([]);
  const [scheduleItems, setScheduleItems] = useState<WorkScheduleItem[]>([]);
  const [activeThreadId, setActiveThreadId] = useState('new');
  const [historyTab, setHistoryTab] = useState<HistoryTab>('chat');
  const [historyQuery, setHistoryQuery] = useState('');
  const threadRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages]);

  async function bootstrap() {
    await refreshRuntime();
    await Promise.all([loadTranscript(), loadSkills(), loadPlans(), loadScheduleHistory()]);
  }

  async function loadPlans() {
    try {
      const { plans: list } = await fetchAgentPlans();
      setPlans(list);
    } catch {
      setPlans([]);
    }
  }

  async function loadScheduleHistory() {
    try {
      const payload = await fetchWorkSchedule();
      setScheduleItems(payload.items);
    } catch {
      setScheduleItems([]);
    }
  }

  function buildConversationContext(): string {
    return messages
      .filter((entry) => entry.content.trim())
      .slice(-12)
      .map((entry) => `${entry.role === 'user' ? '사용자' : 'AI'}: ${entry.content}`)
      .join('\n');
  }

  function recordsToMessages(records: ConversationRecord[]): ChatMessage[] {
    return records.map((record) => ({
      id: record.id || nextId(),
      role: record.role === 'assistant' ? 'assistant' : 'user',
      content: record.content,
      meta:
        record.role === 'assistant'
          ? { provider: record.provider, model: record.model, route: record.route }
          : undefined,
    }));
  }

  function groupConversationThreads(records: ConversationRecord[]): ConversationThread[] {
    const ordered = [...records].sort(
      (a, b) => new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime(),
    );
    const groups: ConversationRecord[][] = [];
    ordered.forEach((record) => {
      const last = groups[groups.length - 1];
      const lastRecord = last?.[last.length - 1];
      const gapMs =
        lastRecord && record.created_at && lastRecord.created_at
          ? new Date(record.created_at).getTime() - new Date(lastRecord.created_at).getTime()
          : 0;
      if (!last || gapMs > 1000 * 60 * 45) {
        groups.push([record]);
      } else {
        last.push(record);
      }
    });
    return groups
      .map((group, index) => {
        const firstUser = group.find((record) => record.role === 'user');
        const title = String(firstUser?.content || group[0]?.content || '새 대화').slice(0, 48);
        return {
          id: `${group[0]?.created_at || index}-${group[0]?.id || index}`,
          title,
          createdAt: String(group[0]?.created_at || ''),
          messageCount: group.length,
          records: group,
        };
      })
      .reverse();
  }

  function startNewThread() {
    setMessages([]);
    setActiveThreadId('new');
    setInput('');
    setAttachments([]);
    setNotice('새 대화를 시작합니다. 이전 기록은 오른쪽 이력 패널에서 다시 열 수 있습니다.');
  }

  function openThread(thread: ConversationThread) {
    setMessages(recordsToMessages(thread.records));
    setActiveThreadId(thread.id);
    setNotice(null);
  }

  function appendHistoryToInput(text: string) {
    setInput((current) => (current.trim() ? `${current.trim()}\n\n${text}` : text));
  }

  const filteredThreads = useMemo(() => {
    const needle = historyQuery.trim().toLowerCase();
    if (!needle) return conversationThreads;
    return conversationThreads.filter((thread) =>
      `${thread.title} ${thread.records.map((record) => record.content).join(' ')}`.toLowerCase().includes(needle),
    );
  }, [conversationThreads, historyQuery]);

  const filteredSchedules = useMemo(() => {
    const needle = historyQuery.trim().toLowerCase();
    return scheduleItems.filter((item) => {
      const haystack = `${item.title} ${item.owner_name} ${item.status} ${item.priority} ${item.notes} ${item.due_date}`.toLowerCase();
      return !needle || haystack.includes(needle);
    });
  }, [historyQuery, scheduleItems]);

  async function handleAgentPlan(text: string) {
    const context = buildConversationContext();
    const userMessage: ChatMessage = { id: nextId(), role: 'user', content: text };
    const assistantId = nextId();
    setMessages((current) => [
      ...current,
      userMessage,
      { id: assistantId, role: 'assistant', content: '실행 계획을 설계하는 중…', streaming: true },
    ]);
    setInput('');
    setShowSlash(false);
    setBusy(true);
    setNotice(null);
    try {
      const { plan } = await generateAgentPlan({
        objective: text,
        title: text.slice(0, 60),
        mode: 'plan_only',
        schedule_refs: [],
        memory_refs: [],
        context,
      });
      const summary = plan.steps
        .map((step, index) => {
          const title = String((step as Record<string, unknown>).title ?? `단계 ${index + 1}`);
          const approval = (step as Record<string, unknown>).requires_approval ? ' (승인 필요)' : '';
          return `${index + 1}. ${title}${approval}`;
        })
        .join('\n');
      setMessages((current) =>
        current.map((item) =>
          item.id === assistantId
            ? {
                ...item,
                streaming: false,
                content: `실행 계획 “${plan.title}”을(를) 설계했습니다. 우측 패널에서 승인·실행할 수 있습니다.\n\n${summary}`,
              }
            : item,
        ),
      );
      await loadPlans();
    } catch (err) {
      const detail = err instanceof Error ? err.message : '실행 계획 생성 실패';
      setMessages((current) =>
        current.map((item) =>
          item.id === assistantId ? { ...item, streaming: false, content: `오류: ${detail}` } : item,
        ),
      );
      setNotice(detail);
    } finally {
      setBusy(false);
      void loadTranscript();
    }
  }

  async function refreshRuntime() {
    try {
      const nextRuntime = await fetchLlmRuntime();
      setRuntime(nextRuntime);
      setRoute(nextRuntime.default_route);
      setProvider(nextRuntime.default_provider);
    } catch (err: unknown) {
      setNotice(err instanceof Error ? err.message : '런타임 로드 실패');
    }
  }

  async function loadTranscript() {
    try {
      const { records } = await fetchConversations();
      const threads = groupConversationThreads(records);
      setConversationThreads(threads);
      if (activeThreadId !== 'new' && !threads.some((thread) => thread.id === activeThreadId)) {
        setActiveThreadId('new');
      }
    } catch {
      // transcript is best-effort; ignore load errors
    }
  }

  async function loadSkills() {
    try {
      const { skills: list } = await fetchSkills();
      setSkills(list);
    } catch {
      setSkills([]);
    }
  }

  async function handleFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    setUploading(true);
    setNotice(null);
    try {
      for (const file of Array.from(fileList)) {
        const form = new FormData();
        form.append('file', file);
        form.append('work_title', 'AI 어시스턴트 첨부');
        form.append('description', '실시간 채팅 첨부 파일');
        const res = await uploadDocument(form);
        setAttachments((current) => [...current, { id: res.upload.id, filename: res.upload.filename }]);
      }
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '첨부 업로드 실패');
    } finally {
      setUploading(false);
    }
  }

  function onInputChange(value: string) {
    setInput(value);
    const trimmed = value.trimStart();
    setShowSlash(trimmed.startsWith('/') && !trimmed.includes('\n') && !trimmed.includes(' '));
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (showSlash && slashMatches.length > 0) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setSlashHighlight((current) => (current + 1) % slashMatches.length);
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setSlashHighlight((current) => (current - 1 + slashMatches.length) % slashMatches.length);
        return;
      }
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        applySlash(slashMatches[slashHighlight]);
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        setShowSlash(false);
        return;
      }
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void handleSubmit(event as unknown as FormEvent<HTMLFormElement>);
    }
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(true);
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (event.currentTarget.contains(event.relatedTarget as Node)) return;
    setDragActive(false);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    void handleFiles(event.dataTransfer.files);
  }

  const slashQuery = useMemo(() => {
    const token = input.trimStart();
    return token.startsWith('/') ? token.slice(1).toLowerCase() : '';
  }, [input]);

  const slashMatches = useMemo(() => {
    if (!showSlash) return [];
    const filtered = skills.filter(
      (skill) =>
        skill.id.toLowerCase().includes(slashQuery) || skill.name.toLowerCase().includes(slashQuery),
    );
    if (slashQuery === '' || slashQuery === 'skill') {
      return filtered.slice(0, 8);
    }
    return filtered.slice(0, 8);
  }, [showSlash, skills, slashQuery]);

  useEffect(() => {
    setSlashHighlight(0);
  }, [slashMatches.length, slashQuery]);

  function applySlash(skill: SkillDescriptor) {
    setInput(`/${skill.id} `);
    setShowSlash(false);
  }

  async function approvePlan(planId: string) {
    try {
      await approveAgentPlan(planId);
      await loadPlans();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '계획 승인 실패');
    }
  }

  async function runPlan(planId: string) {
    try {
      await runAgentPlan(planId);
      setNotice('실행 요청을 기록했습니다.');
      await loadPlans();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '계획 실행 요청 실패');
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    if (mode === 'plan') {
      await handleAgentPlan(text);
      return;
    }
    const attachmentIds = attachments.map((item) => item.id);
    const userMessage: ChatMessage = { id: nextId(), role: 'user', content: text };
    const assistantId = nextId();
    setMessages((current) => [
      ...current,
      userMessage,
      { id: assistantId, role: 'assistant', content: '', streaming: true },
    ]);
    setInput('');
    setAttachments([]);
    setShowSlash(false);
    setBusy(true);
    setNotice(null);

    const patchAssistant = (patch: Partial<ChatMessage>) =>
      setMessages((current) =>
        current.map((item) => (item.id === assistantId ? { ...item, ...patch } : item)),
      );

    try {
      await streamChatMessage(
        text,
        route,
        provider,
        {
          onMeta: (meta) =>
            patchAssistant({ meta: { provider: meta.provider, model: meta.model, route: meta.route }, skillId: meta.skill_id }),
          onDelta: (delta) =>
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantId ? { ...item, content: item.content + delta } : item,
              ),
            ),
          onDone: (response: ChatResponse) =>
            patchAssistant({
              content: response.answer || '(빈 응답)',
              streaming: false,
              notes: response.attachment_notes,
              skillId: response.skill_id,
              meta: { provider: response.provider, model: response.model, route: response.route },
            }),
          onError: (detail) => {
            patchAssistant({ content: `오류: ${detail}`, streaming: false });
            setNotice(detail);
          },
        },
        { attachmentIds },
      );
    } catch (err) {
      patchAssistant({ content: '오류로 응답을 받지 못했습니다.', streaming: false });
      setNotice(err instanceof Error ? err.message : '채팅 호출 실패');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="assistant-layout">
      <div className="panel assistant-controls">
        <p className="eyebrow">AI 어시스턴트</p>
        <h2>메모리 기반 실시간 채팅</h2>
        <p className="muted">
          영구·휘발성 메모리와 최근 대화를 기억하고, <code>/스킬</code> 슬래시 명령으로 오피스 기능을 바로 실행합니다.
        </p>

        <div className="mode-toggle" role="tablist" aria-label="응답 모드">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'chat'}
            className={mode === 'chat' ? 'mode-toggle-btn active' : 'mode-toggle-btn'}
            onClick={() => setMode('chat')}
          >
            대화 모드
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'plan'}
            className={mode === 'plan' ? 'mode-toggle-btn active' : 'mode-toggle-btn'}
            onClick={() => setMode('plan')}
          >
            계획 모드
          </button>
        </div>
        <p className="muted small">
          {mode === 'plan'
            ? '계획 모드: 지금까지의 대화 맥락을 바탕으로 plan.md 형식의 실행 계획을 설계합니다. 이 계획은 코딩 에이전트 계획서 작성·프로세스 설계에서 그대로 불러와 사용할 수 있습니다.'
            : '대화 모드: 메모리와 스킬을 활용한 일반 대화를 합니다.'}
        </p>

        <div className="model-hint">
          <span className="muted small">
            현재 모델: {runtime?.default_route || 'local'} / {runtime?.default_provider || 'vllm'} ·{' '}
            {runtime?.local_model || 'Qwen/Qwen3-4B'}
          </span>
          <p className="muted small">모델·로컬 에이전트 설정은 관리자 설정에서 변경합니다.</p>
        </div>

        <div className="assistant-skill-hint">
          <p className="eyebrow">슬래시 스킬</p>
          <ul>
            {skills.slice(0, 6).map((skill) => (
              <li key={skill.id}>
                <button type="button" onClick={() => applySlash(skill)}>
                  /{skill.id}
                </button>
                <span className="muted"> {skill.name}</span>
              </li>
            ))}
            {skills.length === 0 ? <li className="muted">스킬을 불러오는 중…</li> : null}
          </ul>
          <p className="muted">입력창에 <code>/</code> 를 입력하면 자동완성이 열립니다. <code>/skills</code> 로 전체 목록.</p>
        </div>

        {mode === 'plan' ? (
          <div className="assistant-plan-panel">
            <p className="eyebrow">계획 (plan.md)</p>
            {plans.length === 0 ? (
              <p className="muted small">아직 생성된 계획이 없습니다. 메시지를 보내면 대화 맥락으로 plan.md 계획을 설계합니다.</p>
            ) : (
              <ul className="agent-plan-list" aria-label="에이전트 계획 목록">
                {plans.map((plan) => (
                  <li key={plan.id} className="agent-plan-card">
                    <div className="agent-plan-head">
                      <strong>{plan.title}</strong>
                      <span className="muted small">
                        {plan.status} · 단계 {plan.steps.length}
                      </span>
                    </div>
                    {plan.plan_markdown_path ? (
                      <p className="muted small">📄 {plan.plan_markdown_path}</p>
                    ) : null}
                    <div className="form-actions">
                      <button type="button" onClick={() => void approvePlan(plan.id)}>
                        승인
                      </button>
                      <button className="secondary-button" type="button" onClick={() => void runPlan(plan.id)}>
                        실행 요청
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}
      </div>

      <div
        className={`panel assistant-chat${dragActive ? ' assistant-chat-drag' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {dragActive ? <div className="assistant-drop-overlay">파일을 여기에 놓으세요</div> : null}
        <div className="assistant-thread" ref={threadRef}>
          {messages.length === 0 ? (
            <p className="muted">대화를 시작해 보세요. 예) “이번 주 문서 자동화 업무의 다음 액션 알려줘”</p>
          ) : null}
          {messages.map((entry) => (
            <div key={entry.id} className={`chat-bubble chat-bubble-${entry.role}`}>
              {entry.skillId && !entry.streaming && entry.content ? (
                <SkillResultView skillId={entry.skillId} content={entry.content} />
              ) : (
                <div className="chat-bubble-body">
                  {entry.content || (entry.streaming ? '…' : '(빈 응답)')}
                  {entry.streaming ? <span className="chat-cursor">▌</span> : null}
                </div>
              )}
              {entry.notes && entry.notes.length > 0 ? (
                <ul className="chat-notes">
                  {entry.notes.map((note, idx) => (
                    <li key={idx}>{note}</li>
                  ))}
                </ul>
              ) : null}
              {entry.meta ? (
                <small className="muted">
                  {entry.meta.route} / {entry.meta.provider} / {entry.meta.model || 'unknown'}
                </small>
              ) : null}
            </div>
          ))}
        </div>

        {attachments.length > 0 ? (
          <div className="attachment-list">
            {attachments.map((item) => (
              <span className="attachment-chip" key={item.id}>
                {item.filename}
                <button
                  type="button"
                  onClick={() => setAttachments((current) => current.filter((a) => a.id !== item.id))}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : null}

        <form className="assistant-composer" onSubmit={handleSubmit}>
          {showSlash ? (
            <div className="slash-menu">
              {slashMatches.length === 0 ? (
                <button type="button" onClick={() => { setInput('/skills '); setShowSlash(false); }}>
                  <strong>/skills</strong>
                  <span className="muted">사용 가능한 스킬 목록</span>
                </button>
              ) : null}
              {slashMatches.map((skill, index) => (
                <button
                  key={skill.id}
                  type="button"
                  className={index === slashHighlight ? 'slash-menu-active' : ''}
                  onMouseEnter={() => setSlashHighlight(index)}
                  onClick={() => applySlash(skill)}
                >
                  <strong>/{skill.id}</strong>
                  <span className="muted">{skill.name}</span>
                </button>
              ))}
            </div>
          ) : null}
          <textarea
            value={input}
            placeholder={
              mode === 'plan'
                ? '계획으로 만들 목표를 입력하세요 (대화 맥락 기반 plan.md 생성)'
                : '메시지를 입력하거나 /로 스킬을 호출하세요'
            }
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={handleComposerKeyDown}
          />
          <div className="assistant-composer-actions">
            <label className="file-upload-label">
              {uploading ? '업로드 중…' : '파일 첨부'}
              <input
                type="file"
                multiple
                accept=".png,.jpg,.jpeg,.webp,.gif,.bmp,.pdf,.txt,.md,.csv,.mp3,.wav,.m4a,.ogg,.webm,.flac"
                onChange={(event) => void handleFiles(event.target.files)}
                style={{ display: 'none' }}
              />
            </label>
            <button disabled={busy || uploading} type="submit">
              {busy ? (mode === 'plan' ? '설계 중…' : '응답 중…') : mode === 'plan' ? '계획 설계' : '보내기'}
            </button>
          </div>
        </form>
        {notice ? <p className="alert">{notice}</p> : null}
      </div>

      <aside className="panel assistant-history-rail">
        <div className="conversation-history-head">
          <div>
            <p className="eyebrow">History</p>
            <h3>대화·일정 이력</h3>
          </div>
          <button type="button" onClick={startNewThread}>
            새 대화
          </button>
        </div>
        <input
          value={historyQuery}
          placeholder="과거 대화나 업무 일정 검색"
          onChange={(event) => setHistoryQuery(event.target.value)}
        />
        <div className="history-tab-row" role="tablist" aria-label="이력 종류">
          <button
            type="button"
            className={historyTab === 'chat' ? 'active' : ''}
            onClick={() => setHistoryTab('chat')}
          >
            대화 {filteredThreads.length}
          </button>
          <button
            type="button"
            className={historyTab === 'schedule' ? 'active' : ''}
            onClick={() => setHistoryTab('schedule')}
          >
            일정 {filteredSchedules.length}
          </button>
        </div>

        {historyTab === 'chat' ? (
          <div className="conversation-thread-list">
            {filteredThreads.length === 0 ? <p className="muted small">조건에 맞는 대화 기록이 없습니다.</p> : null}
            {filteredThreads.map((thread) => (
              <article
                key={thread.id}
                className={activeThreadId === thread.id ? 'conversation-thread active' : 'conversation-thread'}
              >
                <button type="button" onClick={() => openThread(thread)}>
                  <strong>{thread.title}</strong>
                  <span>
                    {new Date(thread.createdAt).toLocaleString()} · {thread.messageCount}개 메시지
                  </span>
                </button>
                <button
                  type="button"
                  className="ghost small"
                  onClick={() => appendHistoryToInput(`과거 대화 참고:\n${thread.records.map((record) => `${record.role}: ${record.content}`).join('\n')}`)}
                >
                  입력에 넣기
                </button>
              </article>
            ))}
          </div>
        ) : (
          <div className="conversation-thread-list">
            {filteredSchedules.length === 0 ? <p className="muted small">조건에 맞는 업무 일정이 없습니다.</p> : null}
            {filteredSchedules.map((item) => (
              <article className="conversation-thread" key={item.id}>
                <strong>{item.title}</strong>
                <span>
                  {item.owner_name || '담당자 미정'} · {item.status} · {item.due_date || '마감 미정'}
                </span>
                {item.notes ? <p className="muted small">{item.notes.slice(0, 120)}</p> : null}
                <button
                  type="button"
                  className="ghost small"
                  onClick={() =>
                    appendHistoryToInput(
                      `업무 일정 참고:\n- 제목: ${item.title}\n- 담당: ${item.owner_name || '미정'}\n- 상태: ${item.status}\n- 마감: ${item.due_date || '미정'}\n- 메모: ${item.notes || '없음'}`,
                    )
                  }
                >
                  입력에 넣기
                </button>
              </article>
            ))}
          </div>
        )}
      </aside>
    </section>
  );
}
