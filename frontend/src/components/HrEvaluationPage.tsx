import { useEffect, useMemo, useState } from 'react';

import {
  draftHrEvaluation,
  fetchAccessControl,
  fetchHrEvaluationContext,
  fetchHrEvaluationRecords,
  fetchWorkSchedule,
  readArchiveDocument,
  saveHrEvaluation,
  type DepartmentRecord,
  type DocumentRead,
  type HrEvaluationRecord,
  type PositionRecord,
  type UserRecord,
  type WorkScheduleItem,
} from '../api';

export default function HrEvaluationPage() {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [positions, setPositions] = useState<PositionRecord[]>([]);
  const [workItems, setWorkItems] = useState<WorkScheduleItem[]>([]);
  const [records, setRecords] = useState<HrEvaluationRecord[]>([]);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [departmentFilter, setDepartmentFilter] = useState('');
  const [positionFilter, setPositionFilter] = useState('');
  const [titleFilter, setTitleFilter] = useState('');
  const [selectedWorkIds, setSelectedWorkIds] = useState<string[]>([]);
  const [period, setPeriod] = useState('');
  const [criteria, setCriteria] = useState('');
  const [notes, setNotes] = useState('');
  const [context, setContext] = useState<Record<string, unknown> | null>(null);
  const [draft, setDraft] = useState('');
  const [finalText, setFinalText] = useState('');
  const [openedRecordDoc, setOpenedRecordDoc] = useState<DocumentRead | null>(null);
  const [message, setMessage] = useState('');
  const selectedUser = useMemo(
    () => users.find((entry) => entry.id === selectedUserId),
    [selectedUserId, users],
  );
  const selectedDepartment = useMemo(
    () => departments.find((entry) => entry.id === selectedUser?.department),
    [departments, selectedUser?.department],
  );
  const selectedPosition = useMemo(
    () => positions.find((entry) => entry.id === selectedUser?.position_id),
    [positions, selectedUser?.position_id],
  );
  const filteredUsers = useMemo(() => {
    const query = titleFilter.trim().toLowerCase();
    return users.filter((user) => {
      const matchesDepartment = !departmentFilter || user.department === departmentFilter;
      const matchesPosition = !positionFilter || user.position_id === positionFilter;
      const matchesTitle =
        !query ||
        user.title.toLowerCase().includes(query) ||
        user.display_name.toLowerCase().includes(query) ||
        user.id.toLowerCase().includes(query);
      return matchesDepartment && matchesPosition && matchesTitle;
    });
  }, [departmentFilter, positionFilter, titleFilter, users]);
  const relatedWorkItems = useMemo(() => {
    if (!selectedUser) return workItems;
    const names = new Set([selectedUser.id, selectedUser.display_name].filter(Boolean));
    return workItems.filter(
      (item) =>
        selectedWorkIds.includes(item.id) ||
        item.owner_id === selectedUser.id ||
        item.assignee_kind === selectedUser.id ||
        names.has(item.owner_name),
    );
  }, [selectedUser, selectedWorkIds, workItems]);

  useEffect(() => {
    void (async () => {
      const [acl, work, saved] = await Promise.all([
        fetchAccessControl(),
        fetchWorkSchedule(),
        fetchHrEvaluationRecords(),
      ]);
      setUsers(acl.users ?? []);
      setDepartments(acl.departments ?? []);
      setPositions(acl.positions ?? []);
      setWorkItems(work.items ?? []);
      setRecords(saved.records ?? []);
    })().catch((err) => setMessage(err instanceof Error ? err.message : '인사평가 데이터 로드 실패'));
  }, []);

  async function loadContext() {
    if (!selectedUserId) {
      setMessage('평가 대상 직원을 선택하세요.');
      return;
    }
    try {
      setContext(await fetchHrEvaluationContext(selectedUserId));
      const saved = await fetchHrEvaluationRecords(selectedUserId);
      setRecords(saved.records ?? []);
      setMessage('업무 로그와 과거 기록을 불러왔습니다.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '평가 context 로드 실패');
    }
  }

  async function generateDraft() {
    if (!selectedUserId) {
      setMessage('평가 대상 직원을 선택하세요.');
      return;
    }
    try {
      const result = await draftHrEvaluation({
        user_id: selectedUserId,
        period,
        work_item_ids: selectedWorkIds,
        criteria,
        notes,
      });
      setContext(result.context);
      setDraft(result.draft);
      setFinalText(result.draft);
      setMessage('AI 평가 초안을 생성했습니다. 저장 전 문구를 수정하세요.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'AI 평가 초안 생성 실패');
    }
  }

  async function saveFinal() {
    if (!selectedUserId || !finalText.trim()) {
      setMessage('직원과 최종 평가 내용을 확인하세요.');
      return;
    }
    try {
      const sourceRefs = (context?.source_refs as string[] | undefined) ?? [];
      const result = await saveHrEvaluation({
        user_id: selectedUserId,
        period,
        work_item_ids: selectedWorkIds,
        criteria,
        notes,
        draft,
        final_text: finalText,
        evidence: notes,
        source_refs: sourceRefs,
      });
      setRecords([result.record, ...records]);
      if (result.record.document_path) {
        setOpenedRecordDoc(await readArchiveDocument(result.record.document_path));
      }
      setMessage('인사평가 기록을 저장했습니다. 문서 열람과 영구메모리에도 반영됩니다.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '인사평가 저장 실패');
    }
  }

  async function openEvaluationDocument(path?: string) {
    if (!path) {
      setMessage('이전 형식의 평가 기록이라 문서 경로가 없습니다.');
      return;
    }
    try {
      setOpenedRecordDoc(await readArchiveDocument(path));
      setMessage(`평가 문서를 열었습니다: ${path}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '평가 문서 열람 실패');
    }
  }

  return (
    <section className="page-grid">
      <div className="panel">
        <p className="eyebrow">HR evaluation</p>
        <h2>인사평가</h2>
        <p className="muted">
          직원과 진행 업무를 선택하면 네고티움의 업무 로그를 근거로 AI 평가 초안을 만들고, 관리자가 수정한 최종본을 저장합니다.
        </p>
        <div className="memory-form">
          <div className="org-form-row">
            <label>
              부서로 좁히기
              <select
                value={departmentFilter}
                onChange={(event) => {
                  setDepartmentFilter(event.target.value);
                  setSelectedUserId('');
                  setSelectedWorkIds([]);
                  setContext(null);
                }}
              >
                <option value="">전체 부서</option>
                {departments.map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              직급으로 좁히기
              <select
                value={positionFilter}
                onChange={(event) => {
                  setPositionFilter(event.target.value);
                  setSelectedUserId('');
                  setSelectedWorkIds([]);
                  setContext(null);
                }}
              >
                <option value="">전체 직급</option>
                {positions.map((position) => (
                  <option key={position.id} value={position.id}>
                    {position.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            직함/이름 검색
            <input
              placeholder="예: 팀장, 대리, 이름, 사번"
              value={titleFilter}
              onChange={(event) => {
                setTitleFilter(event.target.value);
                setSelectedUserId('');
                setSelectedWorkIds([]);
                setContext(null);
              }}
            />
          </label>
          <label>
            평가 대상 직원 ({filteredUsers.length}명)
            <select
              value={selectedUserId}
              onChange={(event) => {
                setSelectedUserId(event.target.value);
                setSelectedWorkIds([]);
                setContext(null);
              }}
            >
              <option value="">직원 선택</option>
              {filteredUsers.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.display_name} · {user.title || '직함 없음'} · {user.id}
                </option>
              ))}
            </select>
            <small className="muted">부서와 직급, 직함/이름 검색으로 먼저 좁힌 뒤 직원을 선택하세요.</small>
          </label>
          {selectedUser ? (
            <div className="org-card compact-card">
              <strong>{selectedUser.display_name}</strong>
              <p className="muted">
                부서 {selectedDepartment?.name ?? selectedUser.department ?? '미배정'} · 직급{' '}
                {selectedPosition?.name ?? selectedUser.position_id ?? '미지정'} · 상태{' '}
                {selectedUser.active === false ? '비활성' : '활성'}
              </p>
            </div>
          ) : null}
          <input
            placeholder="평가 기간 (예: 2026 Q2)"
            value={period}
            onChange={(event) => setPeriod(event.target.value)}
          />
          <textarea
            placeholder="평가 기준"
            value={criteria}
            onChange={(event) => setCriteria(event.target.value)}
          />
          <label>
            진행 업무 선택
            <select
              multiple
              value={selectedWorkIds}
              onChange={(event) =>
                setSelectedWorkIds(Array.from(event.target.selectedOptions).map((option) => option.value))
              }
            >
              {relatedWorkItems.map((item) => (
                <option key={item.id} value={item.id}>
                  [{item.status}] {item.title} · 담당 {item.owner_name || item.owner_id || '미지정'}
                </option>
              ))}
            </select>
            <small className="muted">
              선택한 직원의 담당 작업을 우선 표시합니다. 없으면 업무 배정 화면에서 작업을 추가하세요.
            </small>
          </label>
          <textarea
            placeholder="관리자 추가 메모/근거"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
          <div className="form-actions">
            <button type="button" className="secondary-button" onClick={() => void loadContext()}>
              과거 작업 로그 불러오기
            </button>
            <button type="button" onClick={() => void generateDraft()}>AI 평가 초안 생성</button>
          </div>
        </div>
      </div>
      <div className="panel">
        <p className="eyebrow">Evidence</p>
        <h2>로그 요약</h2>
        <p className="muted">{selectedUser ? `${selectedUser.display_name}의 평가 context` : '직원을 선택하세요.'}</p>
        <pre>{context ? JSON.stringify(context, null, 2) : '아직 불러온 로그가 없습니다.'}</pre>
      </div>
      <div className="panel">
        <p className="eyebrow">Draft editor</p>
        <h2>평가 초안 수정/저장</h2>
        <textarea
          className="large-textarea"
          value={finalText}
          placeholder="AI 초안 생성 후 관리자가 문구와 근거를 수정하세요."
          onChange={(event) => setFinalText(event.target.value)}
        />
        <button type="button" onClick={() => void saveFinal()}>수정본 저장</button>
        <p className="muted small">
          저장된 평가서는 archive/hr/evaluations 아래 Markdown 문서로 생성되어 문서 열람과 영구메모리에 자동 반영됩니다.
        </p>
      </div>
      {openedRecordDoc ? (
        <div className="panel">
          <p className="eyebrow">{openedRecordDoc.path}</p>
          <h2>저장된 평가 문서</h2>
          <div className="bounded-preview">
            <pre>{openedRecordDoc.markdown}</pre>
          </div>
        </div>
      ) : null}
      <div className="panel">
        <p className="eyebrow">Records</p>
        <h2>평가 기록</h2>
        <div className="org-list">
          {records.map((record) => (
            <article className="org-card" key={record.id}>
              <strong>{record.period || '기간 미지정'} · {record.user_id}</strong>
              <p className="muted">{record.created_at} · 작성 {record.created_by}</p>
              {record.document_path ? <p className="muted small">문서: {record.document_path}</p> : null}
              <pre>{record.final_text}</pre>
              <button
                type="button"
                className="secondary-button"
                disabled={!record.document_path}
                onClick={() => void openEvaluationDocument(record.document_path)}
              >
                평가 문서 열기
              </button>
            </article>
          ))}
          {records.length === 0 ? <p className="muted">저장된 평가 기록이 없습니다.</p> : null}
        </div>
      </div>
      {message ? <p className="muted org-message">{message}</p> : null}
    </section>
  );
}
