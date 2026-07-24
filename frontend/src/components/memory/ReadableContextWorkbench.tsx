import { useEffect, useMemo, useState } from 'react';

import {
  fetchReadableSource,
  fetchReadableSources,
  previewReadableContext,
  type ReadableContextBundle,
  type ReadableContextSource,
} from '../../api';
import SortableSourceOrder from './SortableSourceOrder';

type Props = {
  query: string;
  onQueryChange: (query: string) => void;
  selectedIds: string[];
  onSelectedIdsChange: (ids: string[]) => void;
  onBundlePreview?: (bundle: ReadableContextBundle) => void;
  onRequestDeletion?: (source: ReadableContextSource) => void | Promise<void>;
  canDeleteImmediately?: boolean;
  onDeleteSource?: (source: ReadableContextSource) => void | Promise<void>;
};

const KIND_FILTERS = [
  'all',
  'document',
  'patch_log',
  'conversation',
  'promoted_memory',
  'patch_record',
  'upload',
] as const;

type KindFilter = (typeof KIND_FILTERS)[number];

const KIND_LABELS: Record<KindFilter, string> = {
  all: '전체',
  document: '문서',
  patch_log: '패치 로그',
  conversation: '대화',
  promoted_memory: '승격 메모리',
  patch_record: '패치 기록',
  upload: '업로드',
};

function isUserFacingSource(source: ReadableContextSource): boolean {
  const path = source.path || source.id || '';
  if (source.kind === 'audit_log' || source.kind === 'token_usage') return false;
  return !(
    path === 'audit_log.jsonl' ||
    path.startsWith('token_usage/') ||
    path.startsWith('context_firewall/') ||
    path.startsWith('mcp_hub/')
  );
}

