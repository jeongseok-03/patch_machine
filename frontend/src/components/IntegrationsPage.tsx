import { useEffect, useMemo, useState } from 'react';

import {
  fetchDiscordIntegration,
  fetchGithubIntegration,
  fetchIntegrationConfig,
  fetchMcpHubAudit,
  fetchMcpHubPrompts,
  fetchMcpHubResources,
  fetchMcpHubTools,
  saveDiscordConnector,
  saveGithubConnector,
  type DiscordChannelBinding,
  type DiscordConnectorConfig,
  type GitHubConnectorConfig,
  type IntegrationConfig,
  type IntegrationStatus,
  type McpAuditRecord,
  type McpPromptDescriptor,
  type McpResourceDescriptor,
  type McpToolDescriptor,
} from '../api';

type IntegrationsPageProps = {
  permissions?: string[];
};

type IntegrationTab = 'overview' | 'connectors' | 'mcp' | 'audit';

const DEFAULT_GITHUB_FORM: GitHubConnectorConfig = {
  enabled: false,
  allowed_repos: [],
  trigger_label: 'negotium',
  webhook_secret: '',
  app_token: '',
  webhook_secret_present: false,
  app_token_present: false,
  event_forms: ['issue', 'pull_request', 'repository', 'push'],
};

const DEFAULT_DISCORD_FORM: DiscordConnectorConfig = {
  enabled: false,
  bot_token: '',
  bot_token_present: false,
  guild_allowlist: [],
  channel_bindings: [],
  command_forms: ['bug_report', 'thread_digest', 'slash_command'],
};

