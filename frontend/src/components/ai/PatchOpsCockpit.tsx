import { FormEvent, useEffect, useState } from 'react';

import {
  analyzePatchRun,
  createPatchRun,
  fetchAgentPlans,
  fetchPatchRunFiles,
  fetchPatchRun,
  fetchPatchRuns,
  fetchPermanentMemory,
  promotePatchRunPlanMarkdown,
  readPatchRunFile,
  revisePatchRunPlanMarkdown,
  savePatchRunPlanMarkdown,
  type AgentPlan,
  type AiJobStatus,
  type PatchArtifactFile,
  type PatchEvent,
  type PatchRun,
  type PermanentMemorySource,
} from '../../api';
import AiJobStatusBar from '../common/AiJobStatusBar';

type Props = {
  onMessage: (message: string) => void;
};

export default function PatchOpsCockpit({ onMessage }: Props) {
  const [runs, setRuns] = useState<PatchRun[]>([]);
  const [selected, setSelected] = useState<PatchRun | null>(null);
  const [events, setEvents] = useState<PatchEvent[]>([]);
  const [repoId, setRepoId] = useState('local');
  const [request, setRequest] = useState('');
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<AiJobStatus | null>(null);
  const [plans, setPlans] = useState<AgentPlan[]>([]);
  const [files, setFiles] = useState<PatchArtifactFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<PatchArtifactFile | null>(null);
  const [planText, setPlanText] = useState('');
  const [reviseInstruction, setReviseInstruction] = useState('');
  const [memorySources, setMemorySources] = useState<PermanentMemorySource[]>([]);
  const [memoryQuery, setMemoryQuery] = useState('');
  const [selectedRefs, setSelectedRefs] = useState<string[]>([]);

  async function refreshRuns() {
    const payload = await fetchPatchRuns();
    setRuns(payload.patch_runs);
    if (!selected && payload.patch_runs[0]) {
      await loadRun(payload.patch_runs[0].id);
    }
  }

  async function loadPlans() {
    try {
      const { plans: list } = await fetchAgentPlans();
      setPlans(list);
    } catch {
      setPlans([]);
    }
  }

  async function loadMemorySources(query = '') {
    try {
      const { sources } = await fetchPermanentMemory(query);
      setMemorySources(sources);
    } catch {
      setMemorySources([]);
    }
  }

  function toggleRef(id: string) {
    setSelectedRefs((prev) => (prev.includes(id) ? prev.filter((entry) => entry !== id) : [...prev, id]));
  }

  function seedFromPlan(planId: string) {
    const plan = plans.find((entry) => entry.id === planId);
    if (!plan) return;
    const steps = plan.steps
      .map((step, index) => {
        const title = String((step as Record<string, unknown>).title ?? `단계 ${index + 1}`);
        return `${index + 1}. ${title}`;
      })
      .join('\n');
    setRequest(`계획 "${plan.title}" 기반 개발 작업\n목표: ${plan.objective}\n\n${steps}`.trim());
  }

  async function loadRun(id: string) {
    const payload = await fetchPatchRun(id);
    setSelected(payload.patch_run);
    setEvents(payload.events);
    await loadFiles(id);
  }

  async function loadFiles(id: string) {
    const payload = await fetchPatchRunFiles(id);
    setFiles(payload.files);
    const defaultFile = payload.files.find((file) => file.name === 'plan.md') ?? payload.files[0] ?? null;
    if (defaultFile) {
      await openFile(id, defaultFile.path);
    } else {
      setSelectedFile(null);
      setPlanText('');
    }
  }

  async function openFile(runId: string, path: string) {
    const payload = await readPatchRunFile(runId, path);
    setSelectedFile(payload.file);
    if (payload.file.name === 'plan.md') {
      setPlanText(payload.file.content ?? '');
    }
  }

  useEffect(() => {
    void refreshRuns().catch((err) => onMessage(err instanceof Error ? err.message : '계획서 작업 로드 실패'));
    void loadPlans();
    void loadMemorySources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!request.trim()) return;
    setBusy(true);
    setJob(localJob('patchops.create', request, 'queued'));
    try {
      setJob(localJob('patchops.create', request, 'running'));
      const payload = await createPatchRun({
        repo_id: repoId,
        request,
        constraints: {
          no_new_dependencies: true,
          require_tests: true,
          require_human_approval_for_auth: true,
        },
      });
      await savePatchRunPlanMarkdown(payload.patch_run.id, starterPlanMarkdown(request, repoId));
      setRequest('');
      await refreshRuns();
      await loadRun(payload.patch_run.id);
      setJob(localJob('patchops.create', request, 'succeeded'));
    } catch (err) {
      onMessage(err instanceof Error ? err.message : '계획서 작업 생성 실패');
      setJob(localJob('patchops.create', request, 'failed', err instanceof Error ? err.message : '계획서 작업 생성 실패'));
    } finally {
      setBusy(false);
    }
  }

  async function runStep(action: 'analyze') {
    if (!selected) return;
    setBusy(true);
    setJob(localJob(`patchops.${action}`, selected.request, 'queued'));
    try {
      setJob(localJob(`patchops.${action}`, selected.request, 'running'));
      if (action === 'analyze') {
        const payload = await analyzePatchRun(selected.id);
        setSelected(payload.patch_run);
        setEvents(payload.events);
      }
      await loadFiles(selected.id);
      await refreshRuns();
      setJob(localJob(`patchops.${action}`, selected.request, 'succeeded'));
    } catch (err) {
      onMessage(err instanceof Error ? err.message : '개발 지시서 생성 실패');
      setJob(localJob(`patchops.${action}`, selected.request, 'failed', err instanceof Error ? err.message : '개발 지시서 생성 실패'));
    } finally {
      setBusy(false);
    }
  }

  async function savePlan() {
    if (!selected) return;
    setBusy(true);
    setJob(localJob('patchops.plan.save', selected.request, 'queued'));
    try {
      setJob(localJob('patchops.plan.save', selected.request, 'running'));
      const payload = await savePatchRunPlanMarkdown(selected.id, planText);
      setSelected(payload.patch_run);
      setSelectedFile(payload.file);
      await loadFiles(selected.id);
      await refreshRuns();
      setJob(localJob('patchops.plan.save', selected.request, 'succeeded'));
    } catch (err) {
      onMessage(err instanceof Error ? err.message : 'plan.md 저장 실패');
      setJob(localJob('patchops.plan.save', selected.request, 'failed', err instanceof Error ? err.message : 'plan.md 저장 실패'));
    } finally {
      setBusy(false);
    }
  }

  async function revisePlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    if (!reviseInstruction.trim() && selectedRefs.length === 0) return;
    setBusy(true);
    const task = selectedRefs.length ? 'patchops.plan.synthesize' : 'patchops.plan.revise';
    const summaryText = reviseInstruction || `참고 파일 ${selectedRefs.length}개 합성`;
    setJob(localJob(task, summaryText, 'queued'));
    try {
      setJob(localJob(task, summaryText, 'running'));
      const payload = await revisePatchRunPlanMarkdown(selected.id, {
        instruction: reviseInstruction,
        current_content: planText,
        source_refs: selectedRefs,
      });
      setSelected(payload.patch_run);
      setSelectedFile(payload.file);
      setPlanText(payload.file.content ?? '');
      setReviseInstruction('');
      await loadFiles(selected.id);
      await refreshRuns();
      setJob(localJob(task, summaryText, 'succeeded'));
    } catch (err) {
      onMessage(err instanceof Error ? err.message : 'plan.md 합성 실패');
      setJob(localJob(task, summaryText, 'failed', err instanceof Error ? err.message : 'plan.md 합성 실패'));
    } finally {
      setBusy(false);
    }
  }

  async function promotePlan() {
    if (!selected) return;
    setBusy(true);
    setJob(localJob('patchops.plan.promote', selected.request, 'queued'));
    try {
      setJob(localJob('patchops.plan.promote', selected.request, 'running'));
      await promotePatchRunPlanMarkdown(selected.id, planText);
      await loadMemorySources(memoryQuery);
      onMessage('plan.md를 영구 메모리에 저장했습니다.');
      setJob(localJob('patchops.plan.promote', selected.request, 'succeeded'));
    } catch (err) {
      onMessage(err instanceof Error ? err.message : '영구 메모리 저장 실패');
      setJob(localJob('patchops.plan.promote', selected.request, 'failed', err instanceof Error ? err.message : '영구 메모리 저장 실패'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel agent-plans-section" aria-labelledby="patchops-heading">
      <p className="eyebrow">Agent-ready development brief</p>
      <h2 id="patchops-heading">코딩 에이전트 계획서 작성</h2>
      <p className="muted small">
        비개발자가 작성한 요청을, Cursor·Claude Code 같은 코딩 에이전트를 쓰는 개발자에게 그대로 넘길 수 있는 plan.md 한 개로
        만드는 데 집중합니다. 영구 메모리에 쌓인 기존 파일들을 골라 지시와 함께 합성하고, 완성한 계획서는 다시 영구 메모리에
        저장할 수 있습니다.
      </p>

      <form className="memory-form" onSubmit={createRun}>
        {plans.length > 0 ? (
          <label>
            계획(plan.md) 불러오기
            <select defaultValue="" onChange={(event) => { seedFromPlan(event.target.value); event.target.value = ''; }}>
              <option value="" disabled>
                계획을 선택해 요청을 채웁니다
              </option>
              {plans.map((plan) => (
                <option key={plan.id} value={plan.id}>
                  {plan.title} ({plan.status})
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <input value={repoId} onChange={(event) => setRepoId(event.target.value)} placeholder="repo id (local 또는 owner/repo)" />
        <textarea value={request} onChange={(event) => setRequest(event.target.value)} placeholder="예: 로그인 후 세션이 끊기는 문제를 개발자가 고칠 수 있도록 계획서를 만들어줘" />
        <button type="submit" disabled={busy}>{busy ? '처리 중...' : '계획서 작업 시작'}</button>
      </form>
      <AiJobStatusBar job={job} />

      <div className="split-panel">
        <div>
          <h3>계획서 작업 목록</h3>
          <ul className="agent-plan-list">
            {runs.map((run) => (
              <li key={run.id} className="agent-plan-card">
                <button className="link-button" type="button" onClick={() => void loadRun(run.id)}>
                  <strong>{run.request}</strong>
                  <span className="muted small">
                    {run.status} · 위험도 {run.risk_level}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        {selected ? (
          <div>
            <div className="agent-plan-head">
              <strong>{selected.request}</strong>
              <span className="status-pill">{selected.status}</span>
            </div>
            <PlanWorkspacePanel
              busy={busy}
              events={events}
              files={files}
              memoryQuery={memoryQuery}
              memorySources={memorySources}
              planText={planText}
              reviseInstruction={reviseInstruction}
              run={selected}
              selectedFile={selectedFile}
              selectedRefs={selectedRefs}
              onAnalyze={() => void runStep('analyze')}
              onMemoryQueryChange={setMemoryQuery}
              onMemorySearch={() => void loadMemorySources(memoryQuery)}
              onPlanChange={setPlanText}
              onPromote={() => void promotePlan()}
              onRevise={revisePlan}
              onReviseInstructionChange={setReviseInstruction}
              onSave={() => void savePlan()}
              onToggleRef={toggleRef}
            />
          </div>
        ) : (
          <p className="muted">계획서 작업을 생성하거나 선택하세요.</p>
        )}
      </div>
    </section>
  );
}

function localJob(
  task: string,
  inputSummary: string,
  status: AiJobStatus['status'],
  error = '',
): AiJobStatus {
  const now = new Date().toISOString();
  return {
    job_id: `local-${task}`,
    task,
    status,
    actor: '',
    input_summary: inputSummary,
    used_sources: [],
    result_path: '',
    error,
    created_at: now,
    updated_at: now,
  };
}

function starterPlanMarkdown(request: string, repoId: string): string {
  return [
    `# 코딩 에이전트 계획서`,
    '',
    `## 요청`,
    request.trim(),
    '',
    `## 대상 저장소`,
    repoId.trim() || 'local',
    '',
    `## 목표`,
    '- Cursor나 Claude Code가 이 파일만 읽고 다음 작업을 이어갈 수 있게 정리합니다.',
    '',
    `## 작업 메모`,
    '- 영구 메모리의 기존 파일을 골라 합성하거나, 직접 수정해 plan.md를 갱신하세요.',
    '',
    `## 실행 체크리스트`,
    '1. [ ] 저장소 구조와 관련 파일을 확인한다.',
    '2. [ ] 변경 범위와 위험 요소를 정리한다.',
    '3. [ ] 구현 단계와 검증 방법을 구체화한다.',
    '',
  ].join('\n');
}

function PlanWorkspacePanel({
  busy,
  events,
  files,
  memoryQuery,
  memorySources,
  planText,
  reviseInstruction,
  run,
  selectedFile,
  selectedRefs,
  onAnalyze,
  onMemoryQueryChange,
  onMemorySearch,
  onPlanChange,
  onPromote,
  onRevise,
  onReviseInstructionChange,
  onSave,
  onToggleRef,
}: {
  busy: boolean;
  events: PatchEvent[];
  files: PatchArtifactFile[];
  memoryQuery: string;
  memorySources: PermanentMemorySource[];
  planText: string;
  reviseInstruction: string;
  run: PatchRun;
  selectedFile: PatchArtifactFile | null;
  selectedRefs: string[];
  onAnalyze: () => void;
  onMemoryQueryChange: (value: string) => void;
  onMemorySearch: () => void;
  onPlanChange: (value: string) => void;
  onPromote: () => void;
  onRevise: (event: FormEvent<HTMLFormElement>) => void;
  onReviseInstructionChange: (value: string) => void;
  onSave: () => void;
  onToggleRef: (id: string) => void;
}) {
  const candidateFiles = arrayValue<string>(run.context.candidate_files);
  const hasPlan = Boolean(run.artifacts.plan_path || files.some((file) => file.name === 'plan.md'));
  const repoLabel = run.repo_id === 'local' ? '현재 로컬 저장소' : run.repo_id;
  const canSynthesize = !busy && (Boolean(reviseInstruction.trim()) || selectedRefs.length > 0);
  return (
    <section>
      <h3>plan.md 작업실</h3>
      <p className="muted small">
        {repoLabel} · {candidateFiles.length ? `코드 후보 ${candidateFiles.length}개 반영` : '아직 저장소를 읽지 않았습니다.'}
      </p>
      <div className="form-actions">
        <button type="button" disabled={busy} onClick={onAnalyze}>
          저장소 읽고 plan.md 만들기
        </button>
        <button type="button" disabled={busy || !planText.trim()} onClick={onSave}>
          직접 수정한 plan.md 저장
        </button>
        <button type="button" disabled={busy || !planText.trim()} onClick={onPromote}>
          영구 메모리에 저장
        </button>
      </div>

      <form className="memory-form plan-synthesis" onSubmit={onRevise}>
        <p className="eyebrow">기존 파일로 plan.md 합성</p>
        <div className="plan-source-search">
          <input
            value={memoryQuery}
            onChange={(event) => onMemoryQueryChange(event.target.value)}
            placeholder="영구 메모리 파일 검색 (제목/키워드)"
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                onMemorySearch();
              }
            }}
          />
          <button type="button" className="ghost" disabled={busy} onClick={onMemorySearch}>
            검색
          </button>
        </div>
        <div className="plan-source-list">
          {memorySources.length === 0 ? (
            <p className="muted small">영구 메모리에 불러올 파일이 없습니다.</p>
          ) : (
            memorySources.map((source) => (
              <label key={source.id} className={selectedRefs.includes(source.id) ? 'plan-source-item selected' : 'plan-source-item'}>
                <input
                  type="checkbox"
                  checked={selectedRefs.includes(source.id)}
                  onChange={() => onToggleRef(source.id)}
                />
                <span className="plan-source-meta">
                  <strong>{source.title || source.path}</strong>
                  <small className="muted">{source.path}</small>
                  {source.excerpt ? <small className="muted">{source.excerpt}</small> : null}
                </span>
              </label>
            ))
          )}
        </div>
        <small className="option-hint">
          선택한 파일 {selectedRefs.length}개 + 아래 지시를 합쳐 개발자에게 넘길 plan.md를 합성합니다.
        </small>
        <label>
          개발자에게 전달할 지시
          <textarea
            value={reviseInstruction}
            onChange={(event) => onReviseInstructionChange(event.target.value)}
            placeholder="예: 위 파일들을 참고해서, Cursor가 바로 따라할 수 있는 단계별 체크리스트와 검증 방법을 정리해줘"
            rows={3}
          />
        </label>
        <button type="submit" disabled={!canSynthesize}>
          {selectedRefs.length ? '선택한 파일로 plan.md 합성' : '지시로 plan.md 수정'}
        </button>
      </form>

      <label className="memory-form">
        plan.md 직접 편집
        <textarea
          value={planText}
          onChange={(event) => onPlanChange(event.target.value)}
          placeholder="아직 plan.md가 없습니다. 저장소를 읽거나 직접 작성하세요."
          rows={24}
        />
      </label>
      <div className="log-list">
        <article className="log-card">
          <strong>plan.md</strong>
          <p>{hasPlan ? '저장됨' : '아직 없음'}</p>
          <small>
            {selectedFile?.updated_at ? `최근 수정: ${selectedFile.updated_at}` : '저장하면 이 작업의 plan.md로 남습니다.'}
          </small>
        </article>
      </div>
      {events.length ? (
        <details>
          <summary>작업 기록 보기</summary>
          <div className="log-list">
            {events.map((event) => (
              <article className="log-card" key={event.id}>
                <strong>{event.type}</strong>
                <p>{event.summary}</p>
                <small>{event.created_at}</small>
              </article>
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}

function arrayValue<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}
