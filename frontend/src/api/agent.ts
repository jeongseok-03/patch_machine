import { requestJson } from './http';
import type {
  AgentPlan,
  AiJobStatus,
  PatchArtifactFile,
  PatchEvent,
  PatchRun,
  PermanentMemorySource,
  SkillCreateInput,
  SkillDescriptor,
  SkillRunResult,
} from './types';

export function fetchAiJobs(limit = 30): Promise<{ jobs: AiJobStatus[] }> {
  return requestJson<{ jobs: AiJobStatus[] }>(`/api/ai-jobs/recent?limit=${limit}`);
}

export function fetchAiJob(jobId: string): Promise<AiJobStatus> {
  return requestJson<AiJobStatus>(`/api/ai-jobs/${encodeURIComponent(jobId)}`);
}

export function generateAgentPlan(payload: {
  objective: string;
  title: string;
  mode: string;
  schedule_refs: string[];
  memory_refs: string[];
  context?: string;
}): Promise<{ ok: boolean; plan: AgentPlan }> {
  return requestJson<{ ok: boolean; plan: AgentPlan }>('/api/agent/plans/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function createPatchRun(payload: {
  repo_id: string;
  request: string;
  autonomy_level?: string;
  privacy_mode?: string;
  target_branch?: string;
  constraints?: Record<string, unknown>;
}): Promise<{ ok: boolean; patch_run: PatchRun }> {
  return requestJson<{ ok: boolean; patch_run: PatchRun }>('/api/patch-runs', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchPatchRuns(): Promise<{ patch_runs: PatchRun[] }> {
  return requestJson<{ patch_runs: PatchRun[] }>('/api/patch-runs');
}

export function fetchPatchRun(id: string): Promise<{ patch_run: PatchRun; events: PatchEvent[] }> {
  return requestJson<{ patch_run: PatchRun; events: PatchEvent[] }>(`/api/patch-runs/${id}`);
}

export function fetchPatchRunFiles(id: string): Promise<{ files: PatchArtifactFile[] }> {
  return requestJson<{ files: PatchArtifactFile[] }>(`/api/patch-runs/${id}/files`);
}

export function readPatchRunFile(id: string, path: string): Promise<{ file: PatchArtifactFile }> {
  return requestJson<{ file: PatchArtifactFile }>(
    `/api/patch-runs/${id}/files/${encodeURIComponent(path)}`,
  );
}

export function savePatchRunPlanMarkdown(id: string, content: string): Promise<{ ok: boolean; patch_run: PatchRun; file: PatchArtifactFile }> {
  return requestJson<{ ok: boolean; patch_run: PatchRun; file: PatchArtifactFile }>(`/api/patch-runs/${id}/plan-md`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  });
}

export function revisePatchRunPlanMarkdown(
  id: string,
  payload: { instruction: string; current_content?: string; source_refs?: string[] },
): Promise<{ ok: boolean; patch_run: PatchRun; file: PatchArtifactFile }> {
  return requestJson<{ ok: boolean; patch_run: PatchRun; file: PatchArtifactFile }>(`/api/patch-runs/${id}/plan-md/revise`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function promotePatchRunPlanMarkdown(
  id: string,
  content = '',
): Promise<{ ok: boolean; patch_run: PatchRun; memory: PermanentMemorySource }> {
  return requestJson<{ ok: boolean; patch_run: PatchRun; memory: PermanentMemorySource }>(
    `/api/patch-runs/${id}/plan-md/promote-memory`,
    {
      method: 'POST',
      body: JSON.stringify({ content }),
    },
  );
}

export function analyzePatchRun(id: string): Promise<{ ok: boolean; patch_run: PatchRun; events: PatchEvent[] }> {
  return requestJson<{ ok: boolean; patch_run: PatchRun; events: PatchEvent[] }>(`/api/patch-runs/${id}/analyze`, {
    method: 'POST',
  });
}

export function approvePatchRunPlan(id: string, decision = 'approve', comment = ''): Promise<{ ok: boolean; patch_run: PatchRun }> {
  return requestJson<{ ok: boolean; patch_run: PatchRun }>(`/api/patch-runs/${id}/approve-plan`, {
    method: 'POST',
    body: JSON.stringify({ decision, comment }),
  });
}

export function draftPatchRunDiff(id: string): Promise<{ ok: boolean; patch_run: PatchRun; events: PatchEvent[] }> {
  return requestJson<{ ok: boolean; patch_run: PatchRun; events: PatchEvent[] }>(`/api/patch-runs/${id}/draft-diff`, {
    method: 'POST',
  });
}

export function writePatchRunMemory(id: string): Promise<{ ok: boolean; patch_run: PatchRun; memory: Record<string, unknown> }> {
  return requestJson<{ ok: boolean; patch_run: PatchRun; memory: Record<string, unknown> }>(`/api/patch-runs/${id}/write-memory`, {
    method: 'POST',
  });
}

export function applyPatchRunDiff(
  id: string,
  payload: { branch_name?: string; apply?: boolean } = {},
): Promise<{ ok: boolean; patch_run: PatchRun; execution: Record<string, unknown> }> {
  return requestJson<{ ok: boolean; patch_run: PatchRun; execution: Record<string, unknown> }>(`/api/patch-runs/${id}/apply-diff`, {
    method: 'POST',
    body: JSON.stringify({ arguments: payload }),
  });
}

export function runPatchRunTests(
  id: string,
  payload: { command?: string; dry_run?: boolean } = {},
): Promise<{ ok: boolean; patch_run: PatchRun; test_result: Record<string, unknown> }> {
  return requestJson<{ ok: boolean; patch_run: PatchRun; test_result: Record<string, unknown> }>(`/api/patch-runs/${id}/run-tests`, {
    method: 'POST',
    body: JSON.stringify({ arguments: payload }),
  });
}

export function analyzePatchRunTestFailure(
  id: string,
  output = '',
): Promise<{ ok: boolean; patch_run: PatchRun; analysis: Record<string, unknown> }> {
  return requestJson<{ ok: boolean; patch_run: PatchRun; analysis: Record<string, unknown> }>(`/api/patch-runs/${id}/analyze-test-failure`, {
    method: 'POST',
    body: JSON.stringify({ arguments: { output } }),
  });
}

export function draftPatchRunPr(
  id: string,
  payload: { branch_name?: string } = {},
): Promise<{ ok: boolean; patch_run: PatchRun; pr_draft: Record<string, unknown>; memory: Record<string, unknown> }> {
  return requestJson<{ ok: boolean; patch_run: PatchRun; pr_draft: Record<string, unknown>; memory: Record<string, unknown> }>(`/api/patch-runs/${id}/draft-pr`, {
    method: 'POST',
    body: JSON.stringify({ arguments: payload }),
  });
}

export function fetchAgentPlans(): Promise<{ plans: AgentPlan[] }> {
  return requestJson<{ plans: AgentPlan[] }>('/api/agent/plans');
}

export function approveAgentPlan(id: string): Promise<{ ok: boolean; plan: AgentPlan }> {
  return requestJson<{ ok: boolean; plan: AgentPlan }>(`/api/agent/plans/${id}/approve`, { method: 'POST' });
}

export function runAgentPlan(id: string): Promise<{ ok: boolean; run: Record<string, unknown> }> {
  return requestJson<{ ok: boolean; run: Record<string, unknown> }>(`/api/agent/plans/${id}/run`, { method: 'POST' });
}

export function fetchSkills(): Promise<{ skills: SkillDescriptor[] }> {
  return requestJson<{ skills: SkillDescriptor[] }>('/api/skills');
}

export function runSkill(
  skillId: string,
  inputs: Record<string, unknown>,
): Promise<{ ok: boolean; result: SkillRunResult }> {
  return requestJson<{ ok: boolean; result: SkillRunResult }>(
    `/api/skills/${encodeURIComponent(skillId)}/run`,
    {
      method: 'POST',
      body: JSON.stringify({ inputs }),
    },
  );
}

export function createSkill(
  payload: SkillCreateInput,
): Promise<{ ok: boolean; skill: SkillDescriptor; skills: SkillDescriptor[] }> {
  return requestJson<{ ok: boolean; skill: SkillDescriptor; skills: SkillDescriptor[] }>(
    '/api/skills',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}
