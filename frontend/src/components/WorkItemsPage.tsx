import { useEffect, useState } from 'react';

import {
  fetchCurrentUser,
  fetchWorkItems,
  readArchiveDocument,
  runWorkScheduleItem,
  signOffWorkItem,
  type AiJobStatus,
  type AuthUser,
  type DocumentRead,
  type ProgressLog,
  type WorkItemsPayload,
} from '../api';
import AiJobStatusBar from './common/AiJobStatusBar';

export default function WorkItemsPage() {
  const [workItems, setWorkItems] = useState<WorkItemsPayload | null>(null);
  const [job, setJob] = useState<AiJobStatus | null>(null);
  const [runningId, setRunningId] = useState<string>('');
  const [message, setMessage] = useState('');
  const [me, setMe] = useState<AuthUser | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [signTarget, setSignTarget] = useState<string>('');
  const [signNote, setSignNote] = useState('');
  const [signing, setSigning] = useState(false);
  const [preview, setPreview] = useState<DocumentRead | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);

  async function refresh() {
    try {
      const payload = await fetchWorkItems();
      setWorkItems(payload);
    } catch {
      setWorkItems({ items: [], bottleneck_summary: '업무 현황을 불러오지 못했습니다.' });
    }
  }

  useEffect(() => {
    void refresh();
    void fetchCurrentUser()
      .then((current) => {
        setMe(current.user);
        const perms = current.user?.permissions ?? [];
        setIsAdmin(perms.includes('*') || perms.includes('admin:users'));
      })
      .catch(() => setMe(null));
  }, []);

  async function runStep(item: ProgressLog) {
    const itemId = item.id || item.path;
    setRunningId(itemId);
    setMessage('');
    setJob({
      job_id: `local-step-${itemId}`,
      task: 'work_process_step',
      status: 'running',
      actor: '',
      input_summary: item.title,
      used_sources: item.source_architecture_id ? [item.source_architecture_id] : [],
      result_path: '',
      error: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    try {
      const result = await runWorkScheduleItem(itemId);
      setJob(result.ai_job ?? null);
      setMessage(`단계 완료: ${result.result_path}`);
      await refresh();
    } catch (err) {
      const detail = err instanceof Error ? err.message : '단계 실행 실패';
      setMessage(detail);
      setJob((current) =>
        current ? { ...current, status: 'failed', error: detail, updated_at: new Date().toISOString() } : current,
      );
    } finally {
      setRunningId('');
    }
  }

  async function confirmSignOff(item: ProgressLog) {
    const itemId = item.id || item.path;
    setSigning(true);
    setMessage('');
    try {
      await signOffWorkItem(itemId, signNote.trim());
      setMessage(`완료 처리되었습니다: ${item.title}`);
      setSignTarget('');
      setSignNote('');
      await refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '완료 처리 실패');
    } finally {
      setSigning(false);
    }
  }

  async function openDocument(path: string) {
    if (!path.trim()) return;
    setPreviewLoading(true);
    setPreviewError('');
    try {
      const doc = await readArchiveDocument(path.trim());
      setPreview(doc);
    } catch (err) {
      setPreview(null);
      setPreviewError(err instanceof Error ? err.message : '문서를 불러오지 못했습니다.');
    } finally {
      setPreviewLoading(false);
    }
  }

  function renderDocumentButton(path: string, label = path) {
    if (!path) return <small className="muted">-</small>;
    return (
      <button className="link-button doc-path-button" type="button" onClick={() => void openDocument(path)}>
        {label}
      </button>
    );
  }

  const items = workItems?.items ?? [];
  const queueItems = items.filter((item) => item.source === 'queue');
  const logItems = items.filter((item) => item.source !== 'queue');

  const mineId = me?.id ?? '';
  const mineName = me?.display_name ?? '';
  const myItems = queueItems.filter(
    (item) =>
      (mineId && item.owner_id === mineId) || (mineName && item.owner_name === mineName),
  );
  const myOpen = myItems.filter((item) => item.status !== 'done');
  const myDone = myItems.filter((item) => item.status === 'done');

  return (
    <section className="panel">
      <p className="eyebrow">Work Items</p>
      <h2>내 업무 · 완료 처리</h2>
      <p className="muted">
        상사가 배정한 업무를 확인하고, 처리한 내용을 기록 파일로 남긴 뒤 “완료 확인”으로 마감하세요.
      </p>

      {!me ? (
        <p className="muted">로그인 정보를 불러오는 중...</p>
      ) : myItems.length === 0 ? (
        <p className="muted">내게 배정된 업무가 없습니다.</p>
      ) : (
        <div className="work-table">
          <div className="work-row work-header">
            <span>업무</span>
            <span>상태</span>
            <span>기록</span>
            <span>처리</span>
          </div>
          {myOpen.map((item) => {
            const itemId = item.id || item.path;
            return (
              <div className="work-row" key={itemId}>
                <span>
                  {item.title}
                  {item.notes ? <small className="muted">{item.notes}</small> : null}
                </span>
                <strong>{item.stage_state || item.status || '-'}</strong>
                <span>
                  {item.completion_record ? (
                    renderDocumentButton(item.completion_record)
                  ) : (
                    <small className="muted">기록 없음</small>
                  )}
                </span>
                <span className="work-actions">
                  {item.runnable ? (
                    <button type="button" disabled={Boolean(runningId)} onClick={() => void runStep(item)}>
                      {runningId === itemId ? '실행 중...' : 'AI로 실행'}
                    </button>
                  ) : null}
                  {signTarget === itemId ? (
                    <div className="signoff-box">
                      <textarea
                        rows={3}
                        placeholder="처리 내용을 기록하세요 (완료 기록 파일로 저장됩니다)"
                        value={signNote}
                        onChange={(event) => setSignNote(event.target.value)}
                      />
                      <div className="work-actions">
                        <button type="button" disabled={signing} onClick={() => void confirmSignOff(item)}>
                          {signing ? '처리 중...' : '완료 확인'}
                        </button>
                        <button type="button" className="ghost" onClick={() => setSignTarget('')}>
                          취소
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => {
                        setSignTarget(itemId);
                        setSignNote('');
                      }}
                    >
                      완료 처리
                    </button>
                  )}
                </span>
              </div>
            );
          })}
          {myDone.map((item) => (
            <div className="work-row" key={item.id || item.path}>
              <span>{item.title}</span>
              <strong>완료</strong>
              <span>
                {item.completion_record ? (
                  renderDocumentButton(item.completion_record)
                ) : (
                  <small className="muted">-</small>
                )}
              </span>
              <small className="muted">
                {item.signed_off_by ? `${item.signed_off_by} 확인` : '서명 없음'}
              </small>
            </div>
          ))}
        </div>
      )}

      <AiJobStatusBar job={job} />
      {message ? <p className="muted">{message}</p> : null}

      {isAdmin ? (
        <>
          <h3>업무 진행중인 사항 (관리자 전용)</h3>
          <p className="muted small">
            md 경로를 누르면 현재 AI/업무가 생성한 계획과 산출물을 바로 열람합니다.
          </p>
          <pre className="status-pre">{workItems?.bottleneck_summary ?? '병목 요약을 불러오는 중...'}</pre>

          <h3>프로세스 단계 큐</h3>
          {queueItems.length === 0 ? (
            <p className="muted">큐잉된 프로세스 단계가 없습니다. 프로세스 설계를 생성하면 단계가 순서대로 등록됩니다.</p>
          ) : (
            <div className="work-table">
              <div className="work-row work-header">
                <span>순서</span>
                <span>단계</span>
                <span>담당</span>
                <span>상태</span>
              </div>
              {queueItems.map((item) => (
                <div className="work-row" key={item.id || item.path}>
                  <span>{item.queue_order || '-'}</span>
                  <span>
                    {item.title}
                    {item.source_architecture_id ? (
                      <small className="muted">계획: {item.source_architecture_id}</small>
                    ) : null}
                    {item.completion_record ? (
                      <small>{renderDocumentButton(item.completion_record, `완료 기록: ${item.completion_record}`)}</small>
                    ) : null}
                  </span>
                  <span>{item.owner_name || '미지정'}</span>
                  <strong>{item.stage_state || item.status || '-'}</strong>
                </div>
              ))}
            </div>
          )}

          <h3>최근 업무 로그</h3>
          <div className="work-table">
            <div className="work-row work-header">
              <span>업무</span>
              <span>상태</span>
              <span>출처</span>
              <span>로그</span>
            </div>
            {logItems.length === 0 ? <p className="muted">표시할 업무 로그가 없습니다.</p> : null}
            {logItems.map((item) => (
              <div className="work-row" key={item.path}>
                <span>{item.summary || item.title}</span>
                <strong>{item.status || '-'}</strong>
                <span>{item.kind || item.source || '-'}</span>
                <small>{renderDocumentButton(item.path)}</small>
              </div>
            ))}
          </div>
          <div className="work-document-preview">
            <div className="work-document-preview-head">
              <div>
                <p className="eyebrow">Document Preview</p>
                <h3>진행 문서 미리보기</h3>
              </div>
              {preview ? <button className="ghost" type="button" onClick={() => setPreview(null)}>닫기</button> : null}
            </div>
            {previewLoading ? <p className="muted">문서를 불러오는 중...</p> : null}
            {previewError ? <p className="error-text small">{previewError}</p> : null}
            {preview ? (
              <>
                <p className="muted small">
                  {preview.path} · {preview.bytes.toLocaleString()} bytes · 수정 {preview.modified_at}
                </p>
                <pre className="status-pre">{preview.markdown}</pre>
              </>
            ) : !previewLoading ? (
              <p className="muted small">최근 업무 로그의 md 경로를 클릭하면 내용이 여기에 표시됩니다.</p>
            ) : null}
          </div>
        </>
      ) : (
        <p className="muted">전체 업무 진행 현황은 관리자만 열람할 수 있습니다.</p>
      )}
    </section>
  );
}
