import { ChangeEvent, useEffect, useMemo, useState } from 'react';

import {
  analyzeInitialOfficeSetup,
  applyInitialOfficeSetup,
  fetchLlmRuntime,
  previewOfficeScan,
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
  type OfficeScanReport,
  type OfficeScanRequest,
  type PatchNoteRecommendationItem,
  type ProviderModelPayload,
  type UploadRecord,
} from '../../api';
import { setSessionToken } from '../../auth';
import AiJobStatusBar from '../common/AiJobStatusBar';
import Button from '../common/Button';
import FormActions from '../common/FormActions';
import FolderBrowserModal from './FolderBrowserModal';
import { SETUP_DRAFT_KEY } from './setupDraft';

type Props = {
  onAuthenticated: (user: AuthUser) => void;
  initialUser?: AuthUser | null;
};

type Step = 'admin' | 'llm' | 'data' | 'analyze' | 'review';
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
  uploads: UploadRecord[];
  message: string;
  apiRiskAccepted: boolean;
  scanRoots: string[];
  scanExcludes: string[];
};

// Older drafts stored newline-separated strings and a 'profile'/'files' step.
function toPathArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === 'string') {
    return value
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
  }
  return [];
}

function migrateStep(step: string): Step {
  if (step === 'profile' || step === 'files') return 'data';
  if (step === 'admin' || step === 'llm' || step === 'data' || step === 'analyze' || step === 'review') {
    return step;
  }
  return 'admin';
}

// The wizard no longer asks the admin to describe the company — the AI infers
// everything from scanned documents. This neutral profile carries no hints.
const neutralCompanyProfile: CompanyProfile = {
    organization_size: 'smb',
    industries: [],
    departments: [],
    primary_goals: [],
    data_sensitivity: [],
    deployment_preference: 'local_recommended',
    company_name: '',
    office_project: '',
    work_summary: '',
    current_tools: '',
    recurring_workflows: '',
    change_management_needs: '',
    automation_priorities: '',
};

