import { ChangeEvent, useEffect, useMemo, useState } from 'react';

import {
  analyzeInitialOfficeSetup,
  applyInitialOfficeSetup,
  fetchLlmRuntime,
  previewProviderModels,
  saveApiKey,
  saveLlmRuntime,
  searchHuggingFaceModels,
  setupAdmin,
  uploadDocument,
  type AiJobStatus,
  type AuthUser,
  type CompanyProfile,
  type HuggingFaceModelItem,
  type InitialOfficeSetupResult,
  type LlmProviderName,
  type PatchNoteRecommendationItem,
  type ProviderModelPayload,
  type UploadRecord,
} from '../../api';
import { setSessionToken } from '../../auth';
import AiJobStatusBar from '../common/AiJobStatusBar';
import { SETUP_DRAFT_KEY } from './setupDraft';

type Props = {
  onAuthenticated: (user: AuthUser) => void;
  initialUser?: AuthUser | null;
};

type Step = 'admin' | 'llm' | 'profile' | 'files' | 'analyze' | 'review';
type LlmChoice = 'local' | 'api';
type ReviewSection = 'memory' | 'agents' | 'templates' | 'workflows' | 'security' | 'integrations' | 'routes';

const recommendedLocalModels = [
  {
    vendor: 'Qwen',
    name: 'Qwen3-4B',
    model: 'Qwen/Qwen3-4B',
    strength: '가벼운 기본 로컬 에이전트 후보',
  },
  {
    vendor: 'Qwen',
    name: 'Qwen3-8B',
    model: 'Qwen/Qwen3-8B',
    strength: '업무 문서/추론 품질을 높인 Qwen 후보',
  },
  {
    vendor: 'Qwen',
    name: 'Qwen2.5-7B-Instruct',
    model: 'Qwen/Qwen2.5-7B-Instruct',
    strength: '검증된 instruct 텍스트 모델',
  },
  {
    vendor: 'LG',
    name: 'EXAONE 텍스트',
    model: 'LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct',
    strength: '국내 기업 모델 후보, 멀티모달 제외 텍스트 중심',
  },
  {
    vendor: '업스테이지',
    name: 'Solar 텍스트',
    model: 'upstage/SOLAR-10.7B-Instruct-v1.0',
    strength: '한국어 업무/문서 자동화 실험 후보',
  },
];

const recommendedSolarModels = [
  {
    name: 'Solar Open 2',
    model: 'solar-open2',
    strength: '한국어 오피스워크에 최적화된 Upstage 오픈 모델 (기본 권장)',
  },
  {
    name: 'Solar Pro 2',
    model: 'solar-pro2',
    strength: '고품질 문서 생성/분석용 상위 모델',
  },
  {
    name: 'Solar Mini',
    model: 'solar-mini',
    strength: '빠른 응답이 필요한 요약/분류 작업 후보',
  },
];

const recommendedTogetherModels = [
  {
    name: 'Llama 3.1 8B Turbo',
    model: 'meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo',
    strength: '빠른 응답과 비용 효율이 좋은 기본 업무 자동화 후보',
  },
  {
    name: 'GPT OSS 20B',
    model: 'openai/gpt-oss-20b',
    strength: '오픈 모델 기반 문서 생성/요약 후보',
  },
  {
    name: 'Mixtral 8x7B Instruct',
    model: 'mistralai/Mixtral-8x7B-Instruct-v0.1',
    strength: '긴 문서와 범용 지시 처리 실험 후보',
  },
];

type SetupDraft = {
  step: Step;
  admin: { user_id: string; display_name: string; title: string };
  llmChoice: LlmChoice;
  provider: LlmProviderName;
  model: string;
  localModel: string;
  localModelQuery: string;
  adapterModel: string;
  localModelUploads: UploadRecord[];
  selectedUploadPath: string;
  companyProfile: CompanyProfile;
  uploads: UploadRecord[];
  message: string;
  apiRiskAccepted: boolean;
};

const defaultCompanyProfile: CompanyProfile = {
    organization_size: 'startup',
    industries: ['it_saas'],
    departments: ['product_dev_it', 'cs'],
    primary_goals: ['meeting_notes', 'action_items', 'weekly_patch_notes', 'release_notes', 'integrated_search'],
    data_sensitivity: ['general'],
    deployment_preference: 'local_recommended',
    company_name: '',
    office_project: '',
    work_summary: '',
    current_tools: '',
    recurring_workflows: '',
    change_management_needs: '',
    automation_priorities: '',
};

function mergeCompanyProfile(draft?: Partial<CompanyProfile>): CompanyProfile {
  return { ...defaultCompanyProfile, ...(draft || {}) };
}

