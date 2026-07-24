import { requestJson } from './http';
import type {
  DiscordConnectorConfig,
  GitHubConnectorConfig,
  IntegrationConfig,
  IntegrationStatus,
  IssueCluster,
  McpAuditRecord,
  McpPromptDescriptor,
  McpResourceDescriptor,
  McpToolDescriptor,
  TestRequirement,
} from './types';

export function fetchMcpHubTools(): Promise<{ tools: McpToolDescriptor[]; transport: string; count: number }> {
  return requestJson<{ tools: McpToolDescriptor[]; transport: string; count: number }>('/api/mcp-hub/tools');
}

export function fetchMcpHubResources(): Promise<{ resources: McpResourceDescriptor[]; count: number }> {
  return requestJson<{ resources: McpResourceDescriptor[]; count: number }>('/api/mcp-hub/resources');
}

export function fetchMcpHubPrompts(): Promise<{ prompts: McpPromptDescriptor[]; count: number }> {
  return requestJson<{ prompts: McpPromptDescriptor[]; count: number }>('/api/mcp-hub/prompts');
}

export function fetchMcpHubAudit(limit = 50): Promise<{ records: McpAuditRecord[]; count: number }> {
  return requestJson<{ records: McpAuditRecord[]; count: number }>(`/api/mcp-hub/audit?limit=${limit}`);
}

export function callMcpMemoryTool<T = Record<string, unknown>>(
  tool: string,
  argumentsPayload: Record<string, unknown>,
): Promise<{ ok: boolean; tool: string; result: T }> {
  return requestJson<{ ok: boolean; tool: string; result: T }>(`/api/mcp-hub/tools/${tool}`, {
    method: 'POST',
    body: JSON.stringify({ arguments: argumentsPayload }),
  });
}

export function searchIssueMemory(query: string, limit = 8): Promise<{ clusters: IssueCluster[]; total: number }> {
  return callMcpMemoryTool<{ clusters: IssueCluster[]; total: number }>('memory.search_issues', { query, limit }).then(
    (response) => response.result,
  );
}

export function createIssueMemoryTestRequirement(payload: {
  patch_candidate_id: string;
  title: string;
  requirement_type: string;
  given: string;
  when: string;
  then: string;
  priority: string;
}): Promise<{ test_requirement: TestRequirement }> {
  return callMcpMemoryTool<{ test_requirement: TestRequirement }>('memory.create_test_requirement', payload).then(
    (response) => response.result,
  );
}

export function fetchGithubIntegration(): Promise<IntegrationStatus> {
  return requestJson<IntegrationStatus>('/api/integrations/github');
}

export function fetchDiscordIntegration(): Promise<IntegrationStatus> {
  return requestJson<IntegrationStatus>('/api/integrations/discord');
}

export function fetchIntegrationConfig(): Promise<IntegrationConfig> {
  return requestJson<IntegrationConfig>('/api/integrations/config');
}

export function saveGithubConnector(payload: GitHubConnectorConfig): Promise<IntegrationConfig> {
  return requestJson<IntegrationConfig>('/api/integrations/github', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function saveDiscordConnector(payload: DiscordConnectorConfig): Promise<IntegrationConfig> {
  return requestJson<IntegrationConfig>('/api/integrations/discord', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}
