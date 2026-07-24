import { useEffect, useMemo, useState } from 'react';

import {
  fetchAgentPlans,
  fetchAiJobs,
  fetchLlmRuntime,
  fetchLocalLlmStatus,
  fetchPatchRuns,
  fetchProgress,
  fetchTokenLimits,
  type AgentPlan,
  type AiJobStatus,
  type LlmRuntime,
  type LocalLlmStatus,
  type PatchRun,
  type ProgressPayload,
  type TokenLimitStatus,
} from '../api';

type WorkflowSnapshot = {
  jobs: AiJobStatus[];
  plans: AgentPlan[];
  patchRuns: PatchRun[];
  progress: ProgressPayload | null;
  runtime: LlmRuntime | null;
  localLlm: LocalLlmStatus | null;
  tokenLimits: TokenLimitStatus | null;
};

const EMPTY_SNAPSHOT: WorkflowSnapshot = {
  jobs: [],
  plans: [],
  patchRuns: [],
  progress: null,
  runtime: null,
  localLlm: null,
  tokenLimits: null,
};

export default function WorkflowStatusPage() {
  const [snapshot, setSnapshot] = useState<WorkflowSnapshot>(EMPTY_SNAPSHOT);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');

  async function refresh() {
    setLoading(true);
    setMessage('');
    const [jobs, plans, patchRuns, progress, runtime, localLlm, tokenLimits] = await Promise.all([
      fetchAiJobs(80).then((payload) => payload.jobs).catch(() => []),
      fetchAgentPlans().then((payload) => payload.plans).catch(() => []),
      fetchPatchRuns().then((payload) => payload.patch_runs).catch(() => []),
      fetchProgress().catch(() => null),
      fetchLlmRuntime().catch(() => null),
      fetchLocalLlmStatus().catch(() => null),
      fetchTokenLimits().catch(() => null),
    ]);
    setSnapshot({ jobs, plans, patchRuns, progress, runtime, localLlm, tokenLimits });
    setLoading(false);
  }

  useEffect(() => {
    void refresh();
  }, []);

  const documentRoute = snapshot.runtime?.task_routes.document_generation ?? null;
  const recentDocumentJobs = snapshot.jobs.filter((job) => job.task === 'document_generation').slice(0, 8);
  const recentDocumentUsage = (snapshot.tokenLimits?.usage.recent ?? [])
    .filter((entry) => entry.task === 'document_generation')
    .slice(0, 8);
  const runningJobs = snapshot.jobs.filter((job) => job.status === 'running' || job.status === 'queued');
  const failedJobs = snapshot.jobs.filter((job) => job.status === 'failed');
  const runningPlans = snapshot.plans.filter((plan) => ['approved', 'running'].includes(plan.status));
  const activePatchRuns = snapshot.patchRuns.filter((run) => !['completed', 'failed', 'pr_drafted'].includes(run.status));

  const nodeCards = useMemo(
    () => [
      {
        title: 'Document LLM',
        status: documentRoute ? `${documentRoute.route}/${documentRoute.provider}` : 'default route',
        detail: documentRoute?.model || snapshot.runtime?.openai_model || 'model 미확인',
        risk:
          documentRoute?.provider === 'openai' && documentRoute.model.includes('gpt-5')
            ? '빈 message.content 응답이면 fallback으로 전환됩니다.'
            : '최근 문서 생성 job/token usage를 확인하세요.',
      },
      {
        title: 'AI Jobs',
        status: `${runningJobs.length} running · ${failedJobs.length} failed`,
        detail: `recent ${snapshot.jobs.length}`,
        risk: failedJobs[0]?.error || 'queued/running/succeeded 상태를 최근순으로 표시합니다.',
      },
      {
        title: 'Agent Plans',
        status: `${runningPlans.length} active`,
        detail: `plans ${snapshot.plans.length}`,
        risk: 'plan run timeline API는 아직 제한적이므로 plan 상태 중심으로 봅니다.',
      },
      {
        title: '코딩 에이전트 계획서 작성',
        status: `${activePatchRuns.length} active`,
        detail: `runs ${snapshot.patchRuns.length}`,
        risk: activePatchRuns[0]?.status || '코딩 에이전트 계획서 작성 화면의 상세 event와 연결됩니다.',
      },
      {
        title: 'Queue',
        status: `${snapshot.progress?.queue_size ?? 0}/${snapshot.progress?.queue_capacity ?? 0}`,
        detail: `${snapshot.progress?.recent_logs.length ?? 0} recent logs`,
        risk: '진행 로그 archive와 queue 상태를 집계합니다.',
      },
      {
        title: 'Local LLM',
        status: snapshot.localLlm?.state || 'unknown',
        detail: snapshot.localLlm?.model || 'model 미확인',
        risk: snapshot.localLlm?.error || snapshot.localLlm?.message || 'local route 사용 시 loaded 상태를 확인하세요.',
      },
    ],
    [activePatchRuns, documentRoute, failedJobs, runningJobs, runningPlans, snapshot],
  );

  return (
    <section className="page-workspace">
      <div className="workspace-hero">
        <div className="panel">
          <p className="eyebrow">Admin workflow observability</p>
          <h2>워크플로우 상태</h2>
          <p className="muted">
            문서 생성, AI job, Agent plan, 코딩 에이전트 계획서 작성, queue, LLM route를 한 화면에서 확인합니다. 빈 출력 fallback이 발생하면
            문서 생성 route와 최근 token/job 기록부터 확인하세요.
          </p>
          <button type="button" className="secondary-button" disabled={loading} onClick={() => void refresh()}>
            {loading ? '조회 중...' : '새로고침'}
          </button>
          {message ? <p className="alert">{message}</p> : null}
        </div>
        <div className="compact-stat-strip">
          <div className="compact-stat">
            <strong>{runningJobs.length}</strong>
            <span>Running jobs</span>
          </div>
          <div className="compact-stat">
            <strong>{failedJobs.length}</strong>
            <span>Failed jobs</span>
          </div>
          <div className="compact-stat">
            <strong>{activePatchRuns.length}</strong>
            <span>Active patch runs</span>
          </div>
        </div>
      </div>

      <div className="summary-grid">
        {nodeCards.map((node) => (
          <article className="panel workflow-node-card" key={node.title}>
            <p className="eyebrow">{node.title}</p>
            <h2>{node.status}</h2>
            <p className="muted small">{node.detail}</p>
            <small>{node.risk}</small>
          </article>
        ))}
      </div>

      <div className="workspace-split">
        <div className="panel workspace-sidebar">
          <div className="sticky-panel-header">
            <p className="eyebrow">Document generation debug</p>
            <h2>빈 출력 점검</h2>
          </div>
          <div className="debug-finding-list">
            <p>
              <strong>현재 route:</strong>{' '}
              {documentRoute
                ? `${documentRoute.route} / ${documentRoute.provider} / ${documentRoute.model || 'model 미지정'}`
                : `${snapshot.runtime?.default_route ?? 'unknown'} / ${snapshot.runtime?.default_provider ?? 'unknown'}`}
            </p>
            <p>
              <strong>원인 후보:</strong> provider 호출은 성공했지만 adapter가 받은 `text`가 빈 문자열이면 fallback 문서가
              저장됩니다. OpenAI `gpt-5*` 계열은 `max_completion_tokens`와 실제 visible output을 함께 확인해야 합니다.
            </p>
            <p>
              <strong>이번 패치:</strong> 빈 `text`면 completion token 수와 무관하게 6000 token 예산으로 1회 재시도하고, 그래도
              비면 fallback 문서에 provider/model/token diagnostic을 남깁니다.
            </p>
          </div>
        </div>

        <div className="panel workspace-detail">
          <div className="sticky-panel-header">
            <p className="eyebrow">Recent document_generation</p>
            <h2>Job / token 기록</h2>
          </div>
          <div className="workflow-debug-grid">
            <div className="compact-card-list bounded-list compact">
              {recentDocumentJobs.map((job) => (
                <article className="log-card" key={job.job_id}>
                  <strong>{job.status}</strong>
                  <p>{job.input_summary || job.task}</p>
                  <small>
                    {job.updated_at} · result {job.result_path || '-'} {job.error ? `· ${job.error}` : ''}
                  </small>
                </article>
              ))}
              {!recentDocumentJobs.length ? <p className="muted small">최근 문서 생성 job이 없습니다.</p> : null}
            </div>
            <div className="compact-card-list bounded-list compact">
              {recentDocumentUsage.map((entry) => (
                <article className="log-card" key={`${entry.occurred_at}-${entry.model}`}>
                  <strong>
                    {entry.provider} / {entry.model}
                  </strong>
                  <p>
                    prompt {entry.prompt_tokens.toLocaleString()} · completion {entry.completion_tokens.toLocaleString()}
                  </p>
                  <small>{entry.occurred_at}</small>
                </article>
              ))}
              {!recentDocumentUsage.length ? <p className="muted small">최근 문서 생성 token 기록이 없습니다.</p> : null}
            </div>
          </div>
        </div>
      </div>

      <details className="advanced-panel">
        <summary>최근 AI job 원본 상태</summary>
        <div className="bounded-preview">
          <pre>{JSON.stringify(snapshot.jobs.slice(0, 30), null, 2)}</pre>
        </div>
      </details>
    </section>
  );
}
