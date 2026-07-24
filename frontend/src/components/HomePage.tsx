import { useEffect, useState } from 'react';

import {
  fetchLatestCompanyReport,
  generateCompanyReport,
  type ApiStatus,
  type CompanyReport,
  type OperationsMemory,
} from '../api';
import Button from './common/Button';
import FormActions from './common/FormActions';

const SECTIONS: Array<[keyof CompanyReport, string, string]> = [
  ['progressed', '✅ 진행된 일', '문서에서 확인된 진척 사항이 여기 표시됩니다.'],
  ['attention', '⚠ 신경 쓸 일', '문제, 지연, 재고·품질 이슈가 여기 표시됩니다.'],
  ['quiet', '⏸ 소식이 없는 일', '언급이 끊긴 업무가 여기 표시됩니다.'],
  ['people', '👥 인력 신호', '부서별 인력 상황과 채용 신호가 여기 표시됩니다.'],
  ['money', '💰 돈 관련 언급', '비용, 단가, 매출, 자금 관련 내용이 여기 표시됩니다.'],
];

export default function HomePage({
  memory,
}: {
  memory: OperationsMemory;
  status: ApiStatus | null;
  onAction: (page: string) => void;
}) {
  const [report, setReport] = useState<CompanyReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    fetchLatestCompanyReport()
      .then((latest) => setReport(latest && Object.keys(latest).length ? latest : null))
      .catch(() => setReport(null));
  }, []);

  async function refreshReport() {
    setBusy(true);
    setNotice('');
    try {
      setReport(await generateCompanyReport());
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '리포트 생성 실패');
    } finally {
      setBusy(false);
    }
  }

  const createdAt = report?.created_at ? new Date(report.created_at).toLocaleString() : '';

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
          {createdAt ? <span className="muted">마지막 리포트: {createdAt}</span> : null}
        </FormActions>
        {notice ? <p className="alert">{notice}</p> : null}
      </div>

      {!report ? (
        <article className="panel report-empty">
          <h3>아직 리포트가 없습니다</h3>
          <p className="muted">
            [지금 리포트 만들기]를 누르면 AI가 회사 폴더의 문서를 읽고 진행된 일 / 신경 쓸 일 /
            인력·자금 신호를 정리해 줍니다. 이후에는 바뀐 문서만 다시 읽어서 빠르게 갱신됩니다.
          </p>
        </article>
      ) : (
        <div className="report-grid">
          {SECTIONS.map(([key, title, description]) => {
            const items = (report[key] as string[] | undefined) || [];
            return (
              <article className="panel report-card" key={String(key)}>
                <h3>{title}</h3>
                {items.length ? (
                  <ul>
                    {items.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">{description} 이번 리포트에서는 발견된 내용이 없습니다.</p>
                )}
              </article>
            );
          })}
          <article className="panel report-card">
            <h3>근거</h3>
            <p className="muted">
              문서 {report.read_files ?? 0}개를 근거로 작성했고, 그중 {report.changed_files ?? 0}개가
              지난 리포트 이후 새로 생기거나 바뀐 문서입니다.
            </p>
          </article>
        </div>
      )}
    </section>
  );
}
