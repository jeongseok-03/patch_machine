import { useCallback, useEffect, useRef, useState } from 'react';

import {
  deleteMemorySource,
  fetchConversations,
  fetchCurrentUser,
  fetchDeletionRequests,
  fetchOperationsMemory,
  fetchPermanentMemory,
  fetchVolatileMemories,
  fetchWorkMemory,
  requestMemoryDeletion,
  saveOperationsMemory,
  saveWorkMemory,
  type ConversationRecord,
  type DeletionRequest,
  type OperationsMemory,
  type PermanentMemorySource,
  type ReadableContextBundle,
  type VolatileMemory,
  type WorkMemory,
} from '../api';
import ContextCompressPanel from './memory/ContextCompressPanel';
import ConversationHistoryModal from './memory/ConversationHistoryModal';
import MemoryGovernancePanel from './memory/MemoryGovernancePanel';
import PermanentSourcesList, { type MemoryKindFilter } from './memory/PermanentSourcesList';
import ReadableContextWorkbench from './memory/ReadableContextWorkbench';
import VolatileMemoriesPanel from './memory/VolatileMemoriesPanel';
import WorkMemoryEditSection from './memory/WorkMemoryEditSection';

const emptyOperations: OperationsMemory = {
  company_name: '',
  office_project: '',
  active_plan: '',
  organization: '',
  departments: '',
  roles: '',
  key_workflows: '',
  office_tools: '',
  sensitive_policy: '',
};

const emptyWork: WorkMemory = {
  goals: '',
  active_projects: '',
  current_focus: '',
  blockers: '',
  decisions: '',
  risks: '',
  next_actions: '',
  updated_at: '',
};

