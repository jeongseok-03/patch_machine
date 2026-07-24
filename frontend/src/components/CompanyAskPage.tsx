import { useState } from 'react';

import { askCompany, previewScannedDocument } from '../api';
import Button from './common/Button';
import FormActions from './common/FormActions';

type Turn = { question: string; answer: string; sources: string[] };

export default function CompanyAskPage() {
  const [question, setQuestion] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [docPreview, setDocPreview] = useState<{ filename: string; text: string } | null>(null);

  async function ask() {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setNotice('');
    try {
      const result = await askCompany(trimmed);
      setTurns((current) => [{ question: trimmed, ...result }, ...current]);
      setQuestion('');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '답변 생성 실패');
    } finally {
      setBusy(false);
    }
  }

  async function openDocument(path: string) {
    try {
      const doc = await previewScannedDocument(path);
      setDocPreview({ filename: doc.filename, text: doc.text });
    } catch {
      setNotice('이 문서를 열 권한이 없습니다. 관리자에게 문의하세요.');
    }
  }

  return (
    <section>
      <div className="hero-panel">
        <p className="eyebrow">회사 기억</p>
        <h1>회사에 물어보기</h1>
        <p className="lede">
          "작년 한마트 납품 단가가 얼마였지?", "품질검사 담당이 누구지?" — 회사 폴더의 문서를 근거로
          답합니다. 답변마다 근거 문서가 붙습니다.
        </p>
        <div className="memory-form">
          <textarea
            value={question}
            rows={2}
            placeholder="회사 문서에 있는 내용이라면 무엇이든 물어보세요"
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void ask();
              }
            }}
          />
          <FormActions>
            <Button disabled={busy || !question.trim()} onClick={() => void ask()}>
              {busy ? '문서를 찾아보는 중...' : '물어보기'}
            </Button>
          </FormActions>
        </div>
        {notice ? <p className="alert">{notice}</p> : null}
      </div>

      <div className="report-grid" style={{ gridTemplateColumns: '1fr' }}>
        {busy ? (
          <div className="panel report-card skeleton-card">
            <div className="skeleton-line w40" />
            <div className="skeleton-line" />
            <div className="skeleton-line w80" />
          </div>
        ) : null}
        {turns.map((turn) => (
          <article className="panel report-card" key={turn.question + turn.answer.slice(0, 20)}>
            <p className="muted">Q. {turn.question}</p>
            <p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{turn.answer}</p>
            {turn.sources.length ? (
              <div className="report-item-meta">
                {turn.sources.map((source) => (
                  <button
                    type="button"
                    className="source-chip"
                    key={source}
                    title={source}
                    onClick={() => void openDocument(source)}
                  >
                    {source.split(/[\\/]/).pop()}
                  </button>
                ))}
              </div>
            ) : null}
          </article>
        ))}
        {!turns.length && !busy ? (
          <article className="panel report-empty">
            <h3>무엇이든 물어보세요</h3>
            <p className="muted">
              계약 조건, 담당자, 절차, 지난 회의 결정사항 — 문서에 남아 있다면 AI가 찾아서 근거와 함께
              답합니다.
            </p>
          </article>
        ) : null}
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
    </section>
  );
}