export default function IntegrationsPage({ permissions = [] }: IntegrationsPageProps) {
  const [github, setGithub] = useState<IntegrationStatus | null>(null);
  const [discord, setDiscord] = useState<IntegrationStatus | null>(null);
  const [tools, setTools] = useState<McpToolDescriptor[]>([]);
  const [resources, setResources] = useState<McpResourceDescriptor[]>([]);
  const [prompts, setPrompts] = useState<McpPromptDescriptor[]>([]);
  const [auditRecords, setAuditRecords] = useState<McpAuditRecord[]>([]);
  const [config, setConfig] = useState<IntegrationConfig | null>(null);
  const [configError, setConfigError] = useState<string>('');
  const [activeTab, setActiveTab] = useState<IntegrationTab>('overview');

  const canManageIntegrations = useMemo(
    () => permissions.includes('*') || permissions.includes('admin:integrations'),
    [permissions],
  );

  async function refresh() {
    const [nextGithub, nextDiscord, nextTools, nextResources, nextPrompts, nextAudit] = await Promise.all([
      fetchGithubIntegration(),
      fetchDiscordIntegration(),
      fetchMcpHubTools(),
      fetchMcpHubResources(),
      fetchMcpHubPrompts(),
      fetchMcpHubAudit().catch(() => ({ records: [], count: 0 })),
    ]);
    setGithub(nextGithub);
    setDiscord(nextDiscord);
    setTools(nextTools.tools);
    setResources(nextResources.resources);
    setPrompts(nextPrompts.prompts);
    setAuditRecords(nextAudit.records);
    if (canManageIntegrations) {
      try {
        const next = await fetchIntegrationConfig();
        setConfig(next);
        setConfigError('');
      } catch (err) {
        setConfigError(err instanceof Error ? err.message : '커넥터 설정을 불러오지 못했습니다.');
      }
    }
  }

  useEffect(() => {
    void refresh();
  }, [canManageIntegrations]);

  return (
    <section className="page-workspace">
      <div className="workspace-hero">
        <div className="panel">
          <p className="eyebrow">MCP integrations</p>
          <h2>MCP 서버 연동</h2>
          <p className="muted">
            네고티움이 외부 플랫폼 양식을 이해하도록 MCP 서버와 플랫폼 커넥터를 관리합니다. GitHub/Discord는 기본
            커넥터이며, 이후 Notion, Slack, Jira, Google Drive 같은 서버를 탭 단위로 추가할 수 있습니다.
          </p>
        </div>
        <div className="compact-stat-strip">
          <div className="compact-stat">
            <strong>{[github, discord].filter((item) => item?.configured).length}</strong>
            <span>Configured</span>
          </div>
          <div className="compact-stat">
            <strong>{tools.length}</strong>
            <span>MCP tools</span>
          </div>
          <div className="compact-stat">
            <strong>{auditRecords.length}</strong>
            <span>Recent audits</span>
          </div>
        </div>
      </div>

      <nav className="workspace-tabs" aria-label="MCP integrations sections">
        {([
          ['overview', 'Overview'],
          ['connectors', 'Connectors'],
          ['mcp', 'MCP Hub'],
          ['audit', 'Audit'],
        ] as const).map(([tab, label]) => (
          <button
            key={tab}
            type="button"
            className={activeTab === tab ? 'workspace-tab active' : 'workspace-tab'}
            onClick={() => setActiveTab(tab)}
          >
            {label}
          </button>
        ))}
      </nav>

      {activeTab === 'overview' ? (
        <div className="panel">
          <div className="connector-grid">
            <ConnectorCard name="GitHub" description="Issue, PR, Repository 이벤트 양식" status={github} />
            <ConnectorCard name="Discord" description="버그 문의 채널, 스레드, 명령어 양식" status={discord} />
            <ConnectorCard
              name="MCP Tool Hub"
              description={`Tools ${tools.length}개 · Resources ${resources.length}개 · Prompts ${prompts.length}개`}
              status={{ ok: true, configured: tools.length > 0, reason: '', items: [] }}
            />
            <ConnectorCard name="Notion" description="문서/태스크 DB MCP 서버 (준비 중)" status={null} comingSoon />
            <ConnectorCard name="Slack/Jira/Drive" description="추가 업무 플랫폼 MCP 서버 (준비 중)" status={null} comingSoon />
          </div>
        </div>
      ) : null}

      {activeTab === 'connectors' ? (
        <div className="workspace-split">
          <div className="workspace-sidebar">
            <IntegrationPanel title="GitHub Issues" status={github} />
            <IntegrationPanel title="Discord Channels" status={discord} />
          </div>
          <div className="workspace-detail">
            {canManageIntegrations ? (
              <ConnectorConfigPanel
                config={config}
                onSavedGithub={(next) => setConfig(next)}
                onSavedDiscord={(next) => setConfig(next)}
                onRefresh={() => void refresh()}
                error={configError}
              />
            ) : (
              <div className="panel">
                <p className="eyebrow">Connector configuration</p>
                <h2>커넥터 외부 설정</h2>
                <p className="muted">
                  관리자(admin:integrations) 권한이 있는 사용자만 GitHub/Discord 외부 설정을 편집할 수 있습니다.
                </p>
              </div>
            )}
          </div>
        </div>
      ) : null}

      {activeTab === 'mcp' ? <McpHubPanel tools={tools} resources={resources} prompts={prompts} /> : null}
      {activeTab === 'audit' ? <McpAuditPanel auditRecords={auditRecords} /> : null}
    </section>
  );
}

function ConnectorCard({
  name,
  description,
  status,
  comingSoon = false,
}: {
  name: string;
  description: string;
  status: IntegrationStatus | null;
  comingSoon?: boolean;
}) {
  const label = comingSoon ? '준비 중' : status?.configured ? (status.ok ? '연결됨' : '확인 필요') : '미설정';
  return (
    <article className="connector-card">
      <strong>{name}</strong>
      <p>{description}</p>
      <span className="status-pill">{label}</span>
    </article>
  );
}

function ConnectorConfigPanel({
  config,
  onSavedGithub,
  onSavedDiscord,
  onRefresh,
  error,
}: {
  config: IntegrationConfig | null;
  onSavedGithub: (next: IntegrationConfig) => void;
  onSavedDiscord: (next: IntegrationConfig) => void;
  onRefresh: () => void;
  error: string;
}) {
  return (
    <div className="panel">
      <p className="eyebrow">Connector configuration</p>
      <h2>외부에서 GitHub / Discord 양식 설정</h2>
      <p className="muted">
        repo 허용 목록, webhook secret, GitHub App token, Discord bot token / 채널 바인딩을 UI에서 관리합니다. 토큰은
        암호화된 secret store 에 저장되며 평문 config 파일에는 기록되지 않습니다.
      </p>
      {error ? <p className="alert" role="alert">{error}</p> : null}
      <div className="connector-config-grid">
        <GithubConnectorForm
          initial={config?.github ?? DEFAULT_GITHUB_FORM}
          onSaved={(next) => {
            onSavedGithub(next);
            onRefresh();
          }}
        />
        <DiscordConnectorForm
          initial={config?.discord ?? DEFAULT_DISCORD_FORM}
          onSaved={(next) => {
            onSavedDiscord(next);
            onRefresh();
          }}
        />
      </div>
    </div>
  );
}

