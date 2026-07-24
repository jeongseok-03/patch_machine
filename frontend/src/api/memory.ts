import { requestJson } from './http';
import type {
  ArchiveDocumentListItem,
  ConversationRecord,
  DeletionRequest,
  DocumentRead,
  OperationsMemory,
  PermanentMemorySource,
  ReadableContextBundle,
  ReadableContextSource,
  VolatileMemory,
  WorkMemory,
} from './types';

export function fetchOperationsMemory(): Promise<OperationsMemory> {
  return requestJson<OperationsMemory>('/api/operations-memory');
}

export function saveOperationsMemory(memory: OperationsMemory): Promise<OperationsMemory> {
  return requestJson<OperationsMemory>('/api/operations-memory', {
    method: 'PUT',
    body: JSON.stringify(memory),
  });
}

export function fetchWorkMemory(): Promise<WorkMemory> {
  return requestJson<WorkMemory>('/api/work-memory');
}

export function saveWorkMemory(memory: WorkMemory): Promise<WorkMemory> {
  return requestJson<WorkMemory>('/api/work-memory', {
    method: 'PUT',
    body: JSON.stringify(memory),
  });
}

export function fetchPermanentMemory(query = ''): Promise<{ sources: PermanentMemorySource[] }> {
  const path = query ? `/api/memory/permanent/search?q=${encodeURIComponent(query)}` : '/api/memory/permanent/recent';
  return requestJson<{ sources: PermanentMemorySource[] }>(path);
}

export function fetchReadableSources(query = '', limit = 100): Promise<{ sources: ReadableContextSource[] }> {
  const params = new URLSearchParams();
  if (query) params.set('q', query);
  params.set('limit', String(limit));
  return requestJson<{ sources: ReadableContextSource[] }>(`/api/memory/readable-sources?${params.toString()}`);
}

export function fetchReadableSource(sourceId: string): Promise<ReadableContextSource> {
  return requestJson<ReadableContextSource>(`/api/memory/readable-source?source_id=${encodeURIComponent(sourceId)}`);
}

export function previewReadableContext(payload: {
  query: string;
  source_ids: string[];
  source_limit: number;
  include_volatile: boolean;
  token_budget: number;
}): Promise<ReadableContextBundle> {
  return requestJson<ReadableContextBundle>('/api/memory/readable-context/preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchVolatileMemories(): Promise<{ memories: VolatileMemory[] }> {
  return requestJson<{ memories: VolatileMemory[] }>('/api/memory/volatile');
}

export function refreshVolatileMemory(payload: {
  scope: string;
  key: string;
  query: string;
  source_limit: number;
  source_ids?: string[];
}): Promise<VolatileMemory> {
  return requestJson<VolatileMemory>('/api/memory/volatile/refresh', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteVolatileMemory(scope: string, key: string): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>(`/api/memory/volatile/${scope}/${key}`, { method: 'DELETE' });
}

export function compressContext(payload: {
  scope: string;
  key: string;
  query: string;
  token_budget: number;
  source_limit: number;
  source_ids?: string[];
  include_volatile?: boolean;
}): Promise<{ context: Record<string, unknown>; used_sources?: Array<Record<string, unknown>>; volatile_memories?: string[] }> {
  return requestJson<{ context: Record<string, unknown>; used_sources?: Array<Record<string, unknown>>; volatile_memories?: string[] }>('/api/memory/context/compress', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchConversations(): Promise<{ records: ConversationRecord[] }> {
  return requestJson<{ records: ConversationRecord[] }>('/api/memory/conversations');
}

export function fetchMemorySchema(): Promise<{ schemas: Array<Record<string, unknown>>; proposals: Array<Record<string, unknown>> }> {
  return requestJson<{ schemas: Array<Record<string, unknown>>; proposals: Array<Record<string, unknown>> }>('/api/memory/schema');
}

export function proposeMemorySchema(proposal: Record<string, unknown>): Promise<{ ok: boolean; proposal: Record<string, unknown> }> {
  return requestJson<{ ok: boolean; proposal: Record<string, unknown> }>('/api/memory/schema/propose', {
    method: 'POST',
    body: JSON.stringify({ mode: 'llm_propose_human_approve', proposal }),
  });
}

export function approveMemorySchemaProposal(id: string): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>(`/api/memory/schema/proposals/${id}/approve`, { method: 'POST' });
}

export function fetchDeletionRequests(): Promise<{ requests: DeletionRequest[] }> {
  return requestJson<{ requests: DeletionRequest[] }>('/api/memory/deletion-requests');
}

export function requestMemoryDeletion(payload: {
  target_type: string;
  target_id: string;
  summary: string;
  source_path: string;
  sensitivity: string;
  reason: string;
}): Promise<{ ok: boolean; request: DeletionRequest }> {
  return requestJson<{ ok: boolean; request: DeletionRequest }>('/api/memory/deletion-requests', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function approveDeletionRequest(id: string): Promise<{ ok: boolean; request: DeletionRequest }> {
  return requestJson<{ ok: boolean; request: DeletionRequest }>(`/api/memory/deletion-requests/${id}/approve`, { method: 'POST' });
}

export function rejectDeletionRequest(id: string): Promise<{ ok: boolean; request: DeletionRequest }> {
  return requestJson<{ ok: boolean; request: DeletionRequest }>(`/api/memory/deletion-requests/${id}/reject`, { method: 'POST' });
}

export function deleteMemorySource(sourceId: string): Promise<{ ok: boolean; source: PermanentMemorySource; request: DeletionRequest; physical_deleted?: boolean }> {
  return requestJson<{ ok: boolean; source: PermanentMemorySource; request: DeletionRequest; physical_deleted?: boolean }>(
    `/api/memory/sources?source_id=${encodeURIComponent(sourceId)}`,
    { method: 'DELETE' },
  );
}

export function readArchiveDocument(path: string): Promise<DocumentRead> {
  return requestJson<DocumentRead>(`/api/archive/documents?path=${encodeURIComponent(path)}`);
}

export function fetchArchiveDocumentIndex(query = '', limit = 200): Promise<{ documents: ArchiveDocumentListItem[] }> {
  return requestJson<{ documents: ArchiveDocumentListItem[] }>(
    `/api/archive/document-index?q=${encodeURIComponent(query)}&limit=${limit}`,
  );
}
