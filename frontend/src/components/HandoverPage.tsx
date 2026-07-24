import { FormEvent, useEffect, useMemo, useState } from 'react';

import {
  createHandoverBrief,
  fetchOrgRoster,
  type AiJobStatus,
  type GeneratedDocument,
  type HandoverRequest,
  type OrgRoster,
  type UserRecord,
} from '../api';
import AiJobStatusBar from './common/AiJobStatusBar';

const emptyHandover: HandoverRequest = {
  work_title: '',
  outgoing_owner: '',
  incoming_owner: '',
  notes: '',
  generate_tasks: true,
};

export default function HandoverPage() {
  const [draft, setDraft] = useState<HandoverRequest>(emptyHandover);
  const [result, setResult] = useState<GeneratedDocument | null>(null);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<AiJobStatus | null>(null);
  const [roster, setRoster] = useState<OrgRoster | null>(null);
  const [outDept, setOutDept] = useState('');
  const [inDept, setInDept] = useState('');

  useEffect(() => {
    void fetchOrgRoster()
      .then(setRoster)
      .catch(() => setRoster(null));
  }, []);

  const deptName = useMemo(() => {
    const map = new Map<string, string>();
    (roster?.departments ?? []).forEach((dept) => map.set(dept.id, dept.name));
    return map;
  }, [roster]);

  const positionName = useMemo(() => {
    const map = new Map<string, string>();
    (roster?.positions ?? []).forEach((pos) => map.set(pos.id, pos.name));
    return map;
  }, [roster]);

  function userLabel(user: UserRecord): string {
    const parts = [user.display_name];
    const pos = user.position_id ? positionName.get(user.position_id) : '';
    const role = pos || user.title;
    if (role) parts.push(role);
    if (user.department) parts.push(deptName.get(user.department) ?? user.department);
    return parts.join(' · ');
  }

  function usersInDept(dept: string): UserRecord[] {
    const users = roster?.users ?? [];
    if (!dept) return users;
    return users.filter((user) => (user.department || '') === dept);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setJob({
      job_id: 'local-handover',
      task: 'handover',
      status: 'queued',
      actor: '',
      input_summary: draft.work_title,
      used_sources: [],
      result_path: '',
      error: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    try {
      setJob((current) => current ? { ...current, status: 'running', updated_at: new Date().toISOString() } : current);
      const next = await createHandoverBrief(draft);
      setResult(next);
      setJob(next.ai_job ?? null);
    } catch (err) {
      setJob((current) =>
        current
          ? {
              ...current,
              status: 'failed',
              error: err instanceof Error ? err.message : '인수인계 문서 생성 실패',
              updated_at: new Date().toISOString(),
            }
          : current,
      );
    } finally {
      setBusy(false);
    }
  }

  const hasRoster = (roster?.users.length ?? 0) > 0;

  return (
    <section className="page-grid">
      <div className="panel">
        <p className="eyebrow">Handover</p>
        <h2>인수인계 문서 생성</h2>
        <p className="muted">
          담당자가 바뀌거나 퇴사할 때, 기존 담당자의 활동 로그(담당 작업·AI 작업 실행·활동 기록)를 자동으로 수집해
          인수인계 문서를 만들고, 신규 담당자가 바로 착수할 업무를 작업 스케줄에 등록합니다. 부서와 직급으로 담당자를
          선택해 혼선을 줄이세요.
        </p>
        <form className="memory-form" onSubmit={handleSubmit}>
          <label>
            업무명
            <input
              value={draft.work_title}
              placeholder="예: Discord 문서 접수 자동화"
              onChange={(event) => setDraft({ ...draft, work_title: event.target.value })}
            />
          </label>

          {hasRoster ? (
            <>
              <div className="field-row">
                <label>
                  기존 담당자 부서
                  <select value={outDept} onChange={(event) => setOutDept(event.target.value)}>
                    <option value="">전체 부서</option>
                    {(roster?.departments ?? []).map((dept) => (
                      <option key={dept.id} value={dept.id}>
                        {dept.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  기존 담당자 (퇴사자)
                  <select
                    value={draft.outgoing_owner}
                    onChange={(event) => setDraft({ ...draft, outgoing_owner: event.target.value })}
                  >
                    <option value="">선택하세요</option>
                    {usersInDept(outDept).map((user) => (
                      <option key={user.id} value={user.id}>
                        {userLabel(user)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="field-row">
                <label>
                  신규 담당자 부서
                  <select value={inDept} onChange={(event) => setInDept(event.target.value)}>
                    <option value="">전체 부서</option>
                    {(roster?.departments ?? []).map((dept) => (
                      <option key={dept.id} value={dept.id}>
                        {dept.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  신규 담당자
                  <select
                    value={draft.incoming_owner}
                    onChange={(event) => setDraft({ ...draft, incoming_owner: event.target.value })}
                  >
                    <option value="">선택하세요</option>
                    {usersInDept(inDept).map((user) => (
                      <option key={user.id} value={user.id}>
                        {userLabel(user)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </>
          ) : (
            <>
              <label>
                기존 담당자
                <input
                  value={draft.outgoing_owner}
                  placeholder="사번 또는 이름"
                  onChange={(event) => setDraft({ ...draft, outgoing_owner: event.target.value })}
                />
              </label>
              <label>
                신규 담당자
                <input
                  value={draft.incoming_owner}
                  placeholder="사번 또는 이름"
                  onChange={(event) => setDraft({ ...draft, incoming_owner: event.target.value })}
                />
              </label>
            </>
          )}

          <label>
            추가 메모
            <textarea
              value={draft.notes}
              placeholder="예: 최근 막힌 지점, 중요한 고객, 반복 실수"
              onChange={(event) => setDraft({ ...draft, notes: event.target.value })}
            />
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={draft.generate_tasks ?? true}
              onChange={(event) => setDraft({ ...draft, generate_tasks: event.target.checked })}
            />
            활동 로그 기반 인수 업무를 작업 스케줄에 자동 등록
          </label>
          <button disabled={busy} type="submit">{busy ? '생성 중...' : '인수인계 문서 생성'}</button>
        </form>
        <AiJobStatusBar job={job} />
      </div>
      <div className="panel">
        <p className="eyebrow">Generated</p>
        <h2>문서 결과</h2>
        {result ? (
          <>
            <p className="muted">저장 위치: {result.path}</p>
            <pre className="status-pre">{result.markdown}</pre>
          </>
        ) : (
          <p className="muted">아직 생성된 문서가 없습니다.</p>
        )}
      </div>
    </section>
  );
}