function GithubConnectorForm({
  initial,
  onSaved,
}: {
  initial: GitHubConnectorConfig;
  onSaved: (next: IntegrationConfig) => void;
}) {
  const [form, setForm] = useState<GitHubConnectorConfig>(initial);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    setForm(initial);
  }, [initial]);

  const reposText = form.allowed_repos.join(', ');
  const eventsText = form.event_forms.join(', ');

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    setErrorMessage('');
    try {
      const next = await saveGithubConnector({
        ...form,
        trigger_label: form.trigger_label.trim() || 'negotium',
        allowed_repos: form.allowed_repos.map((repo) => repo.trim()).filter(Boolean),
        event_forms: form.event_forms.map((item) => item.trim()).filter(Boolean),
      });
      onSaved(next);
      setMessage('GitHub 커넥터 설정을 저장했습니다.');
      setForm({ ...next.github, app_token: '', webhook_secret: '' });
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '저장에 실패했습니다.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="connector-config-form" onSubmit={submit}>
      <header>
        <strong>GitHub 커넥터</strong>
        <span className="status-pill small">
          {form.app_token_present ? 'app token 보유' : 'app token 미설정'} ·{' '}
          {form.webhook_secret_present ? 'webhook secret 보유' : 'webhook secret 미설정'}
        </span>
      </header>
      <label className="switch-row">
        <input
          type="checkbox"
          checked={form.enabled}
          onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
        />
        <span>커넥터 활성화 (Issue / PR / Repository / Push 이벤트 처리)</span>
      </label>
      <label>
        허용 저장소 (쉼표로 구분)
        <input
          type="text"
          value={reposText}
          placeholder="acme/marketing, acme/docs"
          onChange={(event) =>
            setForm({
              ...form,
              allowed_repos: event.target.value.split(',').map((item) => item.trim()).filter(Boolean),
            })
          }
        />
      </label>
      <label>
        Trigger 라벨
        <input
          type="text"
          value={form.trigger_label}
          onChange={(event) => setForm({ ...form, trigger_label: event.target.value })}
        />
      </label>
      <label>
        Event 양식 (쉼표로 구분)
        <input
          type="text"
          value={eventsText}
          onChange={(event) =>
            setForm({
              ...form,
              event_forms: event.target.value.split(',').map((item) => item.trim()).filter(Boolean),
            })
          }
        />
      </label>
      <label>
        GitHub App Token (재입력 시 갱신, 빈칸이면 기존 값 유지)
        <input
          type="password"
          value={form.app_token}
          autoComplete="off"
          onChange={(event) => setForm({ ...form, app_token: event.target.value })}
          placeholder={form.app_token_present ? '****' : 'ghp_xxx'}
        />
      </label>
      <label>
        Webhook Secret (재입력 시 갱신)
        <input
          type="password"
          value={form.webhook_secret}
          autoComplete="off"
          onChange={(event) => setForm({ ...form, webhook_secret: event.target.value })}
          placeholder={form.webhook_secret_present ? '****' : 'random secret'}
        />
      </label>
      <div className="switch-row">
        <button className="primary" type="submit" disabled={saving}>
          {saving ? '저장 중...' : 'GitHub 설정 저장'}
        </button>
        {message ? <span className="status-pill success">{message}</span> : null}
        {errorMessage ? <span className="status-pill warn">{errorMessage}</span> : null}
      </div>
    </form>
  );
}

