import { useEffect, useState } from 'react';

import {
  deleteApiKey,
  fetchContextFirewallAudit,
  fetchContextFirewallPolicy,
  fetchApiKeys,
  fetchProviderModels,
  previewProviderModels,
  saveApiKey,
  sanitizeContextFirewall,
  type ApiKeyInfo,
  type ContextFirewallAuditRecord,
  type ContextFirewallDecision,
  type ProviderModelPayload,
} from '../api';
import LocalAgentAdminPanel from './admin/LocalAgentAdminPanel';
import LlmTaskRoutingPanel from './ai/LlmTaskRoutingPanel';

type AdminSettingsSection = 'api-keys' | 'local-agent' | 'task-routing' | 'context-firewall';

const adminSettingsSections: Array<{ id: AdminSettingsSection; label: string; description: string }> = [
  { id: 'api-keys', label: 'API 키', description: '외부 LLM provider와 모델 선택' },
  { id: 'local-agent', label: '로컬 에이전트', description: '로컬 모델과 기동 상태 관리' },
  { id: 'task-routing', label: '작업 라우팅', description: '업무별 local/API 배정' },
  { id: 'context-firewall', label: '반출 제어', description: '외부 LLM 검열과 감사 로그' },
];

export default function AdminSettingsPage() {
  const [activeSection, setActiveSection] = useState<AdminSettingsSection>('api-keys');
  const [providers, setProviders] = useState<ApiKeyInfo[]>([]);
  const [draft, setDraft] = useState({ provider: 'solar', api_key: '', model: '' });
  const [models, setModels] = useState<ProviderModelPayload | null>(null);
  const [modelSearch, setModelSearch] = useState('');
  const [message, setMessage] = useState('');
  const allModelOptions = models?.models.length ? models.models : [draft.model].filter(Boolean);
  const normalizedModelSearch = modelSearch.trim().toLowerCase();
  const filteredModelOptions = normalizedModelSearch
    ? allModelOptions.filter((model) => model.toLowerCase().includes(normalizedModelSearch))
    : allModelOptions;
  const modelOptions = draft.model && !filteredModelOptions.includes(draft.model)
    ? [draft.model, ...filteredModelOptions]
    : filteredModelOptions;

  async function refresh() {
    try {
      setProviders((await fetchApiKeys()).providers);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'API 키 목록 로드 실패');
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    async function loadModels() {
      try {
        const next = await fetchProviderModels(draft.provider);
        setModels(next);
        setDraft((current) => ({ ...current, model: current.model || next.models[0] || '' }));
      } catch (err) {
        setModels(null);
        setMessage(err instanceof Error ? err.message : '모델 목록 로드 실패');
      }
    }
    void loadModels();
  }, [draft.provider]);

  async function save() {
    try {
      const result = await saveApiKey(draft);
      setProviders(result.providers);
      setMessage(`${draft.provider} API 키를 암호화 저장소에 저장했습니다.`);
      setDraft((current) => ({ ...current, api_key: '' }));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'API 키 저장 실패');
    }
  }

  async function previewModels() {
    try {
      const next = await previewProviderModels(draft.provider, draft.api_key);
      setModels(next);
      setDraft((current) => ({ ...current, model: next.models[0] || current.model }));
      setMessage(
        next.source === 'live'
          ? '입력한 API 키로 채팅 가능한 모델 목록을 확인했습니다.'
          : `기본 추천 목록: ${next.reason}`,
      );
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '모델 목록 확인 실패');
    }
  }

  async function remove(provider: string) {
    const result = await deleteApiKey(provider);
    setProviders(result.providers);
    setMessage(`${provider} API 키를 삭제했습니다.`);
  }

  return (
    <section className="admin-settings-page">
      <div className="panel admin-section-nav-panel">
        <p className="eyebrow">Admin settings</p>
        <h2>API 키·로컬 에이전트</h2>
        <p className="muted">
          설정 화면을 한 번에 모두 펼치지 않고, 필요한 영역만 네비게이션으로 전환해서 봅니다.
        </p>
        <nav className="admin-section-nav" aria-label="관리 설정 섹션">
          {adminSettingsSections.map((section) => (
            <button
              key={section.id}
              type="button"
              className={activeSection === section.id ? 'active-tab' : 'secondary-button'}
              onClick={() => setActiveSection(section.id)}
            >
              <span>{section.label}</span>
              <small>{section.description}</small>
            </button>
          ))}
        </nav>
      </div>

      {activeSection === 'api-keys' ? (
        <section className="admin-api-grid">
          <div className="panel">
            <p className="eyebrow">Frontier API</p>
            <h2>API 키 설정</h2>
            <div className="memory-form">
              <label>
                Provider
                <select
                  value={draft.provider}
                  onChange={(event) => {
                    setModelSearch('');
                    setDraft({ provider: event.target.value, api_key: draft.api_key, model: '' });
                  }}
                >
                  <option value="solar">Upstage / Solar</option>
                  <option value="openai">OpenAI / GPT</option>
                  <option value="anthropic">Anthropic / Claude</option>
                  <option value="gemini">Google / Gemini</option>
                  <option value="together">Together AI</option>
                </select>
              </label>
              <label>
                API Key
                <input type="password" value={draft.api_key} onChange={(event) => setDraft({ ...draft, api_key: event.target.value })} />
              </label>
              <div className="model-select-panel">
                <div className="model-select-head">
                  <span className="model-select-label">Model 선택</span>
                  {draft.model ? <span className="model-selected-pill" title={draft.model}>{draft.model}</span> : null}
                </div>
                <input
                  type="search"
                  placeholder={
                    draft.provider === 'together'
                      ? 'Together 모델 검색: llama, qwen, mistral, gpt-oss...'
                      : '모델 ID 검색'
                  }
                  value={modelSearch}
                  onChange={(event) => setModelSearch(event.target.value)}
                />
                <div className="model-option-list">
                  {modelOptions.length === 0 ? (
                    <p className="muted small">먼저 아래 "모델 목록 확인"을 눌러 사용 가능한 모델을 불러오세요.</p>
                  ) : (
                    modelOptions.map((model) => (
                      <button
                        key={model}
                        type="button"
                        className={'model-option' + (draft.model === model ? ' selected' : '')}
                        title={model}
                        onClick={() => setDraft({ ...draft, model })}
                      >
                        {model}
                      </button>
                    ))
                  )}
                </div>
                <input
                  className="model-manual-input"
                  placeholder="목록에 없으면 모델 ID 직접 입력"
                  value={draft.model}
                  onChange={(event) => setDraft({ ...draft, model: event.target.value })}
                />
                {models ? (
                  <p className="muted small">
                    {models.source === 'live' ? '실시간 API에서 확인한 채팅 가능 모델' : '기본 추천 목록'}
                    {normalizedModelSearch ? ` · 검색 ${filteredModelOptions.length}/${allModelOptions.length}` : ''}
                    {models.reason ? ` · ${models.reason}` : ''}
                  </p>
                ) : null}
              </div>
              <div className="admin-action-row">
                <button className="secondary-button" type="button" onClick={() => void previewModels()}>
                  입력한 키로 모델 목록 확인
                </button>
                <button type="button" onClick={() => void save()}>암호화 저장</button>
              </div>
              {message ? <p className="muted">{message}</p> : null}
            </div>
          </div>
          <div className="panel">
            <p className="eyebrow">Configured</p>
            <h2>저장된 Provider</h2>
            <div className="log-list">
              {providers.map((provider) => (
                <article className="log-card" key={provider.provider}>
                  <strong>{provider.label || provider.provider}</strong>
                  <p>{provider.configured ? provider.masked_value : '미설정'} · {provider.model || 'model -'}</p>
                  <p className="muted">Base URL은 시스템 기본값 사용: {provider.base_url || '-'}</p>
                  <button className="secondary-button" type="button" onClick={() => void remove(provider.provider)}>삭제</button>
                </article>
              ))}
            </div>
          </div>
        </section>
      ) : null}

      {activeSection === 'local-agent' ? <LocalAgentAdminPanel /> : null}
      {activeSection === 'task-routing' ? <LlmTaskRoutingPanel /> : null}
      {activeSection === 'context-firewall' ? <ContextFirewallPanel /> : null}
    </section>
  );
}

