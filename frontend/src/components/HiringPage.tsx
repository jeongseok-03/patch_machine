import { FormEvent, useEffect, useState } from 'react';

import {
  createInterviewKit,
  createOnboardingPlan,
  createRoleRequirements,
  fetchAccessControl,
  saveDepartment,
  savePosition,
  type AiJobStatus,
  type DepartmentRecord,
  type GeneratedDocument,
  type HiringRequest,
  type PositionRecord,
} from '../api';
import AiJobStatusBar from './common/AiJobStatusBar';

const emptyHiring: HiringRequest = {
  role_title: '',
  business_need: '',
  priority: 'normal',
  department_id: '',
  position_id: '',
  candidate_name: '',
  candidate_profile: '',
  interview_stage: '',
  include_workload: true,
};

export default function HiringPage() {
  const [draft, setDraft] = useState<HiringRequest>(emptyHiring);
  const [result, setResult] = useState<GeneratedDocument | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [job, setJob] = useState<AiJobStatus | null>(null);
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [positions, setPositions] = useState<PositionRecord[]>([]);
  const [quickDeptName, setQuickDeptName] = useState('');
  const [quickPositionName, setQuickPositionName] = useState('');
  const [message, setMessage] = useState('');

  async function refreshOrg() {
    try {
      const acl = await fetchAccessControl();
      setDepartments(acl.departments ?? []);
      setPositions(acl.positions ?? []);
    } catch {
      setDepartments([]);
      setPositions([]);
    }
  }

  useEffect(() => {
    void refreshOrg();
  }, []);

  function slug(value: string): string {
    return value.trim().toLowerCase().replace(/[^a-z0-9가-힣]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40);
  }

  async function createQuickDepartment() {
    const name = quickDeptName.trim();
    if (!name) return;
    const id = slug(name) || `dept_${Date.now()}`;
    try {
      const acl = await saveDepartment({ id, name, description: '채용/면접 키트 생성 중 추가됨' });
      setDepartments(acl.departments ?? []);
      setDraft((current) => ({ ...current, department_id: id }));
      setQuickDeptName('');
      setMessage(`조직을 추가했습니다: ${name}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '조직 추가 실패');
    }
  }

  async function createQuickPosition() {
    const name = quickPositionName.trim();
    if (!name) return;
    const id = slug(name) || `position_${Date.now()}`;
    try {
      const acl = await savePosition({
        id,
        name,
        permissions: ['documents:read', 'documents:write'],
        display_order: 10,
        level: 0,
        description: '채용/면접 키트 생성 중 추가됨',
      });
      setPositions(acl.positions ?? []);
      setDraft((current) => ({ ...current, position_id: id, role_title: current.role_title || name }));
      setQuickPositionName('');
      setMessage(`직급을 추가했습니다: ${name}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '직급 추가 실패');
    }
  }

  async function generate(action: 'requirements' | 'interview' | 'onboarding') {
    setBusy(action);
    setJob({
      job_id: `local-hiring-${action}`,
      task: `hiring.${action}`,
      status: 'queued',
      actor: '',
      input_summary: draft.role_title,
      used_sources: [],
      result_path: '',
      error: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    try {
      setJob((current) => current ? { ...current, status: 'running', updated_at: new Date().toISOString() } : current);
      const next =
        action === 'requirements'
          ? await createRoleRequirements(draft)
          : action === 'interview'
            ? await createInterviewKit(draft)
            : await createOnboardingPlan(draft);
      setResult(next);
      setJob(next.ai_job ?? null);
      setMessage(`생성 완료: ${next.path}`);
    } catch (err) {
      setJob((current) =>
        current
          ? {
              ...current,
              status: 'failed',
              error: err instanceof Error ? err.message : '채용 문서 생성 실패',
              updated_at: new Date().toISOString(),
            }
          : current,
      );
    } finally {
      setBusy(null);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void generate('requirements');
  }

  return (
    <section className="page-grid">
      <div className="panel">
        <p className="eyebrow">Hiring BPA</p>
        <h2>채용/면접 키트 생성</h2>
        <p className="muted">
          네고티움 영구메모리와 현재 업무 계획을 바탕으로 직무 요구사항, 면접 질문, 온보딩 계획을 생성합니다.
        </p>
        <form className="memory-form" onSubmit={handleSubmit}>
          <details className="advanced-panel">
            <summary>관리자: 새 조직/직급 빠른 개설</summary>
            <p className="muted small">신입사원을 직원으로 배정하지 않아도 채용 키트 대상 조직과 직급을 먼저 만들 수 있습니다.</p>
            <div className="org-form-row">
              <label>
                새 조직명
                <input value={quickDeptName} placeholder="예: 데이터 제작팀" onChange={(event) => setQuickDeptName(event.target.value)} />
              </label>
              <button type="button" className="secondary-button" onClick={() => void createQuickDepartment()}>
                조직 추가
              </button>
            </div>
            <div className="org-form-row">
              <label>
                새 직급명
                <input value={quickPositionName} placeholder="예: 신입 데이터 검수자" onChange={(event) => setQuickPositionName(event.target.value)} />
              </label>
              <button type="button" className="secondary-button" onClick={() => void createQuickPosition()}>
                직급 추가
              </button>
            </div>
          </details>
          <label>
            직무명
            <input
              value={draft.role_title}
              placeholder="예: 회사 서류 자동화 담당자"
              onChange={(event) => setDraft({ ...draft, role_title: event.target.value })}
            />
          </label>
          <div className="org-form-row">
            <label>
              대상 조직
              <select value={draft.department_id ?? ''} onChange={(event) => setDraft({ ...draft, department_id: event.target.value })}>
                <option value="">조직 미지정</option>
                {departments.map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              직급
              <select
                value={draft.position_id ?? ''}
                onChange={(event) => {
                  const position = positions.find((item) => item.id === event.target.value);
                  setDraft({
                    ...draft,
                    position_id: event.target.value,
                    role_title: draft.role_title || position?.name || '',
                  });
                }}
              >
                <option value="">직급 미지정</option>
                {positions
                  .slice()
                  .sort((a, b) => (b.display_order ?? b.level ?? 0) - (a.display_order ?? a.level ?? 0))
                  .map((position) => (
                    <option key={position.id} value={position.id}>
                      {position.name}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <div className="org-form-row">
            <label>
              후보자/신입 이름
              <input
                value={draft.candidate_name ?? ''}
                placeholder="직원 배정 전 신원 메모용"
                onChange={(event) => setDraft({ ...draft, candidate_name: event.target.value })}
              />
            </label>
            <label>
              채용 단계
              <select value={draft.interview_stage ?? ''} onChange={(event) => setDraft({ ...draft, interview_stage: event.target.value })}>
                <option value="">단계 미지정</option>
                <option value="서류 검토">서류 검토</option>
                <option value="1차 면접">1차 면접</option>
                <option value="실무 과제">실무 과제</option>
                <option value="최종 면접">최종 면접</option>
                <option value="온보딩 준비">온보딩 준비</option>
              </select>
            </label>
          </div>
          <label>
            후보자 신원/경력 메모
            <textarea
              value={draft.candidate_profile ?? ''}
              placeholder="아직 직원 배정 전이라도 경력, 신원 확인 필요사항, 면접 메모를 넣으세요."
              onChange={(event) => setDraft({ ...draft, candidate_profile: event.target.value })}
            />
          </label>
          <label>
            필요한 업무/비즈니스 상황
            <textarea
              value={draft.business_need}
              placeholder="예: Discord로 들어오는 문서를 분류하고 처리 흐름을 자동화해야 함"
              onChange={(event) => setDraft({ ...draft, business_need: event.target.value })}
            />
          </label>
          <label>
            우선순위
            <select
              value={draft.priority}
              onChange={(event) => setDraft({ ...draft, priority: event.target.value })}
            >
              <option value="low">low</option>
              <option value="normal">normal</option>
              <option value="high">high</option>
              <option value="urgent">urgent</option>
            </select>
          </label>
          <label className="checkbox-inline">
            <input
              type="checkbox"
              checked={draft.include_workload ?? true}
              onChange={(event) => setDraft({ ...draft, include_workload: event.target.checked })}
            />
            대상 조직의 현재 업무량/스케줄을 AI가 읽고 반영
          </label>
          <div className="form-actions">
            <button disabled={!!busy} type="submit">요구사항 생성</button>
            <button disabled={!!busy} type="button" onClick={() => void generate('interview')}>
              면접 키트 생성
            </button>
            <button disabled={!!busy} type="button" onClick={() => void generate('onboarding')}>
              온보딩 계획 생성
            </button>
          </div>
        </form>
        {message ? <p className="muted">{message}</p> : null}
        <AiJobStatusBar job={job} />
      </div>
      <GeneratedDocumentPanel result={result} />
    </section>
  );
}

function GeneratedDocumentPanel({ result }: { result: GeneratedDocument | null }) {
  return (
    <div className="panel">
      <p className="eyebrow">Generated</p>
      <h2>생성 결과</h2>
      {result ? (
        <>
          <p className="muted">저장 위치: {result.path}</p>
          <pre className="status-pre">{result.markdown}</pre>
        </>
      ) : (
        <p className="muted">아직 생성된 문서가 없습니다.</p>
      )}
    </div>
  );
}