function DiscordConnectorForm({
  initial,
  onSaved,
}: {
  initial: DiscordConnectorConfig;
  onSaved: (next: IntegrationConfig) => void;
}) {
  const [form, setForm] = useState<DiscordConnectorConfig>(initial);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    setForm(initial);
  }, [initial]);

  const guildText = form.guild_allowlist.join(', ');
  const commandText = form.command_forms.join(', ');

  function updateBinding(index: number, patch: Partial<DiscordChannelBinding>) {
    const next = form.channel_bindings.map((binding, idx) =>
      idx === index ? { ...binding, ...patch } : binding,
    );
    setForm({ ...form, channel_bindings: next });
  }

  function addBinding() {
    setForm({
      ...form,
      channel_bindings: [
        ...form.channel_bindings,
        { guild_id: '', channel_id: '', channel_name: '', repo: '' },
      ],
    });
  }

  function removeBinding(index: number) {
    setForm({
      ...form,
      channel_bindings: form.channel_bindings.filter((_, idx) => idx !== index),
    });
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    setErrorMessage('');
    try {
      const next = await saveDiscordConnector({
        ...form,
        guild_allowlist: form.guild_allowlist.map((item) => item.trim()).filter(Boolean),
        command_forms: form.command_forms.map((item) => item.trim()).filter(Boolean),
        channel_bindings: form.channel_bindings.filter((binding) => binding.channel_id.trim()),
      });
      onSaved(next);
      setMessage('Discord 커넥터 설정을 저장했습니다.');
      setForm({ ...next.discord, bot_token: '' });
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '저장에 실패했습니다.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="connector-config-form" onSubmit={submit}>
      <header>
        <strong>Discord 커넥터</strong>
        <span className="status-pill small">
          {form.bot_token_present ? 'bot token 보유' : 'bot token 미설정'}
        </span>
      </header>
      <label className="switch-row">
        <input
          type="checkbox"
          checked={form.enabled}
          onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
        />
        <span>커넥터 활성화 (버그 문의 채널, 스레드, 명령어 양식)</span>
      </label>
      <label>
        Discord Bot Token (재입력 시 갱신)
        <input
          type="password"
          value={form.bot_token}
          autoComplete="off"
          onChange={(event) => setForm({ ...form, bot_token: event.target.value })}
          placeholder={form.bot_token_present ? '****' : 'Bot OD...'}
        />
      </label>
      <label>
        Guild allowlist (쉼표로 구분)
        <input
          type="text"
          value={guildText}
          onChange={(event) =>
            setForm({
              ...form,
              guild_allowlist: event.target.value.split(',').map((item) => item.trim()).filter(Boolean),
            })
          }
        />
      </label>
      <label>
        명령어 양식 (쉼표로 구분)
        <input
          type="text"
          value={commandText}
          onChange={(event) =>
            setForm({
              ...form,
              command_forms: event.target.value.split(',').map((item) => item.trim()).filter(Boolean),
            })
          }
        />
      </label>
      <div className="connector-bindings">
        <header>
          <strong>채널 바인딩</strong>
          <button type="button" className="secondary" onClick={addBinding}>
            + 채널 추가
          </button>
        </header>
        {form.channel_bindings.length === 0 ? (
          <p className="muted small">버그 문의 채널 / 스레드를 1개 이상 등록하세요.</p>
        ) : null}
        {form.channel_bindings.map((binding, index) => (
          <div className="connector-binding-row" key={`binding-${index}`}>
            <input
              type="text"
              placeholder="guild id"
              value={binding.guild_id}
              onChange={(event) => updateBinding(index, { guild_id: event.target.value })}
            />
            <input
              type="text"
              placeholder="channel id"
              value={binding.channel_id}
              onChange={(event) => updateBinding(index, { channel_id: event.target.value })}
            />
            <input
              type="text"
              placeholder="채널 이름 (선택)"
              value={binding.channel_name}
              onChange={(event) => updateBinding(index, { channel_name: event.target.value })}
            />
            <input
              type="text"
              placeholder="repo (owner/name, 선택)"
              value={binding.repo}
              onChange={(event) => updateBinding(index, { repo: event.target.value })}
            />
            <button type="button" className="danger" onClick={() => removeBinding(index)}>
              삭제
            </button>
          </div>
        ))}
      </div>
      <div className="switch-row">
        <button className="primary" type="submit" disabled={saving}>
          {saving ? '저장 중...' : 'Discord 설정 저장'}
        </button>
        {message ? <span className="status-pill success">{message}</span> : null}
        {errorMessage ? <span className="status-pill warn">{errorMessage}</span> : null}
      </div>
    </form>
  );
}