function loadSetupDraft(): SetupDraft | null {
  try {
    const raw = window.localStorage.getItem(SETUP_DRAFT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<SetupDraft> & { step?: string };
    if (!parsed.step) return null;
    return {
      step: migrateStep(parsed.step),
      admin: parsed.admin || { user_id: '', display_name: '', title: '시스템 관리자' },
      llmChoice: parsed.llmChoice || 'local',
      provider: parsed.provider || 'solar',
      model: parsed.model || '',
      localModel: parsed.localModel || 'Qwen/Qwen3-4B',
      localModelQuery: parsed.localModelQuery || 'Qwen',
      adapterModel: parsed.adapterModel || '',
      localModelUploads: parsed.localModelUploads || [],
      selectedUploadPath: parsed.selectedUploadPath || '',
      uploads: parsed.uploads || [],
      message: parsed.message || '',
      apiRiskAccepted: Boolean(parsed.apiRiskAccepted),
      scanRoots: toPathArray(parsed.scanRoots),
      scanExcludes: toPathArray(parsed.scanExcludes),
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
  const [uploads, setUploads] = useState<UploadRecord[]>(savedDraft?.uploads || []);
  const [message, setMessage] = useState(savedDraft?.message || '');
  const [scanRoots, setScanRoots] = useState<string[]>(savedDraft?.scanRoots || []);
  const [scanExcludes, setScanExcludes] = useState<string[]>(savedDraft?.scanExcludes || []);
  const [scanAllowCloud, setScanAllowCloud] = useState(false);
  const [scanReport, setScanReport] = useState<OfficeScanReport | null>(null);
  const [showFolderBrowser, setShowFolderBrowser] = useState(false);
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
      uploads,
      message,
      apiRiskAccepted,
      scanRoots,
      scanExcludes,
    });
  }, [
    adapterModel,
    admin.display_name,
    admin.title,
    admin.user_id,
    apiRiskAccepted,
    llmChoice,
    localModel,
    localModelQuery,
    localModelUploads,
    message,
    model,
    provider,
    scanExcludes,
    scanRoots,
    selectedUploadPath,
    step,
    uploads,
  ]);

  // Entering the data step with a cloud LLM already chosen (and its risk
  // warning accepted) counts as consent — don't ask twice.
  useEffect(() => {
    if (step === 'data' && llmChoice === 'api' && apiRiskAccepted) {
      setScanAllowCloud(true);
    }
  }, [step, llmChoice, apiRiskAccepted]);

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
      setStep('data');
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

  function buildScanRequest(): OfficeScanRequest | null {
    if (!scanRoots.length) return null;
    return {
      root_paths: scanRoots,
      excluded_paths: scanExcludes,
      allow_cloud: scanAllowCloud,
    };
  }

  async function runScanPreview() {
    const request = buildScanRequest();
    if (!request) {
      setNotice('폴더 찾아보기를 눌러 스캔할 폴더를 먼저 추가하세요.');
      return;
    }
    setBusy(true);
    setNotice('');
    try {
      const report = await previewOfficeScan(request);
      setScanReport(report);
      setNotice(
        report.included_count
          ? `스캔 미리보기 완료: 문서 ${report.included_count}개를 읽습니다.`
          : '읽을 수 있는 문서를 찾지 못했습니다. 경로를 확인해 주세요.',
      );
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '스캔 미리보기 실패');
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
      input_summary: message || '회사 폴더 자동 분석',
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
        company_profile: {
          ...neutralCompanyProfile,
          deployment_preference: llmChoice === 'api' ? 'api_allowed' : 'local_recommended',
        },
        scan: buildScanRequest(),
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
            <FormActions>
              <Button disabled={busy} onClick={() => void createAdmin()}>관리자 생성 후 계속</Button>
            </FormActions>
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
            <FormActions>
              <Button disabled={busy} onClick={() => void configureLlm()}>LLM 설정 저장 후 계속</Button>
            </FormActions>
          </div>
        ) : null}

        {step === 'data' ? (
          <div className="memory-form">
            <div className="panel-subsection">
              <h3>회사 폴더 선택</h3>
              <p className="muted">
                회사 문서가 있는 폴더를 고르면 AI가 문서를 읽고 회사가 무슨 일을 하는지, 부서와 업무 흐름이
                어떻게 되는지 스스로 파악해 초안을 만듭니다. 열면 안 되는 폴더는 제외로 지정하세요 (여러 개 가능).
                비밀번호·인증서·설정 파일은 항상 자동 제외됩니다.
              </p>
              <FormActions>
                <Button onClick={() => setShowFolderBrowser(true)}>폴더 찾아보기</Button>
              </FormActions>
              {scanRoots.length ? (
                <div className="path-tag-list">
                  {scanRoots.map((path) => (
                    <div className="path-tag" key={path}>
                      <span>📂 스캔</span>
                      <code>{path}</code>
                      <Button
                        variant="secondary"
                        onClick={() => setScanRoots(scanRoots.filter((item) => item !== path))}
                      >
                        삭제
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted">아직 선택한 폴더가 없습니다. [폴더 찾아보기]로 추가하세요.</p>
              )}
              {scanExcludes.length ? (
                <div className="path-tag-list">
                  {scanExcludes.map((path) => (
                    <div className="path-tag excluded" key={path}>
                      <span>🚫 제외</span>
                      <code>{path}</code>
                      <Button
                        variant="secondary"
                        onClick={() => setScanExcludes(scanExcludes.filter((item) => item !== path))}
                      >
                        삭제
                      </Button>
                    </div>
                  ))}
                </div>
              ) : null}
              {llmChoice === 'api' ? (
                <p className="muted">
                  스캔한 문서는 선택하신 {provider.toUpperCase()} API로 분석됩니다. 분석 용도로만 사용되며,
                  LLM 설정 단계에서 이미 동의하셔서 추가 확인은 필요 없습니다.
                </p>
              ) : (
                <label className="checkbox-inline">
                  <input
                    type="checkbox"
                    checked={scanAllowCloud}
                    onChange={(e) => setScanAllowCloud(e.target.checked)}
                  />
                  로컬 LLM이 준비되지 않았다면, 스캔한 문서를 외부 API로 보내 분석하는 것에 동의합니다.
                </label>
              )}
              <FormActions>
                <Button variant="secondary" disabled={busy} onClick={() => void runScanPreview()}>
                  스캔 미리보기
                </Button>
              </FormActions>
              {scanReport ? (
                <article className="log-card">
                  <strong>
                    읽을 문서 {scanReport.included_count}개
                    {scanReport.truncated ? ' (상한 도달, 일부만 사용)' : ''}
                  </strong>
                  <small>
                    제외됨: {Object.entries(scanReport.skipped_counts)
                      .map(([reason, count]) => `${reason} ${count}`)
                      .join(' · ') || '없음'}
                  </small>
                  {scanReport.missing_roots.length ? (
                    <small>찾지 못한 경로: {scanReport.missing_roots.join(', ')}</small>
                  ) : null}
                  <div className="log-list">
                    {scanReport.files
                      .filter((file) => file.included)
                      .slice(0, 8)
                      .map((file) => (
                        <small key={file.path}>{file.path}</small>
                      ))}
                  </div>
                </article>
              ) : null}
            </div>
            <div className="panel-subsection">
              <h3>파일 직접 업로드 (선택)</h3>
              <p className="muted">폴더 스캔 대신, 또는 스캔과 함께 조직도·운영 규정 파일을 직접 올릴 수도 있습니다.</p>
              <input type="file" multiple accept=".csv,.tsv,.xlsx,.txt,.md" onChange={(e) => void uploadFiles(e)} />
              <div className="log-list">
                {uploads.map((upload) => (
                  <article className="log-card" key={upload.id}>
                    <strong>{upload.filename}</strong>
                    <small>{upload.path}</small>
                  </article>
                ))}
              </div>
            </div>
            <FormActions>
              <Button
                disabled={!scanRoots.length && !uploads.length}
                onClick={() => setStep('analyze')}
              >
                데이터 선택 완료
              </Button>
            </FormActions>
          </div>
        ) : null}

        {step === 'analyze' ? (
          <div className="memory-form">
            <p className="muted">
              선택한 폴더의 문서를 AI가 읽고, 이 회사가 무슨 일을 하는 회사인지 스스로 파악해서
              회사 프로필과 운영 메모리 초안을 만듭니다. 원하시면 추가 요청을 남길 수 있습니다.
            </p>
            <textarea
              value={message}
              placeholder="(선택) 예: 생산/품질 쪽 업무 흐름을 특히 자세히 정리해줘"
              onChange={(e) => setMessage(e.target.value)}
            />
            <FormActions>
              <Button disabled={busy} onClick={() => void analyze()}>
                {busy ? 'AI가 문서를 읽고 있습니다...' : 'AI 분석 시작'}
              </Button>
            </FormActions>
            {busy ? (
              <p className="muted">추론형 모델은 1~3분 정도 걸릴 수 있습니다. 화면을 닫지 마세요.</p>
            ) : null}
          </div>
        ) : null}

        {step === 'review' ? (
          <div className="memory-form">
            {result?.provenance?.source === 'company_scan' ? (
              <article className="log-card">
                <strong>AI가 회사 폴더를 읽고 만든 초안입니다</strong>
                <small>
                  읽은 문서 {result.provenance.scanned_files}개 · 분석 경로:{' '}
                  {result.provenance.route === 'local' ? '로컬 LLM (외부 전송 없음)' : 'API 모델'}
                </small>
              </article>
            ) : null}
            {result ? (
              <div className="panel-subsection">
                <h3>AI가 파악한 우리 회사</h3>
                <p className="muted">읽어보고 맞으면 그대로 두고, 다른 부분만 [수정]을 눌러 고치세요. 고친 내용이 그대로 저장됩니다.</p>
                <EditableFact
                  label="회사 이름"
                  value={String(result.operations_memory.company_name ?? '')}
                  onSave={(value) => setResult({ ...result, operations_memory: { ...result.operations_memory, company_name: value } })}
                />
                <EditableFact
                  label="무슨 일을 하는 회사인가"
                  value={String(result.operations_memory.organization ?? '')}
                  onSave={(value) => setResult({ ...result, operations_memory: { ...result.operations_memory, organization: value } })}
                />
                <EditableFact
                  label="부서 구성"
                  value={String(result.operations_memory.departments ?? '')}
                  onSave={(value) => setResult({ ...result, operations_memory: { ...result.operations_memory, departments: value } })}
                />
                <EditableFact
                  label="주요 업무 흐름"
                  value={String(result.operations_memory.key_workflows ?? '')}
                  onSave={(value) => setResult({ ...result, operations_memory: { ...result.operations_memory, key_workflows: value } })}
                />
                <EditableFact
                  label="민감정보 취급 원칙"
                  value={String(result.operations_memory.sensitive_policy ?? '')}
                  onSave={(value) => setResult({ ...result, operations_memory: { ...result.operations_memory, sensitive_policy: value } })}
                />
              </div>
            ) : null}
            {result?.questions?.length ? (
              <div className="panel-subsection">
                <h3>⚠ AI가 확인을 요청한 항목</h3>
                <ul>{result.questions.map((question) => <li key={question}>{question}</li>)}</ul>
              </div>
            ) : null}
            {result?.warnings?.length ? (
              <ul>{result.warnings.map((warning) => <li key={warning} className="alert">{warning}</li>)}</ul>
            ) : null}
            <p className="muted">아래 추천 구성은 필요 없는 항목을 끄고 적용할 수 있습니다. 직원 로그인 계정은 자동 생성하지 않습니다.</p>
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
            <FormActions>
              <Button disabled={busy} onClick={() => void apply()}>검토 완료 · 초기 세팅 적용</Button>
            </FormActions>
          </div>
        ) : null}

        {notice ? <p className="alert">{notice}</p> : null}
        <AiJobStatusBar job={aiJob} />
      </section>
      {showFolderBrowser ? (
        <FolderBrowserModal
          roots={scanRoots}
          excludes={scanExcludes}
          onAddRoot={(path) =>
            setScanRoots((current) => (current.includes(path) ? current : [...current, path]))
          }
          onAddExclude={(path) =>
            setScanExcludes((current) => (current.includes(path) ? current : [...current, path]))
          }
          onClose={() => setShowFolderBrowser(false)}
        />
      ) : null}
    </main>
  );
}

function EditableFact({
  label,
  value,
  onSave,
}: {
  label: string;
  value: string;
  onSave: (value: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  return (
    <article className="review-fact-card">
      <div className="review-fact-head">
        <strong>{label}</strong>
        {editing ? (
          <div className="review-fact-actions">
            <Button
              onClick={() => {
                onSave(draft.trim());
                setEditing(false);
              }}
            >
              저장
            </Button>
            <Button variant="secondary" onClick={() => setEditing(false)}>취소</Button>
          </div>
        ) : (
          <Button
            variant="secondary"
            onClick={() => {
              setDraft(value);
              setEditing(true);
            }}
          >
            수정
          </Button>
        )}
      </div>
      {editing ? (
        <textarea rows={3} value={draft} onChange={(e) => setDraft(e.target.value)} />
      ) : (
        <p>{value || <span className="muted">문서에서 찾지 못했습니다 — 직접 입력해 주세요.</span>}</p>
      )}
    </article>
  );
}

function StepBar({ step }: { step: Step }) {
  const steps: Array<[Step, string]> = [
    ['admin', '관리자'],
    ['llm', 'AI 엔진'],
    ['data', '회사 데이터'],
    ['analyze', 'AI 분석'],
    ['review', '확인 · 적용'],
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