function loadSetupDraft(): SetupDraft | null {
  try {
    const raw = window.localStorage.getItem(SETUP_DRAFT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<SetupDraft>;
    if (!parsed.step) return null;
    return {
      step: parsed.step,
      admin: parsed.admin || { user_id: '', display_name: '', title: '시스템 관리자' },
      llmChoice: parsed.llmChoice || 'local',
      provider: parsed.provider || 'solar',
      model: parsed.model || '',
      localModel: parsed.localModel || 'Qwen/Qwen3-4B',
      localModelQuery: parsed.localModelQuery || 'Qwen',
      adapterModel: parsed.adapterModel || '',
      localModelUploads: parsed.localModelUploads || [],
      selectedUploadPath: parsed.selectedUploadPath || '',
      companyProfile: mergeCompanyProfile(parsed.companyProfile),
      uploads: parsed.uploads || [],
      message: parsed.message || '',
      apiRiskAccepted: Boolean(parsed.apiRiskAccepted),
    };
  } catch {
    return null;
  }
}

function saveSetupDraft(draft: SetupDraft) {
  window.localStorage.setItem(SETUP_DRAFT_KEY, JSON.stringify(draft));
}

function clearSetupDraft() {
  window.localStorage.removeItem(SETUP_DRAFT_KEY);
}

export default function InitialOfficeSetupWizard({ onAuthenticated, initialUser = null }: Props) {
  const savedDraft = useMemo(() => loadSetupDraft(), []);
  const [step, setStep] = useState<Step>(savedDraft?.step || (initialUser ? 'llm' : 'admin'));
  const [admin, setAdmin] = useState({ ...(savedDraft?.admin || { user_id: '', display_name: '', title: '시스템 관리자' }), password: '' });
  const [sessionUser, setSessionUser] = useState<AuthUser | null>(initialUser);
  const [llmChoice, setLlmChoice] = useState<LlmChoice>(savedDraft?.llmChoice || 'local');
  const [provider, setProvider] = useState<LlmProviderName>(savedDraft?.provider || 'solar');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState(savedDraft?.model || '');
  const [models, setModels] = useState<ProviderModelPayload | null>(null);
  const [modelSearch, setModelSearch] = useState('');
  const allModelOptions = models?.models.length ? models.models : [model].filter(Boolean);
  const normalizedModelSearch = modelSearch.trim().toLowerCase();
  const filteredModelOptions = normalizedModelSearch
    ? allModelOptions.filter((option) => option.toLowerCase().includes(normalizedModelSearch))
    : allModelOptions;
  const modelOptions = model && !filteredModelOptions.includes(model)
    ? [model, ...filteredModelOptions]
    : filteredModelOptions;
  const [localModel, setLocalModel] = useState(savedDraft?.localModel || 'Qwen/Qwen3-4B');
  const [localModelQuery, setLocalModelQuery] = useState(savedDraft?.localModelQuery || 'Qwen');
  const [hfModels, setHfModels] = useState<HuggingFaceModelItem[]>([]);
  const [adapterModel, setAdapterModel] = useState(savedDraft?.adapterModel || '');
  const [localModelUploads, setLocalModelUploads] = useState<UploadRecord[]>(savedDraft?.localModelUploads || []);
  const [selectedUploadPath, setSelectedUploadPath] = useState(savedDraft?.selectedUploadPath || '');
  const [companyProfile, setCompanyProfile] = useState<CompanyProfile>(
    mergeCompanyProfile(savedDraft?.companyProfile),
  );
  const [uploads, setUploads] = useState<UploadRecord[]>(savedDraft?.uploads || []);
  const [message, setMessage] = useState(savedDraft?.message || '');
  const [result, setResult] = useState<InitialOfficeSetupResult | null>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [aiJob, setAiJob] = useState<AiJobStatus | null>(null);
  const [apiRiskAccepted, setApiRiskAccepted] = useState(savedDraft?.apiRiskAccepted || false);
  const [applySections, setApplySections] = useState<Record<ReviewSection, boolean>>({
    memory: true,
    agents: true,
    templates: true,
    workflows: true,
    security: true,
    integrations: true,
    routes: true,
  });

  useEffect(() => {
    saveSetupDraft({
      step,
      admin: { user_id: admin.user_id, display_name: admin.display_name, title: admin.title },
      llmChoice,
      provider,
      model,
      localModel,
      localModelQuery,
      adapterModel,
      localModelUploads,
      selectedUploadPath,
      companyProfile,
      uploads,
      message,
      apiRiskAccepted,
    });
  }, [
    adapterModel,
    admin.display_name,
    admin.title,
    admin.user_id,
    apiRiskAccepted,
    companyProfile,
    llmChoice,
    localModel,
    localModelQuery,
    localModelUploads,
    message,
    model,
    provider,
    selectedUploadPath,
    step,
    uploads,
  ]);

  useEffect(() => {
    async function loadFallbackModels() {
      try {
        const payload = await previewProviderModels(provider, '');
        setModels(payload);
        setModel((current) => (current && payload.models.includes(current) ? current : payload.models[0] || ''));
      } catch {
        setModels(null);
      }
    }
    if (llmChoice === 'api') {
      void loadFallbackModels();
    }
  }, [llmChoice, provider]);

  async function createAdmin() {
    setBusy(true);
    setNotice('');
    try {
      const session = await setupAdmin(admin);
      setSessionToken(session.token);
      setSessionUser(session.user);
      setStep('llm');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '관리자 생성 실패');
    } finally {
      setBusy(false);
    }
  }

  async function configureLlm() {
    setBusy(true);
    setNotice('');
    try {
      const runtime = await fetchLlmRuntime();
      if (llmChoice === 'api') {
        if (!apiRiskAccepted) {
          setNotice('API 모델을 사용하려면 민감정보 외부 전송 가능성 경고를 확인해야 합니다.');
          return;
        }
        await saveApiKey({ provider, api_key: apiKey, model });
        await saveLlmRuntime({
          ...runtime,
          local_enabled: runtime.local_enabled,
          api_enabled: true,
          default_route: 'api',
          default_provider: provider,
          task_routes: {
            ...(runtime.task_routes || {}),
            memory_summary: { route: 'api', provider, model },
            agent_planning: { route: 'api', provider, model },
            document_generation: { route: 'api', provider, model },
            hiring: { route: 'api', provider, model },
            handover: { route: 'api', provider, model },
            chat: { route: 'api', provider, model },
          },
        });
      } else {
        const selectedLocalModel = (selectedUploadPath || adapterModel || localModel).trim() || 'Qwen/Qwen3-4B';
        await saveLlmRuntime({
          ...runtime,
          local_model: selectedLocalModel,
          local_enabled: true,
          api_enabled: runtime.api_enabled,
          default_route: 'local',
          default_provider: 'vllm',
          task_routes: {
            ...(runtime.task_routes || {}),
            memory_summary: { route: 'local', provider: 'vllm', model: selectedLocalModel },
            agent_planning: { route: 'local', provider: 'vllm', model: selectedLocalModel },
            document_generation: { route: 'local', provider: 'vllm', model: selectedLocalModel },
            hiring: { route: 'local', provider: 'vllm', model: selectedLocalModel },
            handover: { route: 'local', provider: 'vllm', model: selectedLocalModel },
            chat: { route: 'local', provider: 'vllm', model: selectedLocalModel },
          },
        });
      }
      setStep('profile');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'LLM 설정 실패');
    } finally {
      setBusy(false);
    }
  }

  async function searchLocalModels() {
    setBusy(true);
    setNotice('');
    try {
      const payload = await searchHuggingFaceModels(localModelQuery);
      setHfModels(payload.models);
      if (payload.models[0]) {
        setLocalModel(payload.models[0].id);
        setSelectedUploadPath('');
      }
      setNotice(payload.models.length ? 'Hugging Face 로컬 모델 후보를 불러왔습니다.' : '검색 결과가 없습니다.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Hugging Face 모델 검색 실패');
    } finally {
      setBusy(false);
    }
  }

  async function uploadLocalModelFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setNotice('');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('work_title', '초기 로컬 에이전트 모델 설정');
      form.append('tags', 'initial_setup,local_model,lora,finetune');
      form.append('description', '초기 세팅에서 선택한 파인튜닝/LoRA 로컬 모델 파일');
      const saved = (await uploadDocument(form)).upload;
      setLocalModelUploads((current) => [saved, ...current]);
      setSelectedUploadPath(saved.path);
      setNotice(`업로드했습니다: ${saved.filename}. LLM 설정 저장 후 계속을 누르면 이 파일을 로컬 모델로 사용합니다.`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '파인튜닝/LoRA 업로드 실패');
    } finally {
      setBusy(false);
    }
  }

  async function loadModels() {
    try {
      const payload = await previewProviderModels(provider, apiKey);
      setModels(payload);
      setModel(payload.models[0] || model);
      setNotice(payload.source === 'live' ? '입력한 키로 채팅 가능한 모델 목록을 확인했습니다.' : payload.reason);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '모델 확인 실패');
    }
  }

  async function uploadFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    if (files.length === 0) return;
    setBusy(true);
    setNotice('');
    try {
      const saved: UploadRecord[] = [];
      for (const file of files) {
        const form = new FormData();
        form.append('file', file);
        form.append('work_title', '초기 오피스 세팅');
        form.append('tags', 'initial_setup');
        form.append('description', '첫 실행 오피스 세팅 파일');
        saved.push((await uploadDocument(form)).upload);
      }
      setUploads((current) => [...saved, ...current]);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '파일 업로드 실패');
    } finally {
      setBusy(false);
    }
  }

  async function analyze() {
    setBusy(true);
    setNotice('');
    setAiJob({
      job_id: 'local-initial-setup',
      task: 'initial_office_setup.analyze',
      status: 'queued',
      actor: '',
      input_summary: companyProfile.company_name || message,
      used_sources: uploads.map((upload) => upload.path),
      result_path: '',
      error: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    try {
      setAiJob((current) => current ? { ...current, status: 'running', updated_at: new Date().toISOString() } : current);
      const analyzed = await analyzeInitialOfficeSetup({
        message,
        upload_ids: uploads.map((upload) => upload.id),
        intent: 'initial_office_setup',
        company_profile: companyProfile,
      });
      setResult(analyzed);
      setAiJob(analyzed.ai_job ?? null);
      setStep('review');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'AI 초기 세팅 분석 실패');
      setAiJob((current) =>
        current
          ? {
              ...current,
              status: 'failed',
              error: err instanceof Error ? err.message : 'AI 초기 세팅 분석 실패',
              updated_at: new Date().toISOString(),
            }
          : current,
      );
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!result || !sessionUser) return;
    setBusy(true);
    setNotice('');
    try {
      await applyInitialOfficeSetup(approvedResult(result, applySections));
      clearSetupDraft();
      onAuthenticated(sessionUser);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '초기 세팅 적용 실패');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-layout setup-layout">
      <section className="panel setup-wizard">
        <img className="auth-logo" src="/negotium-logo.png" alt="Negotium" />
        <p className="eyebrow">First-run office setup</p>
        <h1>네고티움 초기 오피스 세팅</h1>
        <StepBar step={step} />
        {step === 'admin' ? (
          <div className="memory-form">
            <input placeholder="관리자 ID" value={admin.user_id} onChange={(e) => setAdmin({ ...admin, user_id: e.target.value })} />
            <input placeholder="표시 이름" value={admin.display_name} onChange={(e) => setAdmin({ ...admin, display_name: e.target.value })} />
            <input placeholder="직함" value={admin.title} onChange={(e) => setAdmin({ ...admin, title: e.target.value })} />
            <input type="password" placeholder="비밀번호" value={admin.password} onChange={(e) => setAdmin({ ...admin, password: e.target.value })} />
            <button type="button" disabled={busy} onClick={() => void createAdmin()}>관리자 생성 후 계속</button>
          </div>
        ) : null}

        {step === 'llm' ? (
          <div className="memory-form">
            <div className="local-llm-status">
              <div>
                <strong>민감정보 보호 기본 권장: 로컬 에이전트 서버</strong>
                <p className="muted">인사 정보, 고객 정보, 계약서, 내부 운영 문서는 사내 서버/GPU에서 처리하는 로컬 에이전트를 권장합니다.</p>
              </div>
              <span className="status-pill">recommended</span>
            </div>
            <label className="checkbox-inline">
              <input type="radio" checked={llmChoice === 'local'} onChange={() => setLlmChoice('local')} />
              로컬 에이전트 사용
            </label>
            <label className="checkbox-inline">
              <input type="radio" checked={llmChoice === 'api'} onChange={() => setLlmChoice('api')} />
              API 모델 사용
            </label>
            {llmChoice === 'api' ? (
              <>
                <select
                  value={provider}
                  onChange={(e) => {
                    setProvider(e.target.value as LlmProviderName);
                    setModels(null);
                    setModel('');
                    setModelSearch('');
                  }}
                >
                  <option value="solar">Upstage / Solar</option>
                  <option value="openai">OpenAI / GPT</option>
                  <option value="anthropic">Anthropic / Claude</option>
                  <option value="gemini">Google / Gemini</option>
                  <option value="together">Together AI</option>
                </select>
                {provider === 'solar' ? (
                  <div className="local-llm-status">
                    <div>
                      <strong>Upstage Solar API</strong>
                      <p className="muted">
                        Solar는 OpenAI-compatible API로 호출됩니다. console.upstage.ai에서 발급한 API key를
                        넣고 모델 확인을 누르면 사용 가능한 모델 목록을 가져옵니다.
                      </p>
                    </div>
                    <span className="status-pill">api</span>
                  </div>
                ) : null}
                {provider === 'together' ? (
                  <div className="local-llm-status">
                    <div>
                      <strong>Together API</strong>
                      <p className="muted">
                        Together는 OpenAI-compatible API로 호출됩니다. API key를 넣고 모델 확인을 누르면 사용 가능한
                        hosted/open model 목록을 가져옵니다.
                      </p>
                    </div>
                    <span className="status-pill">api</span>
                  </div>
                ) : null}
                <input type="password" placeholder="API Key" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
                {provider === 'solar' ? (
                  <div className="recommended-model-grid">
                    {recommendedSolarModels.map((item) => (
                      <article className={model === item.model ? 'model-card model-card-selected' : 'model-card'} key={item.model}>
                        <small>Upstage</small>
                        <strong>{item.name}</strong>
                        <p>{item.strength}</p>
                        <code>{item.model}</code>
                        <button className="secondary-button" type="button" onClick={() => setModel(item.model)}>
                          선택
                        </button>
                      </article>
                    ))}
                  </div>
                ) : null}
                {provider === 'together' ? (
                  <div className="recommended-model-grid">
                    {recommendedTogetherModels.map((item) => (
                      <article className={model === item.model ? 'model-card model-card-selected' : 'model-card'} key={item.model}>
                        <small>Together AI</small>
                        <strong>{item.name}</strong>
                        <p>{item.strength}</p>
                        <code>{item.model}</code>
                        <button className="secondary-button" type="button" onClick={() => setModel(item.model)}>
                          선택
                        </button>
                      </article>
                    ))}
                  </div>
                ) : null}
                <label>
                  Model 선택
                  <div className="model-select-panel">
                    <input
                      type="search"
                      placeholder={provider === 'together' ? 'Together 모델 검색: llama, qwen, mistral...' : '모델 ID 검색'}
                      value={modelSearch}
                      onChange={(e) => setModelSearch(e.target.value)}
                    />
                    <select value={model} onChange={(e) => setModel(e.target.value)}>
                      {modelOptions.length ? null : <option value="">먼저 모델 목록을 확인하세요</option>}
                      {modelOptions.map((option) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </select>
                    <input
                      list="initial-setup-model-options"
                      placeholder="목록에 없으면 모델 ID 직접 입력"
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                    />
                    <datalist id="initial-setup-model-options">
                      {allModelOptions.map((option) => (
                        <option key={option} value={option} />
                      ))}
                    </datalist>
                  </div>
                </label>
                <button className="secondary-button" type="button" onClick={() => void loadModels()}>입력한 키로 모델 확인</button>
                {models ? (
                  <p className="muted">
                    모델 목록: {models.source === 'live' ? '실시간 API에서 확인한 채팅 가능 모델' : '기본 추천 목록'}
                    {normalizedModelSearch ? ` · 검색 결과 ${filteredModelOptions.length}/${allModelOptions.length}` : ''}
                    {models.reason ? ` · ${models.reason}` : ''}
                  </p>
                ) : null}
                <label className="checkbox-inline">
                  <input type="checkbox" checked={apiRiskAccepted} onChange={(e) => setApiRiskAccepted(e.target.checked)} />
                  민감정보가 포함된 파일은 외부 API로 전송될 수 있음을 확인했습니다.
                </label>
              </>
            ) : null}
            {llmChoice === 'local' ? (
              <div className="panel-subsection">
                <h3>로컬 에이전트 기본 모델</h3>
                <p className="muted">
                  멀티모달 없이 텍스트 기반 모델부터 시작합니다. Qwen, LG EXAONE, Solar 후보를 고르거나 Hugging Face repo ID/LoRA 파일을 지정하세요.
                </p>
                <div className="recommended-model-grid">
                  {recommendedLocalModels.map((item) => (
                    <article className={localModel === item.model ? 'model-card model-card-selected' : 'model-card'} key={item.model}>
                      <small>{item.vendor}</small>
                      <strong>{item.name}</strong>
                      <p>{item.strength}</p>
                      <code>{item.model}</code>
                      <button className="secondary-button" type="button" onClick={() => {
                        setLocalModel(item.model);
                        setSelectedUploadPath('');
                      }}>
                        선택
                      </button>
                    </article>
                  ))}
                </div>
                <label>
                  Hugging Face 검색어
                  <div className="inline-input-row">
                    <input value={localModelQuery} onChange={(e) => setLocalModelQuery(e.target.value)} placeholder="예: Qwen, EXAONE, Solar, Korean LLM" />
                    <button className="secondary-button" type="button" disabled={busy} onClick={() => void searchLocalModels()}>
                      검색
                    </button>
                  </div>
                </label>
                <label>
                  로컬 Base 모델
                  <select value={localModel} onChange={(e) => {
                    setLocalModel(e.target.value);
                    setSelectedUploadPath('');
                  }}>
                    {[localModel, ...recommendedLocalModels.map((item) => item.model), ...hfModels.map((item) => item.id)]
                      .filter(Boolean)
                      .filter((item, index, arr) => arr.indexOf(item) === index)
                      .map((item) => (
                        <option key={item} value={item}>{item}</option>
                      ))}
                  </select>
                </label>
                <label>
                  파인튜닝 / LoRA Hugging Face repo ID
                  <input value={adapterModel} onChange={(e) => setAdapterModel(e.target.value)} placeholder="예: organization/qwen3-office-lora" />
                </label>
                <label>
                  파인튜닝 / LoRA 파일 업로드
                  <input type="file" accept=".safetensors,.bin,.pt,.pth,.gguf,.zip,.tar,.json" onChange={(e) => void uploadLocalModelFile(e)} />
                </label>
                {localModelUploads.length ? (
                  <label>
                    업로드한 모델/어댑터 선택
                    <select value={selectedUploadPath} onChange={(e) => setSelectedUploadPath(e.target.value)}>
                      <option value="">업로드 파일을 사용하지 않음</option>
                      {localModelUploads.map((upload) => (
                        <option key={upload.id} value={upload.path}>
                          {upload.filename} · {upload.path}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                {hfModels.length ? (
                  <div className="log-list">
                    {hfModels.slice(0, 5).map((item) => (
                      <article className="log-card" key={item.id}>
                        <strong>{item.id}</strong>
                        <small>downloads {item.downloads.toLocaleString()} · likes {item.likes.toLocaleString()}</small>
                        <button className="secondary-button" type="button" onClick={() => {
                          setLocalModel(item.id);
                          setSelectedUploadPath('');
                        }}>
                          이 모델 선택
                        </button>
                      </article>
                    ))}
                  </div>
                ) : null}
                <p className="muted">
                  저장 대상: {(selectedUploadPath || adapterModel || localModel).trim() || 'Qwen/Qwen3-4B'}
                </p>
              </div>
            ) : null}
            <button type="button" disabled={busy} onClick={() => void configureLlm()}>LLM 설정 저장 후 계속</button>
          </div>
        ) : null}

        {step === 'profile' ? (
          <ProfileStep
            companyProfile={companyProfile}
            setCompanyProfile={setCompanyProfile}
            onContinue={() => setStep('files')}
          />
        ) : null}

        {step === 'files' ? (
          <div className="memory-form">
            <p className="muted">회사 인적 사항, 조직도, 운영 규정 파일을 올리면 AI가 초기 메모리와 사용자/직함 초안을 만듭니다.</p>
            <input type="file" multiple accept=".csv,.tsv,.xlsx,.txt,.md" onChange={(e) => void uploadFiles(e)} />
            <div className="log-list">
              {uploads.map((upload) => (
                <article className="log-card" key={upload.id}>
                  <strong>{upload.filename}</strong>
                  <small>{upload.path}</small>
                </article>
              ))}
            </div>
            <button type="button" onClick={() => setStep('analyze')}>파일 선택 완료</button>
          </div>
        ) : null}

        {step === 'analyze' ? (
          <div className="memory-form">
            <textarea
              value={message}
              placeholder="예: 이 엑셀 파일의 직함을 보고 부서/역할/초기 업무 메모리를 정리해줘"
              onChange={(e) => setMessage(e.target.value)}
            />
            <button type="button" disabled={busy} onClick={() => void analyze()}>AI로 초기 오피스 세팅 분석</button>
          </div>
        ) : null}

        {step === 'review' ? (
          <div className="memory-form">
            <p className="muted">AI가 만든 초안을 검토한 뒤 적용하세요. 직원 로그인 계정은 자동 생성하지 않습니다.</p>
            {result ? (
              <>
                <ReviewToggle id="memory" label="운영/작업 메모리 적용" checked={applySections.memory} onChange={(id, checked) => setApplySections({ ...applySections, [id]: checked })} />
                <article className="log-card">
                  <strong>{result.recommended_package}</strong>
                  <small>{JSON.stringify(result.workspace_profile)}</small>
                </article>
                <ReviewToggle id="agents" label="추천 에이전트 팩 적용" checked={applySections.agents} onChange={(id, checked) => setApplySections({ ...applySections, [id]: checked })} />
                <RecommendationList items={result.agent_packs} />
                <ReviewToggle id="templates" label="추천 템플릿 적용" checked={applySections.templates} onChange={(id, checked) => setApplySections({ ...applySections, [id]: checked })} />
                <RecommendationList items={result.templates} />
                <ReviewToggle id="workflows" label="추천 워크플로우 적용" checked={applySections.workflows} onChange={(id, checked) => setApplySections({ ...applySections, [id]: checked })} />
                <RecommendationList items={result.workflows} />
                <ReviewToggle id="security" label="보안 기본값 적용" checked={applySections.security} onChange={(id, checked) => setApplySections({ ...applySections, [id]: checked })} />
                <RecommendationList items={result.security_defaults} />
                <ReviewToggle id="integrations" label="연동 우선순위 적용" checked={applySections.integrations} onChange={(id, checked) => setApplySections({ ...applySections, [id]: checked })} />
                <RecommendationList items={result.integration_priorities} />
                <ReviewToggle id="routes" label="LLM 라우팅 추천 적용" checked={applySections.routes} onChange={(id, checked) => setApplySections({ ...applySections, [id]: checked })} />
                <pre>{JSON.stringify(result.llm_task_routes, null, 2)}</pre>
                <h3>첫 14일 실행안</h3>
                <ul>{result.first_14_days.map((item) => <li key={item}>{item}</li>)}</ul>
                <h3>사람 검토 필수</h3>
                <ul>{result.human_review_required.map((item) => <li key={item}>{item}</li>)}</ul>
              </>
            ) : null}
            <button type="button" disabled={busy} onClick={() => void apply()}>검토 완료 · 초기 세팅 적용</button>
          </div>
        ) : null}

        {notice ? <p className="alert">{notice}</p> : null}
        <AiJobStatusBar job={aiJob} />
      </section>
    </main>
  );
}

type DepartmentId =
  | 'executive'
  | 'hr'
  | 'finance'
  | 'sales'
  | 'marketing'
  | 'cs'
  | 'product_dev_it'
  | 'legal'
  | 'ops_procurement';

type GoalId =
  | 'meeting_notes'
  | 'action_items'
  | 'weekly_patch_notes'
  | 'release_notes'
  | 'integrated_search'
  | 'customer_memory'
  | 'proposal_docs';

const DEPARTMENT_PACK_MAP: Record<DepartmentId, { name: string; description: string }> = {
  executive: { name: 'CEO 브리핑 에이전트', description: '전사 패치 노트, KPI 이슈, 의사결정 로그를 요약합니다.' },
  hr: { name: 'HR 에이전트', description: '채용공고, 면접 질문, 온보딩 체크리스트, 인사 규정 Q&A를 지원합니다.' },
  finance: { name: '재무/회계 에이전트', description: '월말 보고, 비용 정리, 예산 초과 알림을 제안합니다.' },
  sales: { name: '영업 에이전트', description: '미팅 요약, 제안서 초안, 파이프라인 요약을 지원합니다.' },
  marketing: { name: '마케팅 에이전트', description: '캠페인 기획, 콘텐츠 작성, 리뷰 분석을 지원합니다.' },
  cs: { name: 'CS 에이전트', description: '문의 분류, 답변 초안, FAQ 업데이트를 지원합니다.' },
  product_dev_it: { name: '제품/개발/IT 에이전트', description: 'PRD, 릴리즈 노트, 버그 리포트, 포스트모템을 만듭니다.' },
  legal: { name: '법무 보조 에이전트', description: '계약 요약, 표준 조항 비교, 규정 Q&A 보조 (사람 검토 전제).' },
  ops_procurement: { name: '운영/구매 에이전트', description: '구매요청, 공급업체 비교, 운영 리포트를 지원합니다.' },
};

const GOAL_WORKFLOW_MAP: Record<GoalId, { name: string; description: string }> = {
  meeting_notes: { name: '회의 자동 기록', description: '결정사항/반대 의견/담당자/기한 추출' },
  action_items: { name: '액션아이템 자동 생성', description: '회의·문서·메시지에서 할 일/마감 추출' },
  weekly_patch_notes: { name: '팀 패치 노트', description: '완료, 이슈, 결정, 다음주 계획 자동 정리' },
  release_notes: { name: '릴리즈 노트 자동화', description: 'GitHub/Jira 변경사항으로 노트 생성' },
  integrated_search: { name: '권한 기반 통합 검색', description: '문서/메시지/회의/채팅을 권한 인식으로 검색' },
  customer_memory: { name: '고객/프로젝트 메모리', description: '고객별 히스토리·결정·담당자 맥락 기억' },
  proposal_docs: { name: '제안서/보고서 자동화', description: '회의록·요구사항 기반 산출물 초안' },
};

const ORGANIZATION_OPTIONS: Array<[string, string]> = [
  ['solo', '1인/프리랜서 — Patch Note Solo'],
  ['startup', '스타트업/소규모 팀 — Patch Note Team'],
  ['smb', '중소기업 — Patch Note Business'],
  ['mid_market', '중견기업 — Patch Note Business'],
  ['enterprise_public', '대기업/공공기관 — Patch Note Enterprise'],
];

function ProfileStep({
  companyProfile,
  setCompanyProfile,
  onContinue,
}: {
  companyProfile: CompanyProfile;
  setCompanyProfile: (next: CompanyProfile) => void;
  onContinue: () => void;
}) {
  const update = <K extends keyof CompanyProfile>(key: K, value: CompanyProfile[K]) => {
    setCompanyProfile({ ...companyProfile, [key]: value });
  };

  const sensitiveSelected = companyProfile.data_sensitivity.some((value) =>
    ['customer_info', 'hr_info', 'finance_info', 'medical_info', 'trade_secret'].includes(value),
  );
  const recommendedPackage = ORGANIZATION_OPTIONS.find(
    ([id]) => id === companyProfile.organization_size,
  )?.[1] ?? 'Patch Note Team';
  const previewAgents = (companyProfile.departments as DepartmentId[])
    .filter((id) => DEPARTMENT_PACK_MAP[id])
    .slice(0, 6)
    .map((id) => ({ id, ...DEPARTMENT_PACK_MAP[id] }));
  const previewWorkflows = (companyProfile.primary_goals as GoalId[])
    .filter((id) => GOAL_WORKFLOW_MAP[id])
    .slice(0, 6)
    .map((id) => ({ id, ...GOAL_WORKFLOW_MAP[id] }));

  const canContinue = companyProfile.company_name.trim().length >= 1;

  return (
    <div className="setup-profile-grid">
      <div className="setup-profile-form">
        <fieldset className="setup-option-group">
          <legend>회사 정체성</legend>
          <p className="muted">AI가 운영 메모리·문서·공지를 만들 때 회사 이름과 진행 중인 오피스 프로젝트를 기준으로 잡습니다.</p>
          <label>
            회사 이름
            <input
              value={companyProfile.company_name}
              onChange={(event) => update('company_name', event.target.value)}
              placeholder="예: Negotium Lab Co., Ltd."
            />
          </label>
          <label>
            현재 오피스 프로젝트 / 도입 목적
            <input
              value={companyProfile.office_project}
              onChange={(event) => update('office_project', event.target.value)}
              placeholder="예: 분기 회의/주간 보고 자동화 + 릴리즈 노트 정착"
            />
          </label>
          <label>
            우리 회사 업무 요약
            <textarea
              rows={3}
              value={companyProfile.work_summary}
              onChange={(event) => update('work_summary', event.target.value)}
              placeholder="예: B2B SaaS, 영업/CS/제품팀 위주, 매주 릴리즈 + 월간 KPI 리뷰"
            />
          </label>
        </fieldset>

        <fieldset className="setup-option-group">
          <legend>운영 환경</legend>
          <label>
            조직 규모 (추천 패키지가 자동 결정됩니다)
            <select
              value={companyProfile.organization_size}
              onChange={(event) => update('organization_size', event.target.value)}
            >
              {ORGANIZATION_OPTIONS.map(([id, label]) => (
                <option key={id} value={id}>{label}</option>
              ))}
            </select>
          </label>
          <label>
            배포 선호도
            <select
              value={companyProfile.deployment_preference}
              onChange={(event) => update('deployment_preference', event.target.value)}
            >
              <option value="local_recommended">민감정보 보호: 로컬 에이전트 권장</option>
              <option value="api_allowed">API 모델 사용 허용</option>
              <option value="private_required">프라이빗/온프레미스 필요</option>
            </select>
          </label>
          <OptionGroup
            title="데이터 민감도"
            values={companyProfile.data_sensitivity}
            options={[
              ['general', '일반 업무'],
              ['customer_info', '고객정보'],
              ['hr_info', '인사정보'],
              ['finance_info', '금융/재무정보'],
              ['medical_info', '의료정보'],
              ['trade_secret', '영업비밀'],
            ]}
            onChange={(values) => update('data_sensitivity', values)}
          />
        </fieldset>

        <fieldset className="setup-option-group">
          <legend>업무 맥락</legend>
          <p className="muted">아래 입력은 prompt에 그대로 들어가서, AI가 우리 회사에 맞는 운영 템플릿을 조립할 때 기준이 됩니다.</p>
          <label>
            반복적으로 일어나는 업무 / 회의
            <textarea
              rows={3}
              value={companyProfile.recurring_workflows}
              onChange={(event) => update('recurring_workflows', event.target.value)}
              placeholder="예: 매주 월요일 영업 미팅, 격주 제품 리뷰, 매월 KPI 회의, 매주 릴리즈"
            />
          </label>
          <label>
            지금 사용하는 도구 / 연동하고 싶은 시스템
            <textarea
              rows={2}
              value={companyProfile.current_tools}
              onChange={(event) => update('current_tools', event.target.value)}
              placeholder="예: Slack, Notion, Jira, GitHub, HubSpot, Google Drive"
            />
          </label>
          <label>
            변경사항 관리에서 가장 자주 놓치는 것
            <textarea
              rows={2}
              value={companyProfile.change_management_needs}
              onChange={(event) => update('change_management_needs', event.target.value)}
              placeholder="예: 결정 사항이 누구에게 전달됐는지 모름, 릴리즈 후 변경점이 영업/CS에 안 흘러감"
            />
          </label>
          <label>
            우선 자동화하고 싶은 업무 (Top 1~3)
            <textarea
              rows={2}
              value={companyProfile.automation_priorities}
              onChange={(event) => update('automation_priorities', event.target.value)}
              placeholder="예: 회의록 → 액션아이템, 주간 패치 노트, 릴리즈 노트, 고객별 미팅 요약"
            />
          </label>
        </fieldset>

        <OptionGroup
          title="업종"
          values={companyProfile.industries}
          options={[
            ['it_saas', 'IT/SaaS'],
            ['b2b_sales_cs', 'B2B 영업/CS'],
            ['professional_services', '전문서비스'],
            ['manufacturing', '제조'],
            ['construction', '건설'],
            ['ecommerce', '도소매/이커머스'],
            ['finance', '금융'],
            ['healthcare', '의료/복지'],
            ['public', '공공'],
            ['education', '교육'],
          ]}
          onChange={(values) => update('industries', values)}
        />
        <OptionGroup
          title="초기 타깃 부서"
          values={companyProfile.departments}
          options={[
            ['executive', '경영진'],
            ['hr', 'HR'],
            ['finance', '재무'],
            ['sales', '영업'],
            ['marketing', '마케팅'],
            ['cs', 'CS'],
            ['product_dev_it', '제품/개발/IT'],
            ['legal', '법무'],
            ['ops_procurement', '운영/구매'],
          ]}
          onChange={(values) => update('departments', values)}
        />
        <OptionGroup
          title="핵심 목적"
          values={companyProfile.primary_goals}
          options={[
            ['meeting_notes', 'AI 회의록'],
            ['action_items', '액션아이템 추출'],
            ['weekly_patch_notes', '팀 패치 노트'],
            ['release_notes', '릴리즈 노트 자동화'],
            ['integrated_search', '통합 검색'],
            ['customer_memory', '고객/프로젝트 메모리'],
            ['proposal_docs', '제안서/보고서'],
          ]}
          onChange={(values) => update('primary_goals', values)}
        />

        <div className="form-actions">
          <button type="button" disabled={!canContinue} onClick={onContinue}>
            회사 프로파일 저장 후 계속
          </button>
          {!canContinue ? <span className="muted">회사 이름을 입력하면 다음 단계로 넘어갑니다.</span> : null}
        </div>
      </div>

      <aside className="setup-profile-side">
        <article className="panel setup-side-card">
          <p className="eyebrow">AI가 이 입력으로 만드는 것</p>
          <h3>{recommendedPackage}</h3>
          <p className="muted">
            지금 입력한 회사 정체성·업무 맥락·민감도를 바탕으로, AI가 운영 메모리, 추천 에이전트 팩, 템플릿, 워크플로우, 보안 기본값,
            14일 실행안을 한 번에 조립해서 검토 단계에서 보여줍니다.
          </p>
          <ol className="setup-side-steps">
            <li>회사 정체성 → 운영 메모리 (`company_name`, `office_project`, `key_workflows`)</li>
            <li>업무 맥락 → 첫 14일 실행안과 추천 워크플로우</li>
            <li>부서/업종/목적 → 에이전트 팩 + 산업 템플릿</li>
            <li>민감도 → 보안 기본값과 LLM 라우팅 (로컬/외부)</li>
          </ol>
        </article>

        <article className="panel setup-side-card">
          <p className="eyebrow">선택한 부서 기준 추천 에이전트</p>
          {previewAgents.length === 0 ? (
            <p className="muted">초기 타깃 부서를 1개 이상 선택하세요.</p>
          ) : (
            <ul className="setup-side-list">
              {previewAgents.map((agent) => (
                <li key={agent.id}>
                  <strong>{agent.name}</strong>
                  <span>{agent.description}</span>
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="panel setup-side-card">
          <p className="eyebrow">핵심 목적 기준 운영 템플릿</p>
          {previewWorkflows.length === 0 ? (
            <p className="muted">핵심 목적을 1개 이상 선택하세요.</p>
          ) : (
            <ul className="setup-side-list">
              {previewWorkflows.map((workflow) => (
                <li key={workflow.id}>
                  <strong>{workflow.name}</strong>
                  <span>{workflow.description}</span>
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className={sensitiveSelected ? 'panel setup-side-card alert-card' : 'panel setup-side-card'}>
          <p className="eyebrow">신뢰 가능한 기본값</p>
          <ul className="setup-side-list">
            <li><strong>출처 표시</strong><span>모든 AI 답변에 근거 문서 링크 표시</span></li>
            <li><strong>권한 인식 검색</strong><span>사용자 권한 안에서만 RAG로 답변</span></li>
            <li><strong>감사 로그</strong><span>검색·생성·수정·삭제 기록 보존</span></li>
            <li><strong>고위험 업무 사람 검토</strong><span>채용/평가/법률/금융/의료 자동 판단 금지</span></li>
            {sensitiveSelected ? (
              <li>
                <strong>민감정보 감지</strong>
                <span>로컬 에이전트 우선, 외부 API 사용 시 사용자 동의 필요</span>
              </li>
            ) : null}
          </ul>
        </article>
      </aside>
    </div>
  );
}

function StepBar({ step }: { step: Step }) {
  const steps: Array<[Step, string]> = [
    ['admin', '관리자'],
    ['llm', 'LLM'],
    ['profile', '프로파일'],
    ['files', '파일'],
    ['analyze', 'AI 분석'],
    ['review', '적용'],
  ];
  const activeIndex = steps.findIndex(([id]) => id === step);
  return (
    <div className="setup-steps" aria-label="초기 설정 단계">
      {steps.map(([id, label], index) => (
        <span key={id} className={index <= activeIndex ? 'setup-step active' : 'setup-step'}>
          {label}
        </span>
      ))}
    </div>
  );
}

function OptionGroup({
  title,
  values,
  options,
  onChange,
}: {
  title: string;
  values: string[];
  options: Array<[string, string]>;
  onChange: (values: string[]) => void;
}) {
  return (
    <fieldset className="setup-option-group">
      <legend>{title}</legend>
      {options.map(([id, label]) => (
        <label className="checkbox-inline" key={id}>
          <input
            type="checkbox"
            checked={values.includes(id)}
            onChange={(event) => {
              const next = event.target.checked ? [...values, id] : values.filter((value) => value !== id);
              onChange(next.length ? next : [id]);
            }}
          />
          {label}
        </label>
      ))}
    </fieldset>
  );
}

function ReviewToggle({
  id,
  label,
  checked,
  onChange,
}: {
  id: ReviewSection;
  label: string;
  checked: boolean;
  onChange: (id: ReviewSection, checked: boolean) => void;
}) {
  return (
    <label className="checkbox-inline">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(id, event.target.checked)}
      />
      {label}
    </label>
  );
}

function RecommendationList({ items }: { items: PatchNoteRecommendationItem[] }) {
  if (!items.length) {
    return <p className="muted">추천 항목 없음</p>;
  }
  return (
    <div className="log-list">
      {items.map((item) => (
        <article className="log-card" key={item.id || item.name}>
          <strong>{item.name || item.id}</strong>
          <small>{item.description || item.reason || item.priority || ''}</small>
        </article>
      ))}
    </div>
  );
}

function approvedResult(result: InitialOfficeSetupResult, sections: Record<ReviewSection, boolean>): InitialOfficeSetupResult {
  return {
    ...result,
    operations_memory: sections.memory ? result.operations_memory : {},
    work_memory: sections.memory ? result.work_memory : {},
    agent_packs: sections.agents ? result.agent_packs : [],
    templates: sections.templates ? result.templates : [],
    workflows: sections.workflows ? result.workflows : [],
    security_defaults: sections.security ? result.security_defaults : [],
    integration_priorities: sections.integrations ? result.integration_priorities : [],
    llm_task_routes: sections.routes ? result.llm_task_routes : {},
  };
}