export default function WorkMemoryPage() {
  const [section, setSection] = useState<'edit' | 'lookup' | 'summary' | 'governance' | 'cache'>('edit');
  const [editMode, setEditMode] = useState<'permanent' | 'volatile'>('permanent');
  const [operations, setOperations] = useState<OperationsMemory>(emptyOperations);
  const [work, setWork] = useState<WorkMemory>(emptyWork);
  const [sources, setSources] = useState<PermanentMemorySource[]>([]);
  const [volatileMemories, setVolatileMemories] = useState<VolatileMemory[]>([]);
  const [conversations, setConversations] = useState<ConversationRecord[]>([]);
  const [deletionRequests, setDeletionRequests] = useState<DeletionRequest[]>([]);
  const [query, setQuery] = useState('');
  const [message, setMessage] = useState('');
  const [convOpen, setConvOpen] = useState(false);
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [selectedKind, setSelectedKind] = useState<MemoryKindFilter>('all');
  const [readableBundle, setReadableBundle] = useState<ReadableContextBundle | null>(null);
  const [canDeleteSources, setCanDeleteSources] = useState(false);
  const queryRef = useRef(query);
  queryRef.current = query;

  const refreshAdminMemory = useCallback(async () => {
    const q = queryRef.current;
    const [permanent, volatilePayload, conversationPayload, deletions] = await Promise.all([
      fetchPermanentMemory(q),
      fetchVolatileMemories(),
      fetchConversations(),
      fetchDeletionRequests().catch(() => ({ requests: [] })),
    ]);
    setSources(permanent.sources);
    setVolatileMemories(volatilePayload.memories);
    setConversations(conversationPayload.records);
    setDeletionRequests(deletions.requests);
  }, []);

  useEffect(() => {
    Promise.all([fetchOperationsMemory(), fetchWorkMemory(), refreshAdminMemory(), fetchCurrentUser().catch(() => null)])
      .then(([nextOperations, nextWork, , me]) => {
        setOperations(nextOperations);
        setWork(nextWork);
        const permissions = me?.authenticated && me.user ? me.user.permissions || [] : [];
        setCanDeleteSources(permissions.includes('*') || permissions.includes('admin:users'));
      })
      .catch((err) => setMessage(err instanceof Error ? err.message : '메모리 로드 실패'));
  }, [refreshAdminMemory]);

  async function saveAll() {
    const [savedOperations, savedWork] = await Promise.all([saveOperationsMemory(operations), saveWorkMemory(work)]);
    setOperations(savedOperations);
    setWork(savedWork);
    setMessage('메모리를 저장했습니다.');
  }

  async function deleteSourceNow(source: Pick<PermanentMemorySource, 'id' | 'title'>) {
    try {
      const result = await deleteMemorySource(source.id);
      setSelectedSourceIds((current) => current.filter((id) => id !== source.id));
      setMessage(
        result.physical_deleted === false
          ? `원본 보호 항목이라 AI 메모리 목록에서 숨김 처리했습니다: ${source.title}`
          : `즉시 삭제했습니다: ${source.title}`,
      );
      await refreshAdminMemory();
    } catch (err) {
      setMessage(err instanceof Error ? `즉시 삭제 실패: ${err.message}` : '즉시 삭제 실패');
    }
  }

  function toggleSource(id: string, checked: boolean) {
    setSelectedSourceIds((prev) => {
      if (checked) {
        if (prev.includes(id)) return prev;
        return [...prev, id];
      }
      return prev.filter((x) => x !== id);
    });
  }

  const filteredSources = selectedKind === 'all' ? sources : sources.filter((source) => source.kind === selectedKind);
  const currentKindSourceIds = filteredSources.map((source) => source.id);
  const pendingDeletionCount = deletionRequests.filter((request) => request.status === 'pending').length;
  const sectionItems: Array<{ id: typeof section; label: string }> = [
    { id: 'edit', label: '메모리 수정' },
    { id: 'lookup', label: '네고티움 영구메모리 조회' },
    { id: 'summary', label: 'AI 가독 정보 요약' },
    { id: 'governance', label: `삭제 요청 승인${pendingDeletionCount ? ` (${pendingDeletionCount})` : ''}` },
    { id: 'cache', label: '캐시 관리' },
  ];

  return (
    <section className="page-workspace work-memory-layout">
      <div className="workspace-hero">
        <div className="panel">
          <p className="eyebrow">Memory workspace</p>
          <h2>메모리 관리</h2>
          <p className="muted">
            수정, 영구메모리 조회, AI 가독 요약, 삭제 요청 승인, 캐시 관리를 분리해 필요한 작업 영역만 펼쳐 봅니다.
          </p>
          {pendingDeletionCount ? (
            <button type="button" className="secondary-button" onClick={() => setSection('governance')}>
              삭제 요청 {pendingDeletionCount}건 승인하러 가기
            </button>
          ) : null}
          {message ? <p className="status-pill success">{message}</p> : null}
        </div>
        <div className="compact-stat-strip">
          <div className="compact-stat">
            <strong>{sources.length}</strong>
            <span>Permanent</span>
          </div>
          <div className="compact-stat">
            <strong>{selectedSourceIds.length}</strong>
            <span>Selected</span>
          </div>
          <div className="compact-stat">
            <strong>{volatileMemories.length}</strong>
            <span>Volatile</span>
          </div>
          <div className="compact-stat">
            <strong>{pendingDeletionCount}</strong>
            <span>Pending delete</span>
          </div>
        </div>
      </div>

      <div className="work-memory-toolbar">
        <div className="workspace-tabs" role="tablist" aria-label="네고티움 메모리 관리 메뉴">
          {sectionItems.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={section === item.id}
              className={section === item.id ? 'workspace-tab active' : 'workspace-tab'}
              onClick={() => setSection(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <button type="button" className="secondary-button" onClick={() => void setConvOpen(true)}>
          대화 기록 열기
        </button>
      </div>

      <div className="work-memory-grid">
        {section === 'edit' ? (
          <WorkMemoryEditSection
            mode={editMode}
            onModeChange={setEditMode}
            operations={operations}
            setOperations={setOperations}
            work={work}
            setWork={setWork}
            onSave={() => void saveAll()}
            message={message}
          />
        ) : null}

        {section === 'lookup' ? (
          <PermanentSourcesList
            sources={sources}
            selectedKind={selectedKind}
            onKindChange={setSelectedKind}
            query={query}
            setQuery={setQuery}
            onRefresh={() => void refreshAdminMemory()}
            selectedIds={selectedSourceIds}
            onToggleSource={toggleSource}
            onReorderSelected={setSelectedSourceIds}
            onRequestDeletion={(source) =>
              void requestMemoryDeletion({
                target_type: source.kind,
                target_id: source.id,
                summary: source.title,
                source_path: source.path,
                sensitivity: 'internal',
                reason: '관리자 요청',
              }).then(() => refreshAdminMemory())
            }
            canDeleteImmediately={canDeleteSources}
            onDeleteSource={(source) => void deleteSourceNow(source)}
          />
        ) : null}

        {section === 'summary' ? (
          <>
            <ReadableContextWorkbench
              query={query}
              onQueryChange={setQuery}
              selectedIds={selectedSourceIds}
              onSelectedIdsChange={setSelectedSourceIds}
              onBundlePreview={setReadableBundle}
              onRequestDeletion={(source) =>
                void requestMemoryDeletion({
                  target_type: source.kind,
                  target_id: source.id,
                  summary: source.title,
                  source_path: source.path,
                  sensitivity: source.sensitivity || 'internal',
                  reason: '관리자 요청',
                }).then(() => refreshAdminMemory())
              }
              canDeleteImmediately={canDeleteSources}
              onDeleteSource={(source) => void deleteSourceNow(source)}
            />
            <details className="advanced-panel" open>
              <summary>AI 요약 실행 패널</summary>
              <ContextCompressPanel
                query={query}
                selectedSourceIds={selectedSourceIds}
                fallbackSourceIds={currentKindSourceIds}
                readableBundle={readableBundle}
                onMessage={setMessage}
                onAfterCompress={() => refreshAdminMemory()}
              />
            </details>
          </>
        ) : null}

        {section === 'governance' ? (
          <MemoryGovernancePanel
            deletionRequests={deletionRequests}
            onRefresh={() => void refreshAdminMemory()}
          />
        ) : null}

        {section === 'cache' ? (
          <VolatileMemoriesPanel memories={volatileMemories} onAfterChange={() => void refreshAdminMemory()} />
        ) : null}
      </div>

      <ConversationHistoryModal open={convOpen} records={conversations} onClose={() => setConvOpen(false)} />
    </section>
  );
}
