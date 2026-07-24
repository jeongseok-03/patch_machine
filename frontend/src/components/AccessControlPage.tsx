import { useEffect, useState } from 'react';

import {
  approveAccountRequest,
  fetchAccountRequests,
  fetchAccessControl,
  rejectAccountRequest,
  saveDepartmentPermission,
  type AccountRequest,
  type AccessControlPayload,
  type PositionRecord,
} from '../api';

export default function AccessControlPage() {
  const [acl, setAcl] = useState<AccessControlPayload | null>(null);
  const [requests, setRequests] = useState<AccountRequest[]>([]);
  const [message, setMessage] = useState('');

  async function refresh() {
    const [nextAcl, nextRequests] = await Promise.all([fetchAccessControl(), fetchAccountRequests()]);
    setAcl(nextAcl);
    setRequests(nextRequests.requests);
  }

  useEffect(() => {
    void refresh();
  }, []);

  const departments = acl?.departments ?? [];
  const positions = [...(acl?.positions ?? [])].sort((a, b) => (b.display_order ?? 0) - (a.display_order ?? 0));
  const policies = acl?.department_permissions ?? [];

  function policyPermissions(departmentId: string, positionId: string): string[] | null {
    return policies.find((entry) => entry.department_id === departmentId && entry.position_id === positionId)?.permissions ?? null;
  }

  function effectivePermissions(position: PositionRecord, departmentId?: string): string[] {
    if (departmentId) {
      const scoped = policyPermissions(departmentId, position.id);
      if (scoped) return scoped;
    }
    return position.permissions ?? [];
  }

  async function toggleDepartmentPermission(departmentId: string, position: PositionRecord, permission: string, checked: boolean) {
    const current = effectivePermissions(position, departmentId);
    const next = checked ? [...new Set([...current, permission])] : current.filter((entry) => entry !== permission);
    try {
      setAcl(await saveDepartmentPermission({ department_id: departmentId, position_id: position.id, permissions: next }));
      setMessage(`${position.name} · ${departmentId} 부서 권한을 저장했습니다.`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '부서 권한 저장 실패');
    }
  }

  return (
    <section className="page-grid org-grid">
      <div className="panel">
        <p className="eyebrow">Department access</p>
        <h2>부서별 예외 접근 권한</h2>
        <p className="muted">직급 자체 권한은 인사관리에서 직급을 만들 때 정합니다. 이 화면은 특정 부서에서만 더 좁히거나 넓힐 예외 권한만 관리합니다.</p>
        <div className="org-list">
          {departments.map((department) => (
            <article className="org-card" key={department.id}>
              <strong>{department.name}</strong>
              <p className="muted">{department.id}{department.parent_id ? ` · 상위 ${department.parent_id}` : ''}</p>
              {positions.map((position) => (
                <details key={`${department.id}:${position.id}`} className="advanced-panel">
                  <summary>{position.name} 접근 권한</summary>
                  <div className="permission-grid">
                    {acl?.permissions.map((permission) => {
                      const enabled = effectivePermissions(position, department.id).includes('*') || effectivePermissions(position, department.id).includes(permission);
                      return (
                        <label key={permission} className="permission-item">
                          <input
                            type="checkbox"
                            checked={enabled}
                            onChange={(event) => void toggleDepartmentPermission(department.id, position, permission, event.target.checked)}
                          />
                          <span>{permission}</span>
                        </label>
                      );
                    })}
                  </div>
                </details>
              ))}
            </article>
          ))}
          {departments.length === 0 ? <p className="muted">인사관리에서 부서를 먼저 생성하세요.</p> : null}
        </div>
      </div>

      <div className="panel">
        <p className="eyebrow">Account Requests</p>
        <h2>계정 개설 요청</h2>
        <div className="org-list">
          {requests.filter((entry) => entry.status === 'pending').map((entry) => (
            <article className="org-card" key={entry.id}>
              <strong>{entry.display_name}</strong>
              <p className="muted">{entry.user_id} · {entry.title || '직함 미입력'} · {entry.created_at}</p>
              <div className="form-actions">
                <button type="button" onClick={() => approveAccountRequest(entry.id).then(() => void refresh())}>승인</button>
                <button className="secondary-button" type="button" onClick={() => rejectAccountRequest(entry.id).then(() => void refresh())}>거절</button>
              </div>
            </article>
          ))}
          {requests.filter((entry) => entry.status === 'pending').length === 0 ? (
            <p className="muted">대기 중인 계정 요청이 없습니다.</p>
          ) : null}
        </div>
      </div>

      {message ? <p className="muted org-message">{message}</p> : null}
    </section>
  );
}