export default function ReadableContextWorkbench({
  query,
  onQueryChange,
  selectedIds,
  onSelectedIdsChange,
  onBundlePreview,
  onRequestDeletion,
  canDeleteImmediately = false,
  onDeleteSource,
}: Props) {
  const [sources, setSources] = useState<ReadableContextSource[]>([]);
  const [selectedKind, setSelectedKind] = useState<KindFilter>('all');
  const [preview, setPreview] = useState<ReadableContextSource | null>(null);
  const [bundle, setBundle] = useState<ReadableContextBundle | null>(null);
  const [includeVolatile, setIncludeVolatile] = useState(false);
  const [tokenBudget, setTokenBudget] = useState(4000);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  async function refresh() {
    setBusy(true);
    setMessage('');
    try {
      const payload = await fetchReadableSources(query, 150);
      setSources(payload.sources);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'AI 가독 source 조회 실패');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const userFacingSources = useMemo(() => sources.filter(isUserFacingSource), [sources]);
  const visibleSources = useMemo(
    () => userFacingSources.filter((source) => selectedKind === 'all' || source.kind === selectedKind),
    [userFacingSources, selectedKind],
  );
  const idToLabel = useMemo(
    () => Object.fromEntries(userFacingSources.map((source) => [source.id, source.title || source.path])),
    [userFacingSources],
  );
  const selectedSources = selectedIds
    .map((id) => userFacingSources.find((source) => source.id === id))
    .filter((source): source is ReadableContextSource => Boolean(source));

  function toggleSource(source: ReadableContextSource, checked: boolean) {
    if (checked) {
      if (selectedIds.includes(source.id)) return;
      onSelectedIdsChange([...selectedIds, source.id]);
      return;
    }
    onSelectedIdsChange(selectedIds.filter((id) => id !== source.id));
  }

  async function openSource(source: ReadableContextSource) {
    setBusy(true);
    setMessage('');
    try {
      const detailed = await fetchReadableSource(source.id);
      setPreview(detailed);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'source 열람 실패');
    } finally {
      setBusy(false);
    }
  }

  async function buildPreview() {
    setBusy(true);
    setMessage('AI가 읽을 context bundle을 조립 중입니다.');
    try {
      const next = await previewReadableContext({
        query,
        source_ids: selectedIds,
        source_limit: selectedIds.length || 20,
        include_volatile: includeVolatile,
        token_budget: tokenBudget,
      });
      setBundle(next);
      onBundlePreview?.(next);
      setMessage(`미리보기 생성 완료: ${next.used_sources.length}개 source, 약 ${next.estimated_tokens} tokens`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'context bundle 미리보기 실패');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="readable-workbench">
      <div className="panel readable-workbench-browser">
        <p className="eyebrow">AI readable sources</p>
        <h2>AI가 읽을 내부 정보 선택</h2>
        <p className="muted small">
          영구메모리, 생성 문서, 업로드 파일, 패치 기록을 같은 source로 보고 선택합니다.
        </p>
        <div className="memory-form row-compact">
          <input
            value={query}
            placeholder="문서/메모리 검색어"
            onChange={(event) => onQueryChange(event.target.value)}
          />
          <button type="button" disabled={busy} onClick={() => void refresh()}>
            {busy ? '조회 중...' : '검색 / 새로고침'}
          </button>
        </div>
        <div className="kind-filter-list" aria-label="AI readable source 종류별 보기">
          {KIND_FILTERS.map((kind) => (
            <button
              key={kind}
              type="button"
              className={selectedKind === kind ? 'kind-filter active' : 'kind-filter'}
              onClick={() => setSelectedKind(kind)}
            >
              {KIND_LABELS[kind]}
            </button>
          ))}
        </div>
        <div className="source-list" role="list">
          {visibleSources.map((source) => {
            const checked = selectedIds.includes(source.id);
            return (
              <div key={source.id} className={`source-row${checked ? ' source-row-selected' : ''}`} role="listitem">
                <label className="source-row-check">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) => toggleSource(source, event.target.checked)}
                  />
                  <span className="source-row-body">
                    <strong>{source.title}</strong>
                    <span className="muted small">
                      {source.kind} · {source.path}
                    </span>
                    <small className="source-excerpt">{source.excerpt.slice(0, 180)}</small>
                  </span>
                </label>
                <div className="source-row-actions">
                  <button className="secondary-button" type="button" onClick={() => void openSource(source)}>
                    열람
                  </button>
                  {onRequestDeletion ? (
                    <button className="secondary-button" type="button" onClick={() => void onRequestDeletion(source)}>
                      삭제 요청
                    </button>
                  ) : null}
                  {canDeleteImmediately && onDeleteSource ? (
                    <button className="danger" type="button" onClick={() => void onDeleteSource(source)}>
                      즉시 삭제
                    </button>
                  ) : null}
                </div>
              </div>
            );
          })}
          {!visibleSources.length ? <p className="muted small">조회된 source가 없습니다.</p> : null}
        </div>
      </div>

      <div className="panel readable-workbench-selection">
        <p className="eyebrow">Read order</p>
        <h2>선택·드래그 순서</h2>
        <SortableSourceOrder ids={selectedIds} idToLabel={idToLabel} onReorder={onSelectedIdsChange} />
        {selectedSources.length ? (
          <div className="log-list">
            {selectedSources.map((source, index) => (
              <article className="log-card" key={source.id}>
                <strong>
                  #{index + 1} {source.title}
                </strong>
                <p>{source.path}</p>
                <button type="button" className="secondary-button" onClick={() => toggleSource(source, false)}>
                  제외
                </button>
              </article>
            ))}
          </div>
        ) : (
          <p className="muted small">선택된 source가 없으면 검색 결과 상위 항목이 기본 후보가 됩니다.</p>
        )}
        <label className="checkbox-inline">
          <input
            type="checkbox"
            checked={includeVolatile}
            onChange={(event) => setIncludeVolatile(event.target.checked)}
          />
          휘발성 메모리 포함
        </label>
        <label className="memory-form">
          Token budget
          <input
            type="number"
            min={1000}
            max={32000}
            value={tokenBudget}
            onChange={(event) => setTokenBudget(Number(event.target.value) || 4000)}
          />
        </label>
        <button type="button" className="primary" disabled={busy} onClick={() => void buildPreview()}>
          {busy ? '조립 중...' : 'AI가 읽을 정보 미리보기'}
        </button>
        {message ? <p className="muted small">{message}</p> : null}
      </div>

      <div className="panel readable-workbench-preview">
        <p className="eyebrow">Preview</p>
        <h2>{preview ? preview.title : 'Source / context preview'}</h2>
        {preview ? (
          <>
            <p className="muted small">
              {preview.kind} · {preview.path}
            </p>
            <div className="document-viewer">
              <pre>{preview.content || preview.excerpt}</pre>
            </div>
          </>
        ) : bundle ? (
          <>
            <p className="muted small">
              used {bundle.used_sources.length} sources · volatile {bundle.volatile_memories.length} · approx{' '}
              {bundle.estimated_tokens} tokens
            </p>
            {bundle.warnings.length ? <p className="status-pill warn">{bundle.warnings.join(' / ')}</p> : null}
            <div className="document-viewer">
              <pre>{bundle.markdown}</pre>
            </div>
          </>
        ) : (
          <p className="muted small">source를 열람하거나 context bundle 미리보기를 실행하세요.</p>
        )}
      </div>
    </div>
  );
}
