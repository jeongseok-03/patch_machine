import { useEffect, useState } from 'react';

import {
  fetchLlmRuntime,
  fetchLocalLlmStatus,
  saveLlmRuntime,
  searchHuggingFaceModels,
  startLocalLlm,
  stopLocalLlm,
  uploadDocument,
  type HuggingFaceModelItem,
  type LocalLlmStatus,
  type LlmRuntime,
  type UploadRecord,
} from '../../api';

const recommendedLocalModels = [
  'Qwen/Qwen3-4B',
  'Qwen/Qwen3-8B',
  'Qwen/Qwen2.5-7B-Instruct',
  'LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct',
  'upstage/SOLAR-10.7B-Instruct-v1.0',
];

export default function LocalAgentAdminPanel() {
  const [status, setStatus] = useState<LocalLlmStatus | null>(null);
  const [runtime, setRuntime] = useState<LlmRuntime | null>(null);
  const [selectedModel, setSelectedModel] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [query, setQuery] = useState('Qwen');
  const [hfModels, setHfModels] = useState<HuggingFaceModelItem[]>([]);
  const [adapterModel, setAdapterModel] = useState('');
  const [uploadedAdapters, setUploadedAdapters] = useState<UploadRecord[]>([]);
  const [selectedUploadPath, setSelectedUploadPath] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const modelOptions = [...recommendedLocalModels, selectedModel, ...hfModels.map((m) => m.id)]
    .filter(Boolean)
    .filter((model, index, arr) => arr.indexOf(model) === index);

  async function refresh() {
    try {
      const [nextStatus, nextRuntime] = await Promise.all([fetchLocalLlmStatus(), fetchLlmRuntime()]);
      setStatus(nextStatus);
      setRuntime(nextRuntime);
      setSelectedModel((current) => current || nextRuntime.local_model || nextStatus.model || 'Qwen/Qwen3-4B');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '로컬 에이전트 상태 조회 실패');
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function toggleLocal() {
    setBusy(true);
    setMessage('');
    try {
      const next = status?.enabled ? await stopLocalLlm() : await startLocalLlm();
      setStatus(next);
      setMessage(status?.enabled ? '로컬 에이전트를 중지했습니다.' : '로컬 에이전트 기동을 요청했습니다.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '로컬 에이전트 제어 실패');
    } finally {
      setBusy(false);
    }
  }

  async function searchModels() {
    setBusy(true);
    setMessage('');
    try {
      const payload = await searchHuggingFaceModels(query);
      setHfModels(payload.models);
      if (payload.models[0]) setSelectedModel(payload.models[0].id);
      setMessage(payload.models.length ? 'Hugging Face 모델 목록을 불러왔습니다.' : '검색 결과가 없습니다.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Hugging Face 모델 검색 실패');
    } finally {
      setBusy(false);
    }
  }

  async function saveLocalModel() {
    if (!runtime) return;
    const nextModel = (selectedUploadPath || adapterModel || selectedModel).trim();
    if (!nextModel) {
      setMessage('저장할 모델을 선택하세요.');
      return;
    }
    setBusy(true);
    setMessage('');
    try {
      const saved = await saveLlmRuntime({
        ...runtime,
        local_model: nextModel,
        default_route: 'local',
        default_provider: 'vllm',
      });
      setRuntime(saved);
      setStatus(await fetchLocalLlmStatus());
      setMessage(`로컬 모델을 저장했습니다: ${nextModel}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '로컬 모델 설정 저장 실패');
    } finally {
      setBusy(false);
    }
  }

  async function uploadAdapterFile(fileList: FileList | null) {
    const file = fileList?.[0];
    if (!file) return;
    setBusy(true);
    setMessage('');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('work_title', '로컬 에이전트 파인튜닝/LoRA 모델');
      form.append('tags', 'local_model,lora,finetune');
      form.append('description', '로컬 에이전트 LoRA/파인튜닝 파일');
      const saved = (await uploadDocument(form)).upload;
      setUploadedAdapters((current) => [saved, ...current]);
      setSelectedUploadPath(saved.path);
      setMessage(`업로드했습니다: ${saved.filename}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '업로드 실패');
    } finally {
      setBusy(false);
    }
  }

  const embedHint =
    status?.state === 'unavailable'
      ? `모드 ${status.mode}: 호스트에서 NG_VLLM_MODE=embedded 로 negotium serve 실행`
      : '';

  return (
    <section className="panel">
      <p className="eyebrow">Local agent</p>
      <h2>로컬 모델 설정</h2>
      <p className="muted">관리자가 로컬 LLM 모델을 선택하고 기동합니다. 일반 사용자는 AI 어시스턴트에서 상태만 확인합니다.</p>

      <div className={`local-llm-status local-llm-status-${status?.state || 'unknown'}`}>
        <div>
          <p className="eyebrow">Local LLM</p>
          <strong>{status?.message || '상태를 불러오는 중입니다.'}</strong>
          <p className="muted">
            {status?.model || selectedModel || 'model -'} · {status?.mode || 'mode -'}
            {embedHint ? ` · ${embedHint}` : ''}
          </p>
          {status?.error ? <p className="alert">{status.error}</p> : null}
        </div>
        <span className="status-pill">{status?.state || 'unknown'}</span>
      </div>

      <div className="memory-form">
        <label>
          로컬 모델
          <select value={selectedModel} onChange={(event) => {
            setSelectedModel(event.target.value);
            setSelectedUploadPath('');
          }}>
            {modelOptions.map((model) => (
              <option key={model} value={model}>{model}</option>
            ))}
          </select>
        </label>
        <div className="form-actions">
          <button type="button" disabled={busy} onClick={() => void saveLocalModel()}>
            모델 저장
          </button>
          <button type="button" disabled={busy} onClick={() => void toggleLocal()}>
            {status?.enabled ? 'Local OFF' : 'Local ON'}
          </button>
          <button type="button" className="secondary-button" onClick={() => void refresh()}>
            새로고침
          </button>
        </div>
        <button type="button" className="secondary-button" onClick={() => setShowSearch((v) => !v)}>
          {showSearch ? '모델 검색 닫기' : '더 찾기 (Hugging Face)'}
        </button>
        {showSearch ? (
          <div className="panel-subsection">
            <label>
              검색어
              <div className="inline-input-row">
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Qwen, EXAONE, Korean LLM" />
                <button className="secondary-button" type="button" disabled={busy} onClick={() => void searchModels()}>
                  검색
                </button>
              </div>
            </label>
          </div>
        ) : null}
        <button type="button" className="secondary-button" onClick={() => setShowAdvanced((v) => !v)}>
          {showAdvanced ? '고급 설정 닫기' : '고급 설정 (LoRA / 업로드)'}
        </button>
        {showAdvanced ? (
          <div className="panel-subsection">
            <label>
              LoRA Hugging Face repo ID
              <input value={adapterModel} onChange={(event) => setAdapterModel(event.target.value)} placeholder="organization/model-lora" />
            </label>
            <label>
              LoRA 파일 업로드
              <input type="file" accept=".safetensors,.bin,.pt,.pth,.gguf,.zip,.tar,.json" onChange={(event) => void uploadAdapterFile(event.target.files)} />
            </label>
            {uploadedAdapters.length ? (
              <label>
                업로드 파일 선택
                <select value={selectedUploadPath} onChange={(event) => setSelectedUploadPath(event.target.value)}>
                  <option value="">사용 안 함</option>
                  {uploadedAdapters.map((upload) => (
                    <option key={upload.id} value={upload.path}>{upload.filename}</option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>
        ) : null}
      </div>
      {message ? <p className="muted">{message}</p> : null}
    </section>
  );
}
