import { useEffect, useState } from 'react';

import {
  createWorkScheduleItem,
  deleteWorkScheduleItem,
  fetchAssignmentScope,
  fetchWorkSchedule,
  generateWorkSchedule,
  updateWorkScheduleItem,
  type AiJobStatus,
  type AssignmentScope,
  type DepartmentRecord,
  type UserRecord,
  type WorkScheduleItem,
} from '../api';
import AiJobStatusBar from './common/AiJobStatusBar';

const emptyItem: WorkScheduleItem = {
  id: '',
  title: '',
  owner_id: '',
  owner_name: '',
  status: 'todo',
  priority: 'normal',
  start_date: '',
  due_date: '',
  dependencies: [],
  notes: '',
  source_architecture_id: '',
};

export default function WorkSchedulePage() {
  const [items, setItems] = useState<WorkScheduleItem[]>([]);
  const [draft, setDraft] = useState<WorkScheduleItem>(emptyItem);
  const [generator, setGenerator] = useState({ objective: '', participants: '', horizon: '', constraints: '' });
  const [message, setMessage] = useState('');
  const [job, setJob] = useState<AiJobStatus | null>(null);
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [participantIds, setParticipantIds] = useState<string[]>([]);
  const [selectedDept, setSelectedDept] = useState('');
  const [scope, setScope] = useState<AssignmentScope | null>(null);

  const filteredUsers = selectedDept
    ? users.filter((user) => (user.department ?? '') === selectedDept)
    : users;

  async function refresh() {
    const payload = await fetchWorkSchedule();
    setItems(payload.items);
  }

  async function loadOrg() {
    try {
      const next = await fetchAssignmentScope();
      setScope(next);
      setUsers(next.assignable_users.filter((user) => user.active !== false));
      setDepartments(next.departments ?? []);
    } catch {
      setUsers([]);
      setScope(null);
    }
  }

  useEffect(() => {
    void refresh();
    void loadOrg();
  }, []);

  function deptName(id?: string): string {
    if (!id) return '부서 미배정';
    return departments.find((entry) => entry.id === id)?.name ?? '부서 미배정';
  }

  function pickOwner(userId: string) {
    const user = users.find((entry) => entry.id === userId);
    setDraft({ ...draft, owner_id: userId, owner_name: user?.display_name ?? '' });
  }

  function changeDept(deptId: string) {
    setSelectedDept(deptId);
    if (deptId && draft.owner_id) {
      const owner = users.find((entry) => entry.id === draft.owner_id);
      if (owner && (owner.department ?? '') !== deptId) {
        setDraft((current) => ({ ...current, owner_id: '', owner_name: '' }));
      }
    }
    setParticipantIds((current) =>
      deptId
        ? current.filter((id) => (users.find((user) => user.id === id)?.department ?? '') === deptId)
        : current,
    );
  }

  function toggleParticipant(userId: string) {
    setParticipantIds((current) =>
      current.includes(userId) ? current.filter((id) => id !== userId) : [...current, userId],
    );
  }

  async function save() {
    const result = draft.id ? await updateWorkScheduleItem(draft) : await createWorkScheduleItem(draft);
    setItems(result.items);
    setDraft(emptyItem);
  }

  async function generate() {
    const participantNames = participantIds
      .map((id) => users.find((user) => user.id === id)?.display_name)
      .filter(Boolean)
      .join(', ');
    const participants = participantNames || generator.participants;
    setJob({
      job_id: 'local-work-schedule',
      task: 'work_schedule.generate',
      status: 'queued',
      actor: '',
      input_summary: generator.objective,
      used_sources: [],
      result_path: '',
      error: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    try {
      setJob((current) => current ? { ...current, status: 'running', updated_at: new Date().toISOString() } : current);
      const doc = await generateWorkSchedule({ ...generator, participants });
      setJob(doc.ai_job ?? null);
      setMessage(`AI 스케줄 문서 저장됨: ${doc.path}`);
      await refresh();
    } catch (err) {
      setJob((current) =>
        current
          ? {
              ...current,
              status: 'failed',
              error: err instanceof Error ? err.message : 'AI 스케줄 생성 실패',
              updated_at: new Date().toISOString(),
            }
          : current,
      );
      setMessage(err instanceof Error ? err.message : 'AI 스케줄 생성 실패');
    }
  }

  return (
    <section className="page-grid">
      <div className="panel">
        <p className="eyebrow">Office Work · 업무 배정</p>
        <h2>업무 배정 · 완료 확인</h2>
        <p className="muted">
          상사가 자기 부서/하위 직급 사원에게 업무를 배정합니다. 조직을 고르면 해당 부서 소속 사원만 불러옵니다.
          배정된 사원은 “업무 현황 &gt; 내 업무”에서 처리 내용을 기록 파일로 남기고 완료 확인합니다. 사원/부서 등록은 인사관리에서 합니다.
        </p>
        {scope ? (
          <p className="muted small">
            {scope.scope === 'all'
              ? '배정 권한: 전체 부서 (대표/관리자 등급)'
              : scope.scope === 'department'
                ? `배정 권한: 담당 부서(하위 포함) ${scope.departments.length}개 — 매니저 등급`
                : '배정 권한 없음: 등급이 매니저 미만이거나 소속 부서가 없어 다른 사원에게 배정할 수 없습니다.'}
          </p>
        ) : null}
        <div className="memory-form org-form">
          <label>
            업무 제목
            <input placeholder="업무 제목" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
          </label>
          <label>
            조직 선택
            <select value={selectedDept} onChange={(event) => changeDept(event.target.value)}>
              <option value="">전체 조직</option>
              {departments.map((dept) => (
                <option key={dept.id} value={dept.id}>{dept.name}</option>
              ))}
            </select>
          </label>
          <label>
            담당 사원
            {users.length ? (
              <select value={draft.owner_id} onChange={(event) => pickOwner(event.target.value)}>
                <option value="">담당자 미지정</option>
                {filteredUsers.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.display_name} · {deptName(user.department)}
                  </option>
                ))}
              </select>
            ) : (
              <input placeholder="담당자" value={draft.owner_name} onChange={(event) => setDraft({ ...draft, owner_name: event.target.value, owner_id: '' })} />
            )}
          </label>
          <div className="org-form-row">
            <label>
              상태
              <select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}>
                <option value="todo">todo</option>
                <option value="in_progress">in_progress</option>
                <option value="blocked">blocked</option>
                <option value="done">done</option>
                <option value="cancelled">cancelled</option>
              </select>
            </label>
            <label>
              우선순위
              <select value={draft.priority} onChange={(event) => setDraft({ ...draft, priority: event.target.value })}>
                <option value="low">low</option>
                <option value="normal">normal</option>
                <option value="high">high</option>
                <option value="urgent">urgent</option>
              </select>
            </label>
          </div>
          <div className="org-form-row">
            <label>
              시작일
              <input placeholder="YYYY-MM-DD" value={draft.start_date} onChange={(event) => setDraft({ ...draft, start_date: event.target.value })} />
            </label>
            <label>
              마감일
              <input placeholder="YYYY-MM-DD" value={draft.due_date} onChange={(event) => setDraft({ ...draft, due_date: event.target.value })} />
            </label>
          </div>
          <label>
            메모
            <textarea placeholder="메모" value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} />
          </label>
          <div className="form-actions">
            <button type="button" onClick={() => void save()}>{draft.id ? '수정' : '추가'}</button>
            {draft.id ? <button type="button" className="secondary-button" onClick={() => setDraft(emptyItem)}>초기화</button> : null}
          </div>
        </div>
        <div className="org-list">
          {items.map((item) => (
            <article className="org-card" key={item.id}>
              <div className="org-card-head">
                <strong>{item.title}</strong>
                <span className="status-pill">{item.status}</span>
              </div>
              <p className="muted">{item.owner_name || '담당자 미지정'} · {item.priority} · {item.due_date || '마감 미정'}</p>
              {item.signed_off_by ? (
                <p className="muted small">
                  담당자 확인: {item.signed_off_by}
                  {item.signed_off_at ? ` · ${item.signed_off_at.slice(0, 10)}` : ''}
                </p>
              ) : (
                <p className="muted small">담당자 완료 확인 대기 중</p>
              )}
              {item.completion_record ? (
                <p className="muted small">완료 기록 파일: {item.completion_record}</p>
              ) : null}
              <div className="form-actions">
                <button className="secondary-button" type="button" onClick={() => setDraft(item)}>편집</button>
                <button className="secondary-button" type="button" onClick={() => deleteWorkScheduleItem(item.id).then((result) => setItems(result.items))}>삭제</button>
              </div>
            </article>
          ))}
        </div>
      </div>
      <div className="panel">
        <p className="eyebrow">AI Scheduler</p>
        <h2>AI가 업무 작성</h2>
        <p className="muted">목표·참여자·기간을 주면 AI가 업무 항목을 작성해 아래 배정 목록에 등록합니다.</p>
        <div className="memory-form org-form">
          <label>
            목표
            <input placeholder="목표" value={generator.objective} onChange={(event) => setGenerator({ ...generator, objective: event.target.value })} />
          </label>
          <label>
            참여 사원 선택
            {users.length ? (
              <div className="chip-picker">
                {filteredUsers.map((user) => (
                  <button
                    type="button"
                    key={user.id}
                    className={participantIds.includes(user.id) ? 'chip chip-active' : 'chip'}
                    onClick={() => toggleParticipant(user.id)}
                  >
                    {user.display_name}
                  </button>
                ))}
              </div>
            ) : (
              <textarea placeholder="참여자" value={generator.participants} onChange={(event) => setGenerator({ ...generator, participants: event.target.value })} />
            )}
          </label>
          <label>
            기간
            <input placeholder="예: 2주" value={generator.horizon} onChange={(event) => setGenerator({ ...generator, horizon: event.target.value })} />
          </label>
          <label>
            제약
            <textarea placeholder="제약" value={generator.constraints} onChange={(event) => setGenerator({ ...generator, constraints: event.target.value })} />
          </label>
          <button type="button" onClick={() => void generate()}>AI 스케줄 생성</button>
          {message ? <p className="muted">{message}</p> : null}
        </div>
        <AiJobStatusBar job={job} />
      </div>
    </section>
  );
}