function ContextFirewallPanel() {
  const [sample, setSample] = useState(
    'A고객 김민준 팀장 token abc.def.ghi postgres://admin:pass@10.0.3.2:5432/payments',
  );
  const [result, setResult] = useState<ContextFirewallDecision | null>(null);
  const [audit, setAudit] = useState<ContextFirewallAuditRecord[]>([]);
  const [policy, setPolicy] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState('');

  async function refresh() {
    try {
      const [nextPolicy, nextAudit] = await Promise.all([
        fetchContextFirewallPolicy(),
        fetchContextFirewallAudit().catch(() => ({ records: [], count: 0 })),
      ]);
      setPolicy(nextPolicy.policy);
      setAudit(nextAudit.records);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Context Firewall 로드 실패');
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function runRedactionTest() {
    try {
      const payload = await sanitizeContextFirewall({
        destination: 'frontier_llm',
        task_type: 'admin_redaction_test',
        content: sample,
      });
      setResult(payload.result);
      await refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Context Firewall 테스트 실패');
    }
  }

  return (
    <div className="panel">
      <p className="eyebrow">Context Firewall</p>
      <h2>로컬 검열 / 외부 LLM 반출 제어</h2>
      <p className="muted">
        외부 프론티어 LLM으로 나가기 전 secret, PII, 사내 경로 정책, prompt injection을 검사하고 감사 로그를 남깁니다.
      </p>
      <div className="memory-form">
        <label>
          Redaction 테스트 입력
          <textarea value={sample} onChange={(event) => setSample(event.target.value)} />
        </label>
        <button type="button" onClick={() => void runRedactionTest()}>Context Firewall 테스트</button>
        {message ? <p className="muted">{message}</p> : null}
      </div>
      {result ? (
        <div className="log-card">
          <strong>{result.decision} · {result.highest_sensitivity}</strong>
          <p>removed: {JSON.stringify(result.removed_counts)}</p>
          <pre>{JSON.stringify(result.sanitized, null, 2)}</pre>
        </div>
      ) : null}
      <details>
        <summary>Effective Policy</summary>
        <pre>{JSON.stringify(policy, null, 2)}</pre>
      </details>
      <details open>
        <summary>Recent Context Firewall Audit</summary>
        <div className="log-list">
          {audit.slice(0, 8).map((record) => (
            <article className="log-card" key={record.id}>
              <strong>{record.decision} · {record.highest_sensitivity}</strong>
              <p>{record.destination} · {record.task_type}</p>
              <small>{record.detectors_triggered.join(', ') || 'detectors -'} · {record.redacted_context_hash}</small>
            </article>
          ))}
          {!audit.length ? <p className="muted small">아직 Context Firewall audit 기록이 없습니다.</p> : null}
        </div>
      </details>
    </div>
  );
}
