import { Suspense, lazy, useEffect, useState, type ComponentType } from 'react';

import {
  fetchApiStatus,
  fetchCurrentUser,
  fetchOperationsMemory,
  fetchSetupStatus,
  type ApiStatus,
  type AuthUser,
  type OperationsMemory,
} from './api';
import AppShell from './components/AppShell';
import { hasIncompleteInitialSetupDraft } from './components/setup/setupDraft';

// Every page is code-split: only the shell ships in the initial bundle and the
// active page's chunk loads on demand.
const AccessControlPage = lazy(() => import('./components/AccessControlPage'));
const AdminSettingsPage = lazy(() => import('./components/AdminSettingsPage'));
const AuthPage = lazy(() => import('./components/AuthPage'));
const ContributorGuide = lazy(() => import('./components/ContributorGuide'));
const DocumentAutomationPage = lazy(() => import('./components/DocumentAutomationPage'));
const DocumentsViewerPage = lazy(() => import('./components/DocumentsViewerPage'));
const HandoverPage = lazy(() => import('./components/HandoverPage'));
const HiringPage = lazy(() => import('./components/HiringPage'));
const HomePage = lazy(() => import('./components/HomePage'));
const IntegrationsPage = lazy(() => import('./components/IntegrationsPage'));
const LlmChatPage = lazy(() => import('./components/LlmChatPage'));
const OperationsMemoryForm = lazy(() => import('./components/OperationsMemoryForm'));
const PersonnelManagementPage = lazy(() => import('./components/PersonnelManagementPage'));
const ProgressLogPage = lazy(() => import('./components/ProgressLogPage'));
const SystemStatus = lazy(() => import('./components/SystemStatus'));
const TokenLimitsPage = lazy(() => import('./components/TokenLimitsPage'));
const UploadPage = lazy(() => import('./components/UploadPage'));
const UserProfilePage = lazy(() => import('./components/UserProfilePage'));
const WorkArchitecturePage = lazy(() => import('./components/WorkArchitecturePage'));
const WorkItemsPage = lazy(() => import('./components/WorkItemsPage'));
const WorkMemoryPage = lazy(() => import('./components/WorkMemoryPage'));
const WorkSchedulePage = lazy(() => import('./components/WorkSchedulePage'));
const SkillsPage = lazy(() => import('./components/SkillsPage'));
const WorkflowStatusPage = lazy(() => import('./components/WorkflowStatusPage'));
const AiAgentPage = lazy(() => import('./components/ai/AiAgentPage'));
const InitialOfficeSetupWizard = lazy(() => import('./components/setup/InitialOfficeSetupWizard'));

