import { requestJson } from './http';
import type {
  AiJobStatus,
  ApiStatus,
  AssignmentScope,
  GeneratedDocument,
  HandoverRequest,
  ProcessPlan,
  ProgressLog,
  ProgressPayload,
  WorkArchitecture,
  WorkItemsPayload,
  WorkScheduleItem,
} from './types';

export function fetchApiStatus(): Promise<ApiStatus> {
  return requestJson<ApiStatus>('/api/status');
}

export function fetchProgress(): Promise<ProgressPayload> {
  return requestJson<ProgressPayload>('/api/progress');
}

export function fetchWorkItems(): Promise<WorkItemsPayload> {
  return requestJson<WorkItemsPayload>('/api/work-items');
}

export function generateWorkArchitecture(payload: {
  objective: string;
  scope: string;
  horizon: string;
  participants: string;
  constraints: string;
  use_memory: boolean;
}): Promise<WorkArchitecture> {
  return requestJson<WorkArchitecture>('/api/work-architecture/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchWorkSchedule(): Promise<{ items: WorkScheduleItem[] }> {
  return requestJson<{ items: WorkScheduleItem[] }>('/api/work-schedule');
}

export function createWorkScheduleItem(payload: WorkScheduleItem): Promise<{ ok: boolean; item: WorkScheduleItem; items: WorkScheduleItem[] }> {
  return requestJson<{ ok: boolean; item: WorkScheduleItem; items: WorkScheduleItem[] }>('/api/work-schedule/items', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateWorkScheduleItem(payload: WorkScheduleItem): Promise<{ ok: boolean; item: WorkScheduleItem; items: WorkScheduleItem[] }> {
  return requestJson<{ ok: boolean; item: WorkScheduleItem; items: WorkScheduleItem[] }>(`/api/work-schedule/items/${payload.id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function deleteWorkScheduleItem(itemId: string): Promise<{ ok: boolean; items: WorkScheduleItem[] }> {
  return requestJson<{ ok: boolean; items: WorkScheduleItem[] }>(`/api/work-schedule/items/${itemId}`, {
    method: 'DELETE',
  });
}

export function runWorkScheduleItem(itemId: string): Promise<{
  ok: boolean;
  item: WorkScheduleItem;
  items: ProgressLog[];
  result_path: string;
  ai_job?: AiJobStatus;
}> {
  return requestJson<{
    ok: boolean;
    item: WorkScheduleItem;
    items: ProgressLog[];
    result_path: string;
    ai_job?: AiJobStatus;
  }>(`/api/work-schedule/items/${itemId}/run`, {
    method: 'POST',
  });
}

export function fetchAssignmentScope(): Promise<AssignmentScope> {
  return requestJson<AssignmentScope>('/api/work-schedule/assignment-scope');
}

export function signOffWorkItem(
  itemId: string,
  note = '',
): Promise<{
  ok: boolean;
  item: WorkScheduleItem;
  items: ProgressLog[];
  plan?: ProcessPlan;
}> {
  return requestJson<{
    ok: boolean;
    item: WorkScheduleItem;
    items: ProgressLog[];
    plan?: ProcessPlan;
  }>(`/api/work-schedule/items/${itemId}/sign-off`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  });
}

export function fetchProcessPlans(): Promise<{ items: ProcessPlan[] }> {
  return requestJson<{ items: ProcessPlan[] }>('/api/process-plans');
}

export function fetchProcessPlan(planId: string): Promise<ProcessPlan> {
  return requestJson<ProcessPlan>(`/api/process-plans/${planId}`);
}

export function approveProcessPlan(planId: string): Promise<ProcessPlan> {
  return requestJson<ProcessPlan>(`/api/process-plans/${planId}/approve`, { method: 'POST' });
}

export function setProcessPlanMode(planId: string, mode: 'manual' | 'auto'): Promise<ProcessPlan> {
  return requestJson<ProcessPlan>(`/api/process-plans/${planId}/mode`, {
    method: 'POST',
    body: JSON.stringify({ mode }),
  });
}

export function pauseProcessPlan(planId: string): Promise<ProcessPlan> {
  return requestJson<ProcessPlan>(`/api/process-plans/${planId}/pause`, { method: 'POST' });
}

export function resumeProcessPlan(planId: string): Promise<ProcessPlan> {
  return requestJson<ProcessPlan>(`/api/process-plans/${planId}/resume`, { method: 'POST' });
}

export function addProcessStep(
  planId: string,
  payload: { title: string; notes?: string; owner_name?: string; priority?: string; assignee_kind?: string },
): Promise<ProcessPlan> {
  return requestJson<ProcessPlan>(`/api/process-plans/${planId}/steps`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateProcessStep(
  planId: string,
  stepId: string,
  payload: { title?: string; notes?: string; owner_name?: string; priority?: string; assignee_kind?: string },
): Promise<ProcessPlan> {
  return requestJson<ProcessPlan>(`/api/process-plans/${planId}/steps/${stepId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function deleteProcessStep(planId: string, stepId: string): Promise<ProcessPlan> {
  return requestJson<ProcessPlan>(`/api/process-plans/${planId}/steps/${stepId}`, {
    method: 'DELETE',
  });
}

export function reorderProcessSteps(planId: string, orderedIds: string[]): Promise<ProcessPlan> {
  return requestJson<ProcessPlan>(`/api/process-plans/${planId}/reorder`, {
    method: 'POST',
    body: JSON.stringify({ ordered_ids: orderedIds }),
  });
}

export function generateWorkSchedule(payload: {
  objective: string;
  participants: string;
  horizon: string;
  constraints: string;
}): Promise<GeneratedDocument> {
  return requestJson<GeneratedDocument>('/api/work-schedule/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function createHandoverBrief(payload: HandoverRequest): Promise<GeneratedDocument> {
  return requestJson<GeneratedDocument>('/api/handover/brief', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
