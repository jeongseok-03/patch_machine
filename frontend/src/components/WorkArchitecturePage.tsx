import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  addProcessStep,
  approveProcessPlan,
  deleteProcessStep,
  fetchAccessControl,
  fetchAgentPlans,
  fetchProcessPlan,
  fetchProcessPlans,
  generateWorkArchitecture,
  pauseProcessPlan,
  reorderProcessSteps,
  resumeProcessPlan,
  runWorkScheduleItem,
  setProcessPlanMode,
  signOffWorkItem,
  updateProcessStep,
  type AgentPlan,
  type AiJobStatus,
  type DepartmentRecord,
  type PositionRecord,
  type ProcessPlan,
  type ProcessPlanStep,
  type UserRecord,
} from '../api';
import AiJobStatusBar from './common/AiJobStatusBar';
import ProcessGraph from './process/ProcessGraph';

const STATUS_LABELS: Record<string, string> = {
  draft: '초안 (승인 대기)',
  approved: '승인됨',
  running: '실행 중',
  paused: '일시정지',
  completed: '완료',
  cancelled: '취소',
};

const emptyStepDraft = { title: '', notes: '', owner_name: '', priority: 'normal', assignee_kind: 'unassigned' };
const BLOCKED_PARTICIPANT_ROLES = new Set(['owner', 'admin', 'system', 'viewer']);
const ASSIGNEE_LABELS: Record<string, string> = { unassigned: '미지정', human: '사람', ai: 'AI 모델' };

