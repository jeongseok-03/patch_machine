import { requestJson } from './http';
import type {
  AccessControlPayload,
  AccountRequest,
  ApiKeyInfo,
  ContextFirewallAuditRecord,
  ContextFirewallDecision,
  DepartmentPermissionRecord,
  DepartmentRecord,
  OrgRoster,
  PositionRecord,
  RoleRecord,
  UserRecord,
} from './types';

export function createLoginUser(payload: UserRecord & { password: string }): Promise<{ ok: boolean; access_control: AccessControlPayload }> {
  return requestJson<{ ok: boolean; access_control: AccessControlPayload }>('/api/admin/users/create-login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function requestAccount(payload: {
  user_id: string;
  display_name: string;
  title: string;
  password: string;
}): Promise<{ ok: boolean; request: AccountRequest }> {
  return requestJson<{ ok: boolean; request: AccountRequest }>('/api/account-requests', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function sanitizeContextFirewall(payload: {
  destination?: string;
  task_type?: string;
  source_uri?: string;
  content: unknown;
}): Promise<{ ok: boolean; result: ContextFirewallDecision }> {
  return requestJson<{ ok: boolean; result: ContextFirewallDecision }>('/api/security/context-firewall/sanitize', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchContextFirewallAudit(limit = 50): Promise<{ records: ContextFirewallAuditRecord[]; count: number }> {
  return requestJson<{ records: ContextFirewallAuditRecord[]; count: number }>(`/api/security/context-firewall/audit?limit=${limit}`);
}

export function fetchContextFirewallPolicy(): Promise<{ policy: Record<string, unknown> }> {
  return requestJson<{ policy: Record<string, unknown> }>('/api/security/context-firewall/policy');
}

export function fetchOrgRoster(): Promise<OrgRoster> {
  return requestJson<OrgRoster>('/api/org/roster');
}

export function fetchApiKeys(): Promise<{ providers: ApiKeyInfo[] }> {
  return requestJson<{ providers: ApiKeyInfo[] }>('/api/admin/api-keys');
}

export function saveApiKey(payload: {
  provider: string;
  api_key: string;
  model: string;
}): Promise<{ ok: boolean; providers: ApiKeyInfo[] }> {
  return requestJson<{ ok: boolean; providers: ApiKeyInfo[] }>(`/api/admin/api-keys/${payload.provider}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function deleteApiKey(provider: string): Promise<{ ok: boolean; providers: ApiKeyInfo[] }> {
  return requestJson<{ ok: boolean; providers: ApiKeyInfo[] }>(`/api/admin/api-keys/${provider}`, {
    method: 'DELETE',
  });
}

export function fetchAccessControl(): Promise<AccessControlPayload> {
  return requestJson<AccessControlPayload>('/api/admin/access-control');
}

export function saveRole(payload: RoleRecord): Promise<AccessControlPayload> {
  return requestJson<AccessControlPayload>('/api/admin/roles', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteRole(roleId: string): Promise<AccessControlPayload> {
  return requestJson<AccessControlPayload>(`/api/admin/roles/${roleId}`, { method: 'DELETE' });
}

export function saveUser(payload: UserRecord): Promise<AccessControlPayload> {
  return requestJson<AccessControlPayload>('/api/admin/users', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteUser(userId: string): Promise<AccessControlPayload> {
  return requestJson<AccessControlPayload>(`/api/admin/users/${userId}`, { method: 'DELETE' });
}

export function saveDepartment(payload: DepartmentRecord): Promise<AccessControlPayload> {
  return requestJson<AccessControlPayload>('/api/admin/departments', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteDepartment(departmentId: string): Promise<AccessControlPayload> {
  return requestJson<AccessControlPayload>(`/api/admin/departments/${departmentId}`, { method: 'DELETE' });
}

export function savePosition(payload: PositionRecord): Promise<AccessControlPayload> {
  return requestJson<AccessControlPayload>('/api/admin/positions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deletePosition(positionId: string): Promise<AccessControlPayload> {
  return requestJson<AccessControlPayload>(`/api/admin/positions/${positionId}`, { method: 'DELETE' });
}

export function saveDepartmentPermission(payload: DepartmentPermissionRecord): Promise<AccessControlPayload> {
  return requestJson<AccessControlPayload>('/api/admin/department-permissions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchAccountRequests(): Promise<{ requests: AccountRequest[] }> {
  return requestJson<{ requests: AccountRequest[] }>('/api/admin/account-requests');
}

export function approveAccountRequest(requestId: string): Promise<{ ok: boolean; request: AccountRequest }> {
  return requestJson<{ ok: boolean; request: AccountRequest }>(
    `/api/admin/account-requests/${requestId}/approve`,
    { method: 'POST' },
  );
}

export function rejectAccountRequest(requestId: string): Promise<{ ok: boolean; request: AccountRequest }> {
  return requestJson<{ ok: boolean; request: AccountRequest }>(
    `/api/admin/account-requests/${requestId}/reject`,
    { method: 'POST' },
  );
}
