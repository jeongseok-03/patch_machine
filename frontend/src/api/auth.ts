import { requestJson } from './http';
import type {
  AuthSession,
  CurrentUser,
} from './types';

export function fetchSetupStatus(): Promise<{ setup_required: boolean }> {
  return requestJson<{ setup_required: boolean }>('/api/auth/setup-status');
}

export function setupAdmin(payload: {
  user_id: string;
  display_name: string;
  password: string;
  title: string;
}): Promise<AuthSession> {
  return requestJson<AuthSession>('/api/auth/setup-admin', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function login(payload: { user_id: string; password: string }): Promise<AuthSession> {
  return requestJson<AuthSession>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function logout(): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>('/api/auth/logout', { method: 'POST' });
}

export function fetchCurrentUser(): Promise<CurrentUser> {
  return requestJson<CurrentUser>('/api/auth/me');
}
