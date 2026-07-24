import { FormEvent, useEffect, useMemo, useState } from 'react';

import { fetchArchiveDocumentIndex, readArchiveDocument, type ArchiveDocumentListItem, type DocumentRead } from '../api';

export default function DocumentsViewerPage() {
  const [path, setPath] = useState<string>('');
  const [doc, setDoc] = useState<DocumentRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [documents, setDocuments] = useState<ArchiveDocumentListItem[]>([]);
  const [selectedKind, setSelectedKind] = useState('all');

  async function refreshIndex(search = query) {
    setError('');
    try {
      const payload = await fetchArchiveDocumentIndex(search, 300);
      setDocuments(payload.documents);
    } catch (err) {
      setError(err instanceof Error ? err.message : '문서 목록을 불러오지 못했습니다.');
    }
  }

  useEffect(() => {
    void refreshIndex('');
  }, []);

  const kinds = useMemo(() => ['all', ...Array.from(new Set(documents.map((item) => item.kind)))], [documents]);
  const visibleDocuments = selectedKind === 'all' ? documents : documents.filter((item) => item.kind === selectedKind);

  async function load(target: string) {
    if (!target.trim()) return;
    setLoading(true);
    setError('');
    try {
      const next = await readArchiveDocument(target.trim());
      setDoc(next);
      setPath(next.path);
    } catch (err) {
      setError(err instanceof Error ? err.message : '문서를 불러오지 못했습니다.');
      setDoc(null);
    } finally {
      setLoading(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await refreshIndex(query);
  }

  return (
    <section className="page-workspace">
      <div className="workspace-hero">
        <div className="panel">
          <p className="eyebrow">Archive viewer</p>
          <h2>문서 열람</h2>
          <p className="muted">
            archive/ 하위에 자동 생성된 markdown / json / yaml 문서를 안전하게 조회합니다. AI가 읽을 내부 정보 선택은
            문서 자동화와 메모리 관리 화면에서만 다룹니다. 여기서는 제목과 종류 기준으로 문서를 고릅니다.
          </p>
        </div>
        <div className="compact-stat-strip">
          <div className="compact-stat">
            <strong>{documents.length}</strong>
            <span>Indexed docs</span>
          </div>
          <div className="compact-stat">
            <strong>{doc ? '1' : '0'}</strong>
            <span>Opened</span>
          </div>
        </div>
      </div>

      <div className="workspace-split">
        <div className="panel workspace-sidebar">
          <div className="sticky-panel-header">
            <p className="eyebrow">Open document</p>
            <h2>문서 목록</h2>
          </div>
          <form className="connector-config-form" onSubmit={submit}>
            <label>
              제목/종류/내용 검색
              <input
                type="text"
                value={query}
                placeholder="예: 회의록, 온보딩, 업무 아키텍처"
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <div className="switch-row">
              <button className="primary" type="submit" disabled={loading}>
                검색
              </button>
              <button type="button" className="secondary-button" onClick={() => void refreshIndex('')}>
                전체 목록
              </button>
            </div>
            {error ? <span className="status-pill warn">{error}</span> : null}
          </form>
          <div className="kind-filter-list" aria-label="문서 종류별 보기">
            {kinds.map((kind) => (
              <button
                key={kind}
                type="button"
                className={selectedKind === kind ? 'kind-filter active' : 'kind-filter'}
                onClick={() => setSelectedKind(kind)}
              >
                {kind === 'all' ? '전체' : kind}
              </button>
            ))}
          </div>
          <div className="compact-card-list bounded-list compact">
            {visibleDocuments.map((item) => (
              <button
                key={item.path}
                type="button"
                className={`compact-list-card${doc?.path === item.path ? ' selected' : ''}`}
                onClick={() => {
                  setPath(item.path);
                  void load(item.path);
                }}
              >
                <strong>{item.title}</strong>
                <span className="muted small">{item.kind}</span>
                <small>
                  {item.modified_at} · {(item.bytes / 1024).toFixed(1)} KB
                </small>
                {item.excerpt ? <small>{item.excerpt.slice(0, 100)}</small> : null}
              </button>
            ))}
            {!visibleDocuments.length ? <p className="muted small">조건에 맞는 문서가 없습니다.</p> : null}
          </div>
          <details className="advanced-panel">
            <summary>경로를 직접 알고 있을 때 열기</summary>
            <form className="connector-config-form" onSubmit={(event) => { event.preventDefault(); void load(path); }}>
              <input
                type="text"
                value={path}
                placeholder="documents/20260507_meeting.md"
                onChange={(event) => setPath(event.target.value)}
              />
              <button type="submit" disabled={loading}>{loading ? '불러오는 중...' : '경로로 열기'}</button>
            </form>
          </details>
        </div>
        <div className="panel workspace-detail">
          {doc ? (
            <>
              <p className="eyebrow">{doc.path}</p>
              <h2>문서 미리보기</h2>
              <p className="muted small">
                {doc.bytes.toLocaleString()} bytes · 수정 {doc.modified_at}
              </p>
              <div className="bounded-preview">
                <pre>{doc.markdown}</pre>
              </div>
            </>
          ) : (
            <p className="muted">왼쪽에서 경로를 입력하거나 문서 예시를 선택하세요.</p>
          )}
        </div>
      </div>
    </section>
  );
}
