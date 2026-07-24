import type { AuthUser } from '../api';

type Props = {
  user: AuthUser;
};

function permissionSummary(permissions: string[] = []): string {
  if (permissions.includes('*')) return '전체 관리 권한';
  if (permissions.length === 0) return '권한 정보 없음';
  return permissions.join(', ');
}

export default function UserProfilePage({ user }: Props) {
  const permissions = user.permissions || [];
  const isAdmin = permissions.includes('*') || permissions.some((permission) => permission.startsWith('admin:'));

  return (
    <section className="page-grid">
      <div className="panel">
        <p className="eyebrow">User profile</p>
        <h2>유저 프로필</h2>
        <div className="profile-facts">
          <p>
            <strong>이름</strong>
            <span>{user.display_name || user.id}</span>
          </p>
          <p>
            <strong>사용자 ID</strong>
            <span>{user.id}</span>
          </p>
          <p>
            <strong>직함</strong>
            <span>{user.title || '미지정'}</span>
          </p>
          <p>
            <strong>역할</strong>
            <span>{user.role_id || 'viewer'}</span>
          </p>
        </div>
      </div>

      <div className="panel">
        <p className="eyebrow">Agent user spec</p>
        <h2>에이전트가 이해하는 사용자 명세</h2>
        <div className="log-list">
          <article className="log-card">
            <strong>업무상 위치</strong>
            <p>
              {user.display_name || user.id}님은 {user.title || '직함 미지정'} 역할로 등록되어 있으며,
              시스템 역할은 <code>{user.role_id || 'viewer'}</code>입니다.
            </p>
          </article>
          <article className="log-card">
            <strong>가능한 작업 권한</strong>
            <p>{permissionSummary(permissions)}</p>
          </article>
          <article className="log-card">
            <strong>AI 에이전트 운영 메모</strong>
            <p>
              {isAdmin
                ? '관리 권한이 있으므로 로컬 에이전트, MCP 서버 연동, 사용자/권한 설정 같은 시스템 운영 작업을 수행할 수 있습니다.'
                : '일반 사용자로 분류됩니다. AI 에이전트는 승인된 업무 실행과 조회 가능한 회사 운영 정보 안에서 응답해야 합니다.'}
            </p>
          </article>
        </div>
      </div>
    </section>
  );
}