const emptyMemory: OperationsMemory = {
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

type Page =
  | 'home'
  | 'profile'
  | 'dashboard'
  | 'chat'
  | 'assistant'
  | 'skills'
  | 'progress'
  | 'work'
  | 'work-memory'
  | 'work-architecture'
  | 'work-schedule'
  | 'hiring'
  | 'documents'
  | 'documents-viewer'
  | 'handover'
  | 'integrations'
  | 'uploads'
  | 'admin'
  | 'access'
  | 'workflow-status'
  | 'token-limits'
  | 'personnel';

type NavItem = { id: Page; label: string; group: string; requiredPermission?: string };

const navItems: NavItem[] = [
  { id: 'home', label: '홈', group: '사이트' },
  { id: 'profile', label: '유저 프로필', group: '사이트' },
  { id: 'work', label: '업무 현황', group: '회사 업무 운영' },
  { id: 'work-architecture', label: '프로세스 설계', group: '회사 업무 운영', requiredPermission: 'memory:write' },
  { id: 'progress', label: '진행 로그', group: '회사 업무 운영' },
  { id: 'work-memory', label: '네고티움 메모리', group: '네고티움 메모리 관리', requiredPermission: 'memory:write' },
  { id: 'assistant', label: 'AI 어시스턴트', group: 'AI 에이전트', requiredPermission: 'llm:chat' },
  { id: 'skills', label: '스킬 실행', group: 'AI 에이전트', requiredPermission: 'work:read' },
  { id: 'hiring', label: '채용/면접', group: '오피스워크' },
  { id: 'work-schedule', label: '업무 배정', group: '오피스워크', requiredPermission: 'memory:write' },
  { id: 'documents', label: '문서 자동화', group: '오피스워크' },
  { id: 'documents-viewer', label: '문서 열람', group: '오피스워크', requiredPermission: 'documents:read' },
  { id: 'handover', label: '인수인계', group: '오피스워크' },
  { id: 'chat', label: '코딩 에이전트 계획서 작성', group: '오피스워크' },
  { id: 'dashboard', label: '회사 운영 설정', group: '조직·운영 관리', requiredPermission: 'memory:write' },
  { id: 'personnel', label: '인사관리', group: '조직·운영 관리', requiredPermission: 'admin:users' },
  { id: 'uploads', label: '업로드', group: '시스템 관리', requiredPermission: 'uploads:write' },
  { id: 'admin', label: 'API 키·로컬 에이전트', group: '시스템 관리', requiredPermission: 'admin:api_keys' },
  { id: 'workflow-status', label: '워크플로우 상태', group: '시스템 관리', requiredPermission: 'admin:users' },
  { id: 'integrations', label: 'MCP 서버 연동', group: '시스템 관리', requiredPermission: 'admin:mcp' },
  { id: 'token-limits', label: '토큰 사용량·한도', group: '시스템 관리', requiredPermission: 'admin:token_limits' },
];

// Pages that take no props render straight from this map; pages needing props
// (home/profile/dashboard/integrations) are handled explicitly in renderPage.
const simplePages: Partial<Record<Page, ComponentType>> = {
  assistant: LlmChatPage,
  chat: AiAgentPage,
  progress: ProgressLogPage,
  work: WorkItemsPage,
  'work-memory': WorkMemoryPage,
  'work-architecture': WorkArchitecturePage,
  'work-schedule': WorkSchedulePage,
  hiring: HiringPage,
  documents: DocumentAutomationPage,
  'documents-viewer': DocumentsViewerPage,
  handover: HandoverPage,
  uploads: UploadPage,
  admin: AdminSettingsPage,
  access: AccessControlPage,
  'workflow-status': WorkflowStatusPage,
  skills: SkillsPage,
  'token-limits': TokenLimitsPage,
  personnel: PersonnelManagementPage,
};

function canAccess(user: AuthUser, item: NavItem): boolean {
  if (!item.requiredPermission) return true;
  const permissions = user.permissions || [];
  return permissions.includes('*') || permissions.includes(item.requiredPermission);
}

const pageFallback = <section className="panel">로딩 중...</section>;

export default function App() {
  const [memory, setMemory] = useState<OperationsMemory>(emptyMemory);
  const [status, setStatus] = useState<ApiStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<Page>('home');
  const [setupRequired, setSetupRequired] = useState(false);
  const [resumeInitialSetup, setResumeInitialSetup] = useState(false);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  async function refresh() {
    setError(null);
    try {
      const [nextMemory, nextStatus] = await Promise.all([
        fetchOperationsMemory(),
        fetchApiStatus(),
      ]);
      setMemory(nextMemory);
      setStatus(nextStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  }

  async function bootstrap() {
    setError(null);
    try {
      const setup = await fetchSetupStatus();
      setSetupRequired(setup.setup_required);
      setResumeInitialSetup(hasIncompleteInitialSetupDraft());
      if (!setup.setup_required) {
        const me = await fetchCurrentUser();
        setCurrentUser(me.authenticated ? me.user : null);
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.');
      setLoading(false);
    }
  }

  useEffect(() => {
    void bootstrap();
  }, []);

  if (loading) {
    return <main className="auth-layout"><section className="panel">로딩 중...</section></main>;
  }

  if (setupRequired || (resumeInitialSetup && currentUser)) {
    return (
      <>
        {error ? <div className="alert">API 연결 실패: {error}</div> : null}
        <Suspense fallback={pageFallback}>
          <InitialOfficeSetupWizard
            initialUser={currentUser}
            onAuthenticated={(user) => {
              setCurrentUser(user);
              setSetupRequired(false);
              setResumeInitialSetup(false);
              void refresh();
            }}
          />
        </Suspense>
      </>
    );
  }

  if (!currentUser) {
    return (
      <>
        {error ? <div className="alert">API 연결 실패: {error}</div> : null}
        <Suspense fallback={pageFallback}>
          <AuthPage
            setupRequired={setupRequired}
            onAuthenticated={(user) => {
              setCurrentUser(user);
              setSetupRequired(false);
              setResumeInitialSetup(hasIncompleteInitialSetupDraft());
              void refresh();
            }}
          />
        </Suspense>
      </>
    );
  }

  const visibleNavItems = navItems.filter((item) => canAccess(currentUser, item));
  const activePageAllowed = visibleNavItems.some((item) => item.id === page);
  const activePage: Page = activePageAllowed ? page : 'profile';

  function renderPage() {
    if (activePage === 'home') {
      return <HomePage memory={memory} status={status} onAction={(next) => setPage(next as Page)} />;
    }
    if (activePage === 'profile') {
      return <UserProfilePage user={currentUser!} />;
    }
    if (activePage === 'dashboard') {
      return (
        <>
          <section className="dashboard-grid">
            <OperationsMemoryForm
              disabled={loading}
              memory={memory}
              onSaved={(nextMemory) => {
                setMemory(nextMemory);
                void refresh();
              }}
            />
            <SystemStatus loading={loading} status={status} onRefresh={() => void refresh()} />
          </section>
          <ContributorGuide />
        </>
      );
    }
    if (activePage === 'integrations') {
      return <IntegrationsPage permissions={currentUser!.permissions || []} />;
    }
    const PageComponent = simplePages[activePage];
    return PageComponent ? <PageComponent /> : <UserProfilePage user={currentUser!} />;
  }

  return (
    <AppShell page={activePage} navItems={visibleNavItems} onNavigate={setPage} user={currentUser} onLoggedOut={() => setCurrentUser(null)}>
      {error ? <div className="alert">API 연결 실패: {error}</div> : null}
      <Suspense fallback={pageFallback}>{renderPage()}</Suspense>
    </AppShell>
  );
}
