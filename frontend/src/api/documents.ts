import { requestJson } from './http';
import type {
  GeneratedDocument,
  HiringRequest,
  HrEvaluationRecord,
  OfficeDocumentRequest,
} from './types';

export function createRoleRequirements(payload: HiringRequest): Promise<GeneratedDocument> {
  return requestJson<GeneratedDocument>('/api/hr/role-requirements', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function createInterviewKit(payload: HiringRequest): Promise<GeneratedDocument> {
  return requestJson<GeneratedDocument>('/api/hr/interview-kit', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function createOnboardingPlan(payload: HiringRequest): Promise<GeneratedDocument> {
  return requestJson<GeneratedDocument>('/api/hr/onboarding-plan', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function createOfficeDocument(payload: OfficeDocumentRequest): Promise<GeneratedDocument> {
  return requestJson<GeneratedDocument>('/api/documents/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchHrEvaluationContext(userId: string): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(`/api/hr/evaluation/context?user_id=${encodeURIComponent(userId)}`);
}

export function draftHrEvaluation(payload: {
  user_id: string;
  period?: string;
  work_item_ids?: string[];
  criteria?: string;
  notes?: string;
}): Promise<{ ok: boolean; draft: string; context: Record<string, unknown> }> {
  return requestJson<{ ok: boolean; draft: string; context: Record<string, unknown> }>('/api/hr/evaluation/draft', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function saveHrEvaluation(payload: {
  user_id: string;
  period?: string;
  work_item_ids?: string[];
  criteria?: string;
  notes?: string;
  draft?: string;
  final_text?: string;
  evidence?: string;
  source_refs?: string[];
}): Promise<{ ok: boolean; record: HrEvaluationRecord; document_path?: string }> {
  return requestJson<{ ok: boolean; record: HrEvaluationRecord; document_path?: string }>('/api/hr/evaluation/save', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchHrEvaluationRecords(userId = ''): Promise<{ records: HrEvaluationRecord[] }> {
  const query = userId ? `?user_id=${encodeURIComponent(userId)}` : '';
  return requestJson<{ records: HrEvaluationRecord[] }>(`/api/hr/evaluation/records${query}`);
}