export default function WorkArchitecturePage() {
  const [draft, setDraft] = useState({
    objective: '',
    scope: '',
    horizon: '',
    participants: '',
    constraints: '',
    use_memory: true,
  });
  const [message, setMessage] = useState('');
  const [job, setJob] = useState<AiJobStatus | null>(null);
  const [generating, setGenerating] = useState(false);

  const [plans, setPlans] = useState<ProcessPlan[]>([]);
  const [plan, setPlan] = useState<ProcessPlan | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [stepDraft, setStepDraft] = useState(emptyStepDraft);
  const [showMarkdown, setShowMarkdown] = useState(false);
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [positions, setPositions] = useState<PositionRecord[]>([]);
  const [selectedDeptIds, setSelectedDeptIds] = useState<string[]>([]);
  const [selectedParticipantIds, setSelectedParticipantIds] = useState<string[]>([]);
  const [participantDeptFilter, setParticipantDeptFilter] = useState('');
  const [participantPositionFilter, setParticipantPositionFilter] = useState('');
  const [deptPickerOpen, setDeptPickerOpen] = useState(false);
  const [participantPickerOpen, setParticipantPickerOpen] = useState(false);
  const [agentPlans, setAgentPlans] = useState<AgentPlan[]>([]);
  const busyRef = useRef(false);

  useEffect(() => {
    void (async () => {
      try {
        const acl = await fetchAccessControl();
        setUsers(acl.users.filter((user) => user.active !== false));
        setDepartments(acl.departments ?? []);
        setPositions(acl.positions ?? []);
      } catch {
        setUsers([]);
      }
      try {
        const { plans: list } = await fetchAgentPlans();
        setAgentPlans(list);
      } catch {
        setAgentPlans([]);
      }
    })();
  }, []);

  function seedFromAgentPlan(planId: string) {
    const source = agentPlans.find((entry) => entry.id === planId);
    if (!source) return;
    const steps = source.steps
      .map((step, index) => {
        const title = String((step as Record<string, unknown>).title ?? `단계 ${index + 1}`);
        return `${index + 1}. ${title}`;
      })
      .join('\n');
    setDraft((current) => ({
      ...current,
      objective: source.objective || source.title,
      constraints: current.constraints || `참고 계획 단계:\n${steps}`,
    }));
    setMessage(`계획 “${source.title}”을(를) 설계 기반으로 불러왔습니다. 투입 인력·기간을 지정하세요.`);
  }

  const sortedPositions = [...positions].sort((a, b) => (b.display_order ?? b.level ?? 0) - (a.display_order ?? a.level ?? 0));
  const selectedDepartments = selectedDeptIds
    .map((deptId) => departments.find((dept) => dept.id === deptId))
    .filter((dept): dept is DepartmentRecord => Boolean(dept));
  const participantDepartments = selectedDepartments.length ? selectedDepartments : departments;
  const eligibleParticipants = useMemo(
    () =>
      users.filter((user) => {
        if (BLOCKED_PARTICIPANT_ROLES.has(user.role_id)) return false;
        if (!user.department || !user.position_id) return false;
        if (selectedDeptIds.length && !selectedDeptIds.includes(user.department)) return false;
        return true;
      }),
    [selectedDeptIds, users],
  );
  const eligibleParticipantIds = useMemo(() => new Set(eligibleParticipants.map((user) => user.id)), [eligibleParticipants]);
  const filteredParticipants = eligibleParticipants.filter((user) => {
    if (participantDeptFilter && (user.department ?? '') !== participantDeptFilter) return false;
    if (participantPositionFilter && (user.position_id ?? '') !== participantPositionFilter) return false;
    return true;
  });

  function positionName(id?: string): string {
    if (!id) return '직급 미지정';
    return positions.find((entry) => entry.id === id)?.name ?? '직급 미지정';
  }

  function participantLabel(user: UserRecord): string {
    const dept = departments.find((d) => d.id === user.department)?.name;
    const position = positions.find((p) => p.id === user.position_id)?.name;
    const tags = [dept, position].filter(Boolean).join('/');
    return tags ? `${user.display_name}(${tags})` : user.display_name;
  }

  function syncParticipantDraft(ids: string[]) {
    const names = ids
      .map((userId) => users.find((user) => user.id === userId))
      .filter((user): user is UserRecord => Boolean(user))
      .map(participantLabel);
    setDraft((current) => ({ ...current, participants: names.join(', ') }));
  }

  function toggleDept(id: string) {
    const next = selectedDeptIds.includes(id)
      ? selectedDeptIds.filter((entry) => entry !== id)
      : [...selectedDeptIds, id];
    setSelectedDeptIds(next);
    const names = next.map((deptId) => departments.find((d) => d.id === deptId)?.name).filter(Boolean);
    setDraft((current) => ({ ...current, scope: names.join(', ') }));
    if (participantDeptFilter && next.length && !next.includes(participantDeptFilter)) {
      setParticipantDeptFilter('');
    }
    setSelectedParticipantIds((current) => {
      const allowed = current.filter((userId) => {
        const user = users.find((entry) => entry.id === userId);
        if (!user) return false;
        if (BLOCKED_PARTICIPANT_ROLES.has(user.role_id)) return false;
        if (!user.department || !user.position_id) return false;
        return next.length === 0 || next.includes(user.department);
      });
      syncParticipantDraft(allowed);
      return allowed;
    });
  }

  function toggleParticipant(id: string) {
    if (!eligibleParticipantIds.has(id)) {
      setMessage('참여자는 선택한 부서에 배정된 일반 업무 담당자만 고를 수 있습니다.');
      return;
    }
    const next = selectedParticipantIds.includes(id)
      ? selectedParticipantIds.filter((entry) => entry !== id)
      : [...selectedParticipantIds, id];
    setSelectedParticipantIds(next);
    syncParticipantDraft(next);
  }

  const refreshPlans = useCallback(async () => {
    const payload = await fetchProcessPlans();
    setPlans(payload.items);
    return payload.items;
  }, []);

  const loadPlan = useCallback(async (planId: string) => {
    const detail = await fetchProcessPlan(planId);
    setPlan(detail);
    return detail;
  }, []);

  useEffect(() => {
    void refreshPlans();
  }, [refreshPlans]);

  useEffect(() => {
    if (!plan || !selectedStepId) {
      setStepDraft(emptyStepDraft);
      return;
    }
    const step = plan.steps.find((item) => item.id === selectedStepId);
    if (step) {
      setStepDraft({
        title: step.title || '',
        notes: step.notes || '',
        owner_name: step.owner_name || '',
        priority: step.priority || 'normal',
        assignee_kind: step.assignee_kind || 'unassigned',
      });
    }
  }, [plan, selectedStepId]);

  async function generate() {
    setGenerating(true);
    setMessage('AI가 프로세스를 설계하는 중...');
    setJob({
      job_id: 'local-work-architecture',
      task: 'work_architecture',
      status: 'running',
      actor: '',
      input_summary: draft.objective,
      used_sources: [],
      result_path: '',
      error: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    try {
      const next = await generateWorkArchitecture(draft);
      setJob(next.ai_job ?? null);
      setMessage(`설계 완료: ${next.path}. 검토 후 승인하세요.`);
      await refreshPlans();
      if (next.plan?.id) {
        await loadPlan(next.plan.id);
        setShowMarkdown(true);
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : '업무 프로세스 설계 생성 실패';
      setMessage(detail);
      setJob((current) =>
        current ? { ...current, status: 'failed', error: detail, updated_at: new Date().toISOString() } : current,
      );
    } finally {
      setGenerating(false);
    }
  }

  const runStep = useCallback(
    async (step: ProcessPlanStep) => {
      if (!plan) return;
      busyRef.current = true;
      setJob({
        job_id: `local-step-${step.id}`,
        task: 'work_process_step',
        status: 'running',
        actor: '',
        input_summary: step.title,
        used_sources: step.source_architecture_id ? [step.source_architecture_id] : [],
        result_path: '',
        error: '',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
      try {
        const result = await runWorkScheduleItem(step.id);
        setJob(result.ai_job ?? null);
        setMessage(`단계 완료: ${result.result_path}`);
        await loadPlan(plan.id);
        await refreshPlans();
      } catch (err) {
        const detail = err instanceof Error ? err.message : '단계 실행 실패';
        setMessage(detail);
        setJob((current) =>
          current ? { ...current, status: 'failed', error: detail, updated_at: new Date().toISOString() } : current,
        );
      } finally {
        busyRef.current = false;
      }
    },
    [plan, loadPlan, refreshPlans],
  );

  // Auto driver: when approved/running + auto mode, run the next runnable step in order.
  useEffect(() => {
    if (!plan || busyRef.current) return;
    if (plan.mode !== 'auto') return;
    if (plan.status !== 'approved' && plan.status !== 'running') return;
    const nextStep = plan.steps.find((step) => step.runnable);
    if (!nextStep) return;
    void runStep(nextStep);
  }, [plan, runStep]);

  async function approve() {
    if (!plan) return;
    const updated = await approveProcessPlan(plan.id);
    setPlan(updated);
    await refreshPlans();
  }

  async function toggleMode() {
    if (!plan) return;
    const updated = await setProcessPlanMode(plan.id, plan.mode === 'auto' ? 'manual' : 'auto');
    setPlan(updated);
  }

  async function pauseOrResume() {
    if (!plan) return;
    const updated = plan.status === 'paused' ? await resumeProcessPlan(plan.id) : await pauseProcessPlan(plan.id);
    setPlan(updated);
    await refreshPlans();
  }

  async function saveStep() {
    if (!plan || !selectedStepId) return;
    const updated = await updateProcessStep(plan.id, selectedStepId, {
      title: stepDraft.title,
      notes: stepDraft.notes,
      owner_name: stepDraft.owner_name,
      assignee_kind: stepDraft.assignee_kind,
    });
    setPlan(updated);
  }

  async function signOffStep(step: ProcessPlanStep) {
    if (!plan) return;
    try {
      await signOffWorkItem(step.id);
      setMessage(`“${step.title}” 단계를 완료 서명했습니다.`);
      await loadPlan(plan.id);
      await refreshPlans();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '완료 서명 실패');
    }
  }

  async function addStep() {
    if (!plan) return;
    const updated = await addProcessStep(plan.id, { title: '새 단계' });
    setPlan(updated);
    await refreshPlans();
  }

  async function removeStep(stepId: string) {
    if (!plan) return;
    const updated = await deleteProcessStep(plan.id, stepId);
    setPlan(updated);
    if (selectedStepId === stepId) setSelectedStepId(null);
    await refreshPlans();
  }

  async function moveStep(stepId: string, direction: -1 | 1) {
    if (!plan) return;
    const ids = plan.steps.map((step) => step.id);
    const index = ids.indexOf(stepId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    const updated = await reorderProcessSteps(plan.id, ids);
    setPlan(updated);
  }

  const selectedStep = plan?.steps.find((step) => step.id === selectedStepId) ?? null;
  const canEdit = plan ? ['draft', 'approved', 'paused'].includes(plan.status) : false;

  return (
    <section className="page-grid">
      <div className="panel">
        <p className="eyebrow">Process Design</p>
        <h2>AI 업무 프로세스 설계</h2>
        <p className="muted">
          프로세스 설계는 계획(plan.md)을 실제로 굴리는 단계입니다. 어떤 인력(사람·AI)이 투입되고 기간은 어떻게 되는지
          구체화하고, 각 단계에 AI 자동화 기능과 담당을 배치합니다. 승인하면 단계가 순서대로 실행됩니다.
        </p>
        <div className="memory-form">
          {agentPlans.length ? (
            <label>
              계획(plan.md) 기반으로 시작
              <select defaultValue="" onChange={(event) => { seedFromAgentPlan(event.target.value); event.target.value = ''; }}>
                <option value="" disabled>
                  계획을 선택해 목표를 채웁니다
                </option>
                {agentPlans.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.title} ({entry.status})
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <input placeholder="자동화하려는 업무 목표" value={draft.objective} onChange={(event) => setDraft({ ...draft, objective: event.target.value })} />
          <label>
            포함할 부서
            {departments.length ? (
              <div className="collapsible-picker">
                <button
                  type="button"
                  className="collapsible-picker-header"
                  onClick={() => setDeptPickerOpen((open) => !open)}
                >
                  <span>{selectedDeptIds.length ? `${selectedDeptIds.length}개 부서 선택됨` : '부서 선택 열기'}</span>
                  <small>{deptPickerOpen ? '접기' : '펼치기'}</small>
                </button>
                {selectedDepartments.length ? (
                  <p className="muted small">선택: {selectedDepartments.map((entry) => entry.name).join(', ')}</p>
                ) : (
                  <p className="muted small">업무 범위에 포함할 부서를 먼저 고르면 참여자 후보도 해당 부서로 제한됩니다.</p>
                )}
                {deptPickerOpen ? (
                  <div className="chip-picker bounded-chip-picker">
                    {departments.map((entry) => (
                      <button
                        type="button"
                        key={entry.id}
                        className={selectedDeptIds.includes(entry.id) ? 'chip chip-active' : 'chip'}
                        onClick={() => toggleDept(entry.id)}
                      >
                        {entry.name}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <textarea placeholder="포함할 부서/업무 범위" value={draft.scope} onChange={(event) => setDraft({ ...draft, scope: event.target.value })} />
            )}
          </label>
          <input placeholder="기간" value={draft.horizon} onChange={(event) => setDraft({ ...draft, horizon: event.target.value })} />
          <label>
            참여자 (직급체계 기반 선택)
            {users.length ? (
              <div className="collapsible-picker">
                <button
                  type="button"
                  className="collapsible-picker-header"
                  onClick={() => setParticipantPickerOpen((open) => !open)}
                >
                  <span>
                    {selectedParticipantIds.length
                      ? `${selectedParticipantIds.length}명 참여자 선택됨`
                      : '업무 담당자 선택 열기'}
                  </span>
                  <small>{participantPickerOpen ? '접기' : '펼치기'}</small>
                </button>
                <p className="muted small">
                  시스템 관리자/조회자/부서·직급 미배정 사용자는 후보에서 제외됩니다. 부서를 선택하면 해당 부서 담당자만
                  고를 수 있습니다.
                </p>
                {draft.participants ? <p className="muted small">선택: {draft.participants}</p> : null}
                {participantPickerOpen ? (
                  <>
                    <div className="org-form-row">
                      <select value={participantDeptFilter} onChange={(event) => setParticipantDeptFilter(event.target.value)}>
                        <option value="">{selectedDeptIds.length ? '선택 부서 전체' : '전체 부서'}</option>
                        {participantDepartments.map((entry) => (
                          <option key={entry.id} value={entry.id}>{entry.name}</option>
                        ))}
                      </select>
                      <select value={participantPositionFilter} onChange={(event) => setParticipantPositionFilter(event.target.value)}>
                        <option value="">전체 직급</option>
                        {sortedPositions.map((entry) => (
                          <option key={entry.id} value={entry.id}>{entry.name}</option>
                        ))}
                      </select>
                    </div>
                    <div className="chip-picker bounded-chip-picker">
                      {filteredParticipants.length === 0 ? (
                        <span className="muted small">조건에 맞는 업무 담당자가 없습니다. 부서/직급 배정을 먼저 확인하세요.</span>
                      ) : null}
                      {filteredParticipants.map((entry) => (
                        <button
                          type="button"
                          key={entry.id}
                          className={selectedParticipantIds.includes(entry.id) ? 'chip chip-active' : 'chip'}
                          onClick={() => toggleParticipant(entry.id)}
                        >
                          {entry.display_name} · {positionName(entry.position_id)}
                        </button>
                      ))}
                    </div>
                  </>
                ) : null}
              </div>
            ) : (
              <textarea placeholder="참여자" value={draft.participants} onChange={(event) => setDraft({ ...draft, participants: event.target.value })} />
            )}
          </label>
          <textarea placeholder="제약" value={draft.constraints} onChange={(event) => setDraft({ ...draft, constraints: event.target.value })} />
          <label>
            <input type="checkbox" checked={draft.use_memory} onChange={(event) => setDraft({ ...draft, use_memory: event.target.checked })} />
            저장된 메모리 사용
          </label>
          <button type="button" disabled={generating} onClick={() => void generate()}>
            {generating ? '설계 중...' : 'AI가 업무 흐름 설계하기'}
          </button>
          {message ? <p className="muted">{message}</p> : null}
        </div>
        <AiJobStatusBar job={job} />

        <h3>프로세스 계획 목록</h3>
        <div className="compact-card-list bounded-list compact">
          {plans.length === 0 ? <p className="muted">아직 생성된 계획이 없습니다.</p> : null}
          {plans.map((item) => (
            <button
              key={item.id}
              type="button"
              className={'compact-list-card' + (plan?.id === item.id ? ' active' : '')}
              onClick={() => void loadPlan(item.id)}
            >
              <strong>{item.objective || '(제목 없음)'}</strong>
              <small>
                {STATUS_LABELS[item.status] || item.status} · {item.mode === 'auto' ? '자동' : '수동'} ·{' '}
                {item.step_done}/{item.step_total} 단계
              </small>
            </button>
          ))}
        </div>
      </div>

      <div className="panel">
        <p className="eyebrow">Process Control</p>
        {plan ? (
          <>
            <div className="plan-header">
              <h2>{plan.objective || '프로세스 계획'}</h2>
              <span className={`status-pill plan-status ${plan.status}`}>
                {STATUS_LABELS[plan.status] || plan.status}
              </span>
            </div>
            <div className="plan-controls">
              {plan.status === 'draft' || plan.status === 'paused' ? (
                <button type="button" className="primary" onClick={() => void approve()}>
                  승인
                </button>
              ) : null}
              <button type="button" className="secondary-button" onClick={() => void toggleMode()}>
                모드: {plan.mode === 'auto' ? '자동' : '수동'} (전환)
              </button>
              {plan.status === 'running' || plan.status === 'approved' ? (
                <button type="button" className="secondary-button" onClick={() => void pauseOrResume()}>
                  일시정지
                </button>
              ) : null}
              {plan.status === 'paused' ? (
                <button type="button" className="secondary-button" onClick={() => void pauseOrResume()}>
                  재개
                </button>
              ) : null}
              <button type="button" className="secondary-button" onClick={() => setShowMarkdown((value) => !value)}>
                {showMarkdown ? '계획 본문 숨기기' : '계획 본문 보기'}
              </button>
            </div>
            <p className="muted small">
              {plan.mode === 'auto'
                ? '자동 모드: 승인 후 다음 단계가 순서대로 자동 실행됩니다. 일시정지로 중단할 수 있습니다.'
                : '수동 모드: 각 단계를 직접 실행합니다.'}
            </p>

            {showMarkdown ? (
              <div className="bounded-preview">
                <pre>{plan.plan_markdown || '계획 본문을 불러올 수 없습니다.'}</pre>
              </div>
            ) : null}

            <ProcessGraph steps={plan.steps} selectedId={selectedStepId} onSelect={setSelectedStepId} />

            <div className="plan-step-toolbar">
              {canEdit ? (
                <button type="button" className="secondary-button" onClick={() => void addStep()}>
                  단계 추가
                </button>
              ) : null}
            </div>

            {selectedStep ? (
              <div className="plan-step-editor">
                <h3>단계 편집</h3>
                <p className="muted small">{selectedStep.stage_state || selectedStep.status}</p>
                <input
                  placeholder="단계 제목"
                  value={stepDraft.title}
                  disabled={!canEdit || selectedStep.status === 'done'}
                  onChange={(event) => setStepDraft({ ...stepDraft, title: event.target.value })}
                />
                <textarea
                  placeholder="단계 메모 (AI 자동화 기능/검토자/결과물)"
                  value={stepDraft.notes}
                  disabled={!canEdit || selectedStep.status === 'done'}
                  onChange={(event) => setStepDraft({ ...stepDraft, notes: event.target.value })}
                />
                <div className="form-grid">
                  <label>
                    담당 유형
                    <select
                      value={stepDraft.assignee_kind}
                      disabled={!canEdit || selectedStep.status === 'done'}
                      onChange={(event) => setStepDraft({ ...stepDraft, assignee_kind: event.target.value })}
                    >
                      <option value="unassigned">미지정</option>
                      <option value="human">사람</option>
                      <option value="ai">AI 모델</option>
                    </select>
                  </label>
                  <label>
                    담당자
                    {users.length ? (
                      <select
                        value={stepDraft.owner_name}
                        disabled={!canEdit || selectedStep.status === 'done'}
                        onChange={(event) => setStepDraft({ ...stepDraft, owner_name: event.target.value })}
                      >
                        <option value="">미지정</option>
                        {users.map((entry) => (
                          <option key={entry.id} value={entry.display_name}>
                            {participantLabel(entry)}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        placeholder="담당자 이름"
                        value={stepDraft.owner_name}
                        disabled={!canEdit || selectedStep.status === 'done'}
                        onChange={(event) => setStepDraft({ ...stepDraft, owner_name: event.target.value })}
                      />
                    )}
                  </label>
                </div>
                <p className="muted small">
                  담당: {ASSIGNEE_LABELS[selectedStep.assignee_kind || 'unassigned']}
                  {selectedStep.owner_name ? ` · ${selectedStep.owner_name}` : ''}
                  {selectedStep.signed_off_by
                    ? ` · ✔ 완료 서명: ${selectedStep.signed_off_by}`
                    : ''}
                </p>
                <div className="switch-row">
                  {canEdit && selectedStep.status !== 'done' ? (
                    <button type="button" className="primary" onClick={() => void saveStep()}>
                      저장
                    </button>
                  ) : null}
                  {canEdit ? (
                    <>
                      <button type="button" className="secondary-button" onClick={() => void moveStep(selectedStep.id, -1)}>
                        위로
                      </button>
                      <button type="button" className="secondary-button" onClick={() => void moveStep(selectedStep.id, 1)}>
                        아래로
                      </button>
                      <button type="button" className="secondary-button" onClick={() => void removeStep(selectedStep.id)}>
                        삭제
                      </button>
                    </>
                  ) : null}
                  {selectedStep.runnable && selectedStep.assignee_kind !== 'human' ? (
                    <button type="button" className="primary" disabled={busyRef.current} onClick={() => void runStep(selectedStep)}>
                      AI로 실행
                    </button>
                  ) : null}
                  {selectedStep.status !== 'done' && !selectedStep.signed_off_by ? (
                    <button type="button" className="secondary-button" onClick={() => void signOffStep(selectedStep)}>
                      완료 서명
                    </button>
                  ) : null}
                </div>
              </div>
            ) : (
              <p className="muted">그래프에서 단계를 클릭하면 내용을 보고 편집할 수 있습니다.</p>
            )}
          </>
        ) : (
          <p className="muted">왼쪽에서 계획을 선택하거나 새 프로세스를 설계하세요.</p>
        )}
      </div>
    </section>
  );
}
