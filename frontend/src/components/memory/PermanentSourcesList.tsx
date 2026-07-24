import { useMemo } from 'react';

import type { PermanentMemorySource } from '../../api';

import SortableSourceOrder from './SortableSourceOrder';

export type MemoryKindFilter = 'all' | 'patch_log' | 'document' | 'conversation' | 'promoted_memory';

const KIND_LABELS: Record<MemoryKindFilter, string> = {
  all: '전체',
  patch_log: '패치 로그',
  document: '문서',
  conversation: '대화 기록',
  promoted_memory: '승격 메모리',
};

function isUserFacingSource(source: PermanentMemorySource): boolean {
  const path = source.path || source.id || '';
  if (source.kind === 'audit_log' || source.kind === 'token_usage') return false;
  return !(
    path === 'audit_log.jsonl' ||
    path.startsWith('token_usage/') ||
    path.startsWith('context_firewall/') ||
    path.startsWith('mcp_hub/')
  );
}

type Props = {
  sources: PermanentMemorySource[];
  selectedKind: MemoryKindFilter;
  onKindChange: (kind: MemoryKindFilter) => void;
  query: string;
  setQuery: (q: string) => void;
  onRefresh: () => void | Promise<void>;
  selectedIds: string[];
  onToggleSource: (id: string, checked: boolean) => void;
  onReorderSelected: (ids: string[]) => void;
  onRequestDeletion: (source: PermanentMemorySource) => void | Promise<void>;
  canDeleteImmediately?: boolean;
  onDeleteSource?: (source: PermanentMemorySource) => void | Promise<void>;
};

export default function PermanentSourcesList({
  sources,
  selectedKind,
  onKindChange,
  query,
  setQuery,
  onRefresh,
  selectedIds,
  onToggleSource,
  onReorderSelected,
  onRequestDeletion,
  canDeleteImmediately = false,
  onDeleteSource,
}: Props) {
  const userFacingSources = useMemo(() => sources.filter(isUserFacingSource), [sources]);
  const idToLabel = useMemo(
    () => Object.fromEntries(userFacingSources.map((s) => [s.id, s.title || s.path])),
    [userFacingSources],
  );
  const counts = useMemo(() => {
    const next: Record<MemoryKindFilter, number> = {
      all: userFacingSources.length,
      patch_log: 0,
      document: 0,
      conversation: 0,
      promoted_memory: 0,
    };
    for (const source of userFacingSources) {
      if (source.kind in next) {
        next[source.kind as MemoryKindFilter] += 1;
      }
    }
    return next;
  }, [userFacingSources]);
  const visibleSources =
    selectedKind === 'all' ? userFacingSources : userFacingSources.filter((source) => source.kind === selectedKind);

  return (
    <div className="panel memory-sources-panel">
      <p className="eyebrow">Permanent memory browser</p>
      <h2>네고티움 영구메모리 조회</h2>
      <p className="muted small">저장된 기억을 종류별로 살펴보고, AI가 참고할 항목을 선택합니다.</p>
      <div className="kind-filter-list" aria-label="메모리 종류별 보기">
        {(Object.keys(KIND_LABELS) as MemoryKindFilter[]).map((kind) => (
          <button
            key={kind}
            type="button"
            className={selectedKind === kind ? 'kind-filter active' : 'kind-filter'}
            onClick={() => onKindChange(kind)}
          >
            {KIND_LABELS[kind]} <span>{counts[kind]}</span>
          </button>
        ))}
      </div>
      <div className="memory-form row-compact">
        <input placeholder="보조 검색어 (선택)" value={query} onChange={(e) => setQuery(e.target.value)} />
        <button type="button" onClick={() => void onRefresh()}>
          검색 / 새로고침
        </button>
      </div>
      <SortableSourceOrder ids={selectedIds} idToLabel={idToLabel} onReorder={onReorderSelected} />
      <div className="source-list" role="list">
        {visibleSources.map((source) => {
          const checked = selectedIds.includes(source.id);
          return (
            <div key={source.id} className={`source-row${checked ? ' source-row-selected' : ''}`} role="listitem">
              <label className="source-row-check">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => onToggleSource(source.id, e.target.checked)}
                />
                <span className="source-row-body">
                  <strong>{source.title}</strong>
                  <span className="muted small">
                    {source.kind} · {source.path}
                  </span>
                  <small className="source-excerpt">{source.excerpt.slice(0, 180)}</small>
                </span>
              </label>
              <button
                className="secondary-button source-row-action"
                type="button"
                onClick={() => void onRequestDeletion(source)}
              >
                삭제 요청
              </button>
              {canDeleteImmediately && onDeleteSource ? (
                <button
                  className="danger source-row-action"
                  type="button"
                  onClick={() => void onDeleteSource(source)}
                >
                  즉시 삭제
                </button>
              ) : null}
            </div>
          );
        })}
        {visibleSources.length === 0 ? <p className="muted">이 종류에 저장된 메모리가 없습니다.</p> : null}
      </div>
    </div>
  );
}