function McpHubPanel({
  tools,
  resources,
  prompts,
}: {
  tools: McpToolDescriptor[];
  resources: McpResourceDescriptor[];
  prompts: McpPromptDescriptor[];
}) {
  const [query, setQuery] = useState('');
  const normalizedQuery = query.trim().toLowerCase();
  const visibleTools = normalizedQuery
    ? tools.filter((tool) => `${tool.name} ${tool.description} ${tool.server}`.toLowerCase().includes(normalizedQuery))
    : tools;

  return (
    <div className="panel">
      <div className="sticky-panel-header">
        <p className="eyebrow">MCP-compatible hub</p>
        <h2>코딩 에이전트 계획서 작성 MCP Hub</h2>
        <p className="muted">
          HTTP-compatible API와 JSON-RPC/SSE skeleton을 함께 제공해 코딩 에이전트 계획서 작성 기능이 tools, resources, prompts를 표준
          형태로 조회합니다.
        </p>
        <div className="switch-row">
          <span className="status-pill">tools {tools.length}</span>
          <span className="status-pill">resources {resources.length}</span>
          <span className="status-pill">prompts {prompts.length}</span>
        </div>
        <div className="memory-form row-compact">
          <input
            value={query}
            placeholder="tool 이름, 설명, 서버 검색"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </div>
      <div className="compact-card-list bounded-list">
        {visibleTools.slice(0, 50).map((tool) => (
          <article className="log-card" key={tool.name}>
            <strong>{tool.name}</strong>
            <p>{tool.description}</p>
            <small>
              {tool.server || 'mcp'} · permission: {tool.required_permission}
            </small>
          </article>
        ))}
        {!visibleTools.length ? <p className="muted small">검색 조건에 맞는 tool이 없습니다.</p> : null}
      </div>
      <details className="advanced-panel">
        <summary>Resources preview</summary>
        <div className="bounded-preview">
          <pre>{JSON.stringify(resources.slice(0, 10), null, 2)}</pre>
        </div>
      </details>
      <details className="advanced-panel">
        <summary>Prompts preview</summary>
        <div className="bounded-preview">
          <pre>{JSON.stringify(prompts, null, 2)}</pre>
        </div>
      </details>
    </div>
  );
}

function McpAuditPanel({ auditRecords }: { auditRecords: McpAuditRecord[] }) {
  return (
    <div className="panel">
      <div className="sticky-panel-header">
        <p className="eyebrow">Recent tool audit</p>
        <h2>MCP 호출 감사</h2>
        <p className="muted">tool 호출, actor, guard finding을 별도 탭에서 확인해 Hub 탐색 화면이 길게 늘어나지 않게 했습니다.</p>
      </div>
      <div className="compact-card-list bounded-list">
        {auditRecords.map((record) => (
          <article className="log-card" key={record.id}>
            <strong>{record.tool_name}</strong>
            <p>
              {record.mcp_server} · actor {record.actor || 'unknown'}
            </p>
            <small>
              risk {record.risk_level}
              {record.guard_findings?.length ? ` · guard ${record.guard_findings.join(', ')}` : ''}
            </small>
          </article>
        ))}
        {!auditRecords.length ? <p className="muted small">아직 MCP tool audit 기록이 없습니다.</p> : null}
      </div>
    </div>
  );
}

function IntegrationPanel({ title, status }: { title: string; status: IntegrationStatus | null }) {
  return (
    <div className="panel">
      <p className="eyebrow">Platform connector</p>
      <h2>{title}</h2>
      <p className="muted">
        {status
          ? status.configured
            ? status.ok
              ? '연동 정보 조회 완료'
              : '연동 조회 중 일부 오류가 있습니다.'
            : status.reason
          : '조회 중...'}
      </p>
      <div className="log-list">
        {status?.items.map((item, index) => (
          <article className="log-card" key={`${title}-${index}`}>
            <strong>{String(item.repo || item.channel_name || item.name || item.guild_id || 'item')}</strong>
            <pre>{JSON.stringify(item, null, 2)}</pre>
          </article>
        ))}
      </div>
    </div>
  );
}
