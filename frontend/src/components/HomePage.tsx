import { useEffect, useState, type ReactElement } from 'react';

import {
  createWorkScheduleItem,
  generateHandoverDraft,
  generateWeeklyDraft,
  fetchCompanyReportStatus,
  fetchOrgRoster,
  fetchWorkSchedule,
  generateCompanyReport,
  previewScannedDocument,
  saveReportSchedule,
  setReportItemStatus,
  type ApiStatus,
  type AuthUser,
  type CompanyReport,
  type OperationsMemory,
  type ReportInterval,
  type ReportItem,
  type WorkScheduleItem,
} from '../api';
import Button from './common/Button';
import FormActions from './common/FormActions';

type SectionKey = 'progressed' | 'attention' | 'quiet' | 'people' | 'money';

const ICONS: Record<SectionKey, ReactElement> = {
  progressed: (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
      <path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  attention: (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
      <path d="M8 2 15 14H1L8 2Z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M8 6.5v3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="8" cy="12" r="0.9" fill="currentColor" />
    </svg>
  ),
  quiet: (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
      <path d="M5 3v10M11 3v10" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  ),
  people: (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
      <circle cx="5.5" cy="5.5" r="2.4" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M1.5 13.5c.6-2.6 2.1-3.9 4-3.9s3.4 1.3 4 3.9" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="11.5" cy="5.5" r="2" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10.5 9.8c2 0 3.5 1.2 4 3.7" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
  money: (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
      <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M5.5 6.2h5M5.5 8h5M6 10.2c.5.8 1.2 1.2 2 1.2 1.2 0 2.2-.9 2.2-2.4S9.2 6.6 8 6.6" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),
};

const SECTIONS: Array<[SectionKey, string]> = [
  ['progressed', '진행된 일'],
  ['attention', '신경 쓸 일'],
  ['quiet', '소식이 없는 일'],
  ['people', '인력 신호'],
  ['money', '돈 관련 언급'],
];

const ADMIN_SHORTCUTS: Array<[string, string, string]> = [
  ['personnel', '인사관리', '조직도, 직급, 직원 배정과 인사평가'],
  ['work', '업무 현황', '진행 중인 업무와 병목 요약'],
  ['documents', '문서 만들기', '회의록, 보고서, 업무 요청서 생성'],
  ['admin', '시스템 설정', 'API 키, 감사 로그, 데이터 관리'],
];

// Status palette validated with the dataviz six-checks script for both themes
// (order matters: 완료 → 대기 → 진행 중 → 지연 keeps adjacent pairs CVD-safe).
const STATUS_ORDER: Array<{ key: string; label: string; varName: string; match: (s: string) => boolean }> = [
  { key: 'done', label: '완료', varName: '--viz-done', match: (s) => /완료|done|closed/i.test(s) },
  { key: 'waiting', label: '대기', varName: '--viz-waiting', match: (s) => /대기|보류|pending|todo|planned/i.test(s) },
  { key: 'progress', label: '진행 중', varName: '--viz-progress', match: () => true },
  { key: 'late', label: '기한 임박·지연', varName: '--viz-late', match: () => false },
];

function normalizeItems(value: Array<ReportItem | string> | undefined): ReportItem[] {
  return (value || []).map((item) =>
    typeof item === 'string' ? { text: item, sources: [] } : { text: item.text, sources: item.sources || [] },
  );
}

function isDueSoon(item: WorkScheduleItem): boolean {
  if (!item.due_date || /완료|done/i.test(item.status || '')) return false;
  const due = new Date(item.due_date);
  if (Number.isNaN(due.getTime())) return false;
  const days = (due.getTime() - Date.now()) / 86_400_000;
  return days <= 7;
}

export default function HomePage({
  memory,
  user,
  onAction,
}: {
  memory: OperationsMemory;
  status: ApiStatus | null;
  user: AuthUser;
  onAction: (page: string) => void;
}) {
  const permissions = user.permissions || [];
  const isAdmin = permissions.includes('*') || permissions.includes('admin:users');
  const [report, setReport] = useState<CompanyReport | null>(null);
  const [loadingReport, setLoadingReport] = useState(true);
  const [interval, setIntervalValue] = useState<ReportInterval>('off');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [workItems, setWorkItems] = useState<WorkScheduleItem[]>([]);
  const [employeeCount, setEmployeeCount] = useState<number | null>(null);
  const [docPreview, setDocPreview] = useState<{ filename: string; text: string } | null>(null);
  const [resolved, setResolved] = useState<Set<string>>(new Set());
  const [draftText, setDraftText] = useState<{ title: string; markdown: string } | null>(null);
  const [draftBusy, setDraftBusy] = useState(false);
  const [handoverName, setHandoverName] = useState('');

  function showToast(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(''), 3500);
  }

  useEffect(() => {
    fetchWorkSchedule()
      .then((payload) => setWorkItems(payload.items))
      .catch(() => setWorkItems([]));
    if (!isAdmin) {
      setLoadingReport(false);
      return;
    }
    fetchOrgRoster()
      .then((roster) => setEmployeeCount(roster.users.length))
      .catch(() => setEmployeeCount(null));
    fetchCompanyReportStatus()
      .then((reportStatus) => {
        const latest =
          reportStatus.report && Object.keys(reportStatus.report).length ? reportStatus.report : null;
        setReport(latest);
        setIntervalValue(reportStatus.schedule?.interval || 'off');
        setLoadingReport(false);
        if (reportStatus.is_due) {
          void refreshReport();
        }
      })
      .catch(() => setLoadingReport(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  async function refreshReport() {
    setBusy(true);
    try {
      setReport(await generateCompanyReport());
      showToast('새 리포트를 만들었습니다.');
    } catch (err) {
      showToast(err instanceof Error ? err.message : '리포트 생성 실패');
    } finally {
      setBusy(false);
    }
  }

  async function changeInterval(next: ReportInterval) {
    setIntervalValue(next);
    try {
      await saveReportSchedule(next);
      showToast('자동 갱신 주기를 저장했습니다.');
    } catch (err) {
      showToast(err instanceof Error ? err.message : '주기 저장 실패');
    }
  }

  async function openDocument(path: string) {
    try {
      const doc = await previewScannedDocument(path);
      setDocPreview({ filename: doc.filename, text: doc.text });
    } catch (err) {
      showToast(err instanceof Error ? err.message : '문서를 열 수 없습니다.');
    }
  }

  async function resolveItem(text: string, itemStatus: 'done' | 'dismissed') {
    try {
      await setReportItemStatus(text, itemStatus);
      setResolved((current) => new Set(current).add(text));
      showToast(itemStatus === 'done' ? '처리됨으로 표시했습니다.' : '무시 목록에 넣었습니다. 다음 리포트부터 제외됩니다.');
    } catch (err) {
      showToast(err instanceof Error ? err.message : '상태 저장 실패');
    }
  }

  async function convertToTask(text: string) {
    try {
      await createWorkScheduleItem({
        id: '',
        title: text.slice(0, 80),
        owner_id: user.id,
        owner_name: user.display_name,
        status: '대기',
        priority: '중',
        start_date: new Date().toISOString().slice(0, 10),
        due_date: '',
        dependencies: [],
        notes: 'AI 현황 리포트에서 생성됨',
        source_architecture_id: '',
      });
      showToast('업무 배정 목록에 추가했습니다. 담당자는 업무 배정 화면에서 바꿀 수 있습니다.');
    } catch (err) {
      showToast(err instanceof Error ? err.message : '업무 생성 실패');
    }
  }

  async function makeWeeklyDraft() {
    setDraftBusy(true);
    try {
      const result = await generateWeeklyDraft();
      setDraftText({ title: '주간보고 초안', markdown: result.markdown });
    } catch (err) {
      showToast(err instanceof Error ? err.message : '주간보고 초안 생성 실패');
    } finally {
      setDraftBusy(false);
    }
  }

  async function makeHandoverDraft() {
    if (!handoverName.trim()) {
      showToast('인수인계 대상자 이름을 입력하세요.');
      return;
    }
    setDraftBusy(true);
    try {
      const result = await generateHandoverDraft(handoverName.trim());
      setDraftText({ title: `${handoverName.trim()} 인수인계 초안`, markdown: result.markdown });
    } catch (err) {
      showToast(err instanceof Error ? err.message : '인수인계 초안 생성 실패');
    } finally {
      setDraftBusy(false);
    }
  }

  const draftModal = draftText ? (
    <div className="modal-backdrop" role="dialog" aria-modal="true" onClick={() => setDraftText(null)}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="folder-browser-head">
          <strong>{draftText.title}</strong>
          <span className="report-item-actions">
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard.writeText(draftText.markdown);
                showToast('복사했습니다.');
              }}
            >
              복사
            </button>
            <button type="button" onClick={() => setDraftText(null)}>닫기</button>
          </span>
        </div>
        <pre className="doc-preview">{draftText.markdown}</pre>
      </div>
    </div>
  ) : null;

  const myItems = workItems.filter(
    (item) => item.owner_id === user.id || item.owner_name === user.display_name,
  );
  const activeItems = workItems.filter((item) => !/완료|done/i.test(item.status || ''));
  const dueSoonItems = workItems.filter(isDueSoon);
  const createdAt = report?.created_at ? new Date(report.created_at).toLocaleString() : '';

  const statusCounts = STATUS_ORDER.map((entry) => ({
    ...entry,
    count:
      entry.key === 'late'
        ? dueSoonItems.length
        : workItems.filter(
            (item) => !isDueSoon(item) && entry.match(item.status || '') &&
              STATUS_ORDER.find((candidate) => candidate.match(item.status || ''))?.key === entry.key,
          ).length,
  }));
  const statusTotal = statusCounts.reduce((sum, entry) => sum + entry.count, 0);

  if (!isAdmin) {
    return (
      <section>
        <div className="hero-panel">
          <p className="eyebrow">{memory.company_name || '우리 회사'}</p>
          <h1>{user.display_name}님, 안녕하세요</h1>
          <p className="lede">오늘 할 일을 확인하고, 궁금한 회사 맥락은 AI에게 바로 물어보세요.</p>
          <FormActions>
            <Button disabled={draftBusy} onClick={() => void makeWeeklyDraft()}>
              {draftBusy ? '문서를 읽는 중...' : '주간보고 초안 만들기'}
            </Button>
            <Button variant="secondary" onClick={() => onAction('ask')}>회사에 물어보기</Button>
            <Button variant="secondary" onClick={() => onAction('work')}>업무 현황</Button>
          </FormActions>
        </div>
        <article className="panel report-card">
          <h3>내 업무</h3>
          {myItems.length ? (
            <ul>
              {myItems.map((item) => (
                <li key={item.id}>
                  <strong>{item.title}</strong>
                  {' — '}
                  {item.status || '상태 없음'}
                  {item.due_date ? ` · 마감 ${item.due_date}` : ''}
                  {item.priority ? ` · 우선순위 ${item.priority}` : ''}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">아직 배정된 업무가 없습니다. 관리자가 업무를 배정하면 여기에 표시됩니다.</p>
          )}
        </article>
        {draftModal}
        {toast ? <div className="toast">{toast}</div> : null}
      </section>
    );
  }

  return (
    <section>
      <div className="hero-panel">
        <p className="eyebrow">{memory.company_name || '우리 회사'}</p>
        <h1>지금 우리 회사, 어떻게 돌아가고 있나</h1>
        <p className="lede">
          {memory.organization ||
            'AI가 회사 폴더의 문서를 읽고 진행상황을 정리합니다. 아래에서 최신 리포트를 확인하세요.'}
        </p>
        <FormActions>
          <Button disabled={busy} onClick={() => void refreshReport()}>
            {busy ? 'AI가 문서를 읽는 중... (1~3분)' : '지금 리포트 만들기'}
          </Button>
          <label className="checkbox-inline">
            자동 갱신
            <select value={interval} onChange={(e) => void changeInterval(e.target.value as ReportInterval)}>
              <option value="off">끄기</option>
              <option value="monthly">매월</option>
              <option value="quarterly">분기마다</option>
              <option value="semiannual">반기마다</option>
            </select>
          </label>
          {createdAt ? <span className="muted">마지막 리포트: {createdAt}</span> : null}
        </FormActions>
      </div>

      <div className="kpi-strip">
        <button type="button" className="kpi-tile" onClick={() => onAction('work')}>
          <span className="kpi-value">{activeItems.length}</span>
          <span className="kpi-label">진행 중 업무</span>
        </button>
        <button type="button" className="kpi-tile" onClick={() => onAction('work-schedule')}>
          <span className="kpi-value">{dueSoonItems.length}</span>
          <span className="kpi-label">기한 임박 (7일)</span>
        </button>
        <button type="button" className="kpi-tile" onClick={() => onAction('personnel')}>
          <span className="kpi-value">{employeeCount ?? '-'}</span>
          <span className="kpi-label">등록 직원</span>
        </button>
        <div className="kpi-tile" role="presentation">
          <span className="kpi-value">{report?.changed_files ?? 0}</span>
          <span className="kpi-label">새로/바뀐 문서</span>
        </div>
      </div>

      {statusTotal > 0 ? (
        <article className="panel report-card viz-card">
          <h3>업무 상태 분포</h3>
          <div className="status-bar" role="img" aria-label="업무 상태 분포 차트">
            {statusCounts
              .filter((entry) => entry.count > 0)
              .map((entry) => (
                <span
                  key={entry.key}
                  className="status-seg"
                  style={{ flexGrow: entry.count, background: `var(${entry.varName})` }}
                  title={`${entry.label} ${entry.count}건`}
                />
              ))}
          </div>
          <div className="status-legend">
            {statusCounts.map((entry) => (
              <span className="status-legend-item" key={entry.key}>
                <span className="status-dot" style={{ background: `var(${entry.varName})` }} />
                {entry.label} <strong>{entry.count}</strong>
              </span>
            ))}
          </div>
        </article>
      ) : null}

      {loadingReport || busy ? (
        <div className="report-grid">
          {[1, 2, 3].map((n) => (
            <div className="panel report-card skeleton-card" key={n}>
              <div className="skeleton-line w40" />
              <div className="skeleton-line" />
              <div className="skeleton-line w80" />
            </div>
          ))}
        </div>
      ) : null}

      {!loadingReport && !busy && !report ? (
        <article className="panel report-empty">
          <h3>아직 리포트가 없습니다</h3>
          <p className="muted">
            [지금 리포트 만들기]를 누르면 AI가 회사 폴더의 문서를 읽고 진행된 일 / 신경 쓸 일 /
            인력·자금 신호를 정리해 줍니다. 이후에는 바뀐 문서만 다시 읽어서 빠르게 갱신됩니다.
          </p>
        </article>
      ) : null}

      {!loadingReport && !busy && report ? (
        <div className="report-grid">
          {SECTIONS.map(([key, title]) => {
            const items = normalizeItems(report[key]).filter((item) => !resolved.has(item.text));
            return (
              <article className="panel report-card" key={key}>
                <h3 className="report-title">
                  <span className={`report-icon icon-${key}`}>{ICONS[key]}</span>
                  {title}
                </h3>
                {items.length ? (
                  <ul className="report-items">
                    {items.map((item) => (
                      <li key={item.text}>
                        <p>{item.text}</p>
                        <div className="report-item-meta">
                          {item.sources.slice(0, 3).map((source) => (
                            <button
                              type="button"
                              className="source-chip"
                              key={source}
                              onClick={() => void openDocument(source)}
                              title={source}
                            >
                              {source.split(/[\\/]/).pop()}
                            </button>
                          ))}
                          <span className="report-item-actions">
                            <button type="button" onClick={() => void convertToTask(item.text)}>업무로</button>
                            <button type="button" onClick={() => void resolveItem(item.text, 'done')}>처리됨</button>
                            <button type="button" onClick={() => void resolveItem(item.text, 'dismissed')}>무시</button>
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">이번 리포트에서는 발견된 내용이 없습니다.</p>
                )}
              </article>
            );
          })}
          <article className="panel report-card">
            <h3>근거</h3>
            <p className="muted">
              문서 {report.read_files ?? 0}개를 근거로 작성했고, 그중 {report.changed_files ?? 0}개가
              지난 리포트 이후 새로 생기거나 바뀐 문서입니다. 각 항목의 문서 칩을 누르면 원문을 볼 수 있습니다.
            </p>
          </article>
        </div>
      ) : null}

      <div className="report-grid">
        {ADMIN_SHORTCUTS.map(([page, title, description]) => (
          <article className="panel report-card" key={page}>
            <h3>{title}</h3>
            <p className="muted">{description}</p>
            <FormActions>
              <Button variant="secondary" onClick={() => onAction(page)}>열기</Button>
            </FormActions>
          </article>
        ))}
        <article className="panel report-card">
          <h3>인수인계 초안</h3>
          <p className="muted">퇴사·이동하는 직원의 이름을 넣으면 관련 문서를 찾아 인수인계 초안을 만듭니다.</p>
          <div className="inline-input-row">
            <input
              value={handoverName}
              placeholder="예: 김영순"
              onChange={(e) => setHandoverName(e.target.value)}
            />
            <Button variant="secondary" disabled={draftBusy} onClick={() => void makeHandoverDraft()}>
              {draftBusy ? '작성 중...' : '만들기'}
            </Button>
          </div>
        </article>
        <article className="panel report-card">
          <h3>주간보고 초안</h3>
          <p className="muted">최근 7일 사이 바뀐 문서로 주간보고 초안을 만듭니다. 직원 홈에도 같은 버튼이 있습니다.</p>
          <FormActions>
            <Button variant="secondary" disabled={draftBusy} onClick={() => void makeWeeklyDraft()}>
              {draftBusy ? '작성 중...' : '만들기'}
            </Button>
          </FormActions>
        </article>
      </div>

      {docPreview ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" onClick={() => setDocPreview(null)}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="folder-browser-head">
              <strong>{docPreview.filename}</strong>
              <Button variant="secondary" onClick={() => setDocPreview(null)}>닫기</Button>
            </div>
            <pre className="doc-preview">{docPreview.text}</pre>
          </div>
        </div>
      ) : null}
      {draftModal}
      {toast ? <div className="toast">{toast}</div> : null}
    </section>
  );
}
