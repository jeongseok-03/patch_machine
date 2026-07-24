import { useEffect, useMemo, useState } from 'react';

import {
  fetchLlmRuntime,
  fetchProviderModels,
  saveLlmRuntime,
  type LlmProviderName,
  type LlmRuntime,
  type LlmRuntimeRoute,
  type LlmTaskRoute,
} from '../../api';

const PROVIDERS: LlmProviderName[] = ['vllm', 'solar', 'openai', 'anthropic', 'gemini', 'together', 'fake'];

const LOCAL_MODELS = [
  'Qwen/Qwen3-4B',
  'Qwen/Qwen3-8B',
  'Qwen/Qwen2.5-7B-Instruct',
  'LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct',
  'upstage/SOLAR-10.7B-Instruct-v1.0',
];

const TASKS: Array<{ id: string; label: string; description: string }> = [
  { id: 'memory_summary', label: 'AI 가독 정보 요약', description: '네고티움 영구메모리와 작업 기억을 읽기 좋게 요약' },
  { id: 'agent_planning', label: '에이전트 실행계획', description: '작업 목표를 승인 가능한 실행 단계로 분해' },
  { id: 'document_generation', label: '문서 자동화', description: '보고서, 회의록, 업무 요청서 등 회사 문서 생성' },
  { id: 'hiring', label: '채용/면접', description: '직무 요구사항, 면접 질문, 온보딩 문서 생성' },
  { id: 'handover', label: '인수인계', description: '담당자 변경 시 업무 맥락과 다음 액션 정리' },
  { id: 'chat', label: 'AI 어시스턴트', description: '메모리 기반 실시간 채팅' },
];

function defaultTaskRoute(runtime: LlmRuntime): LlmTaskRoute {
  return {
    route: runtime.default_route,
    provider: runtime.default_provider,
    model: '',
  };
}

export default function LlmTaskRoutingPanel() {
  const [runtime, setRuntime] = useState<LlmRuntime | null>(null);
  const [message, setMessage] = useState('');
  const [providerModels, setProviderModels] = useState<Record<string, string[]>>({});

  async function refresh() {
    try {
      setRuntime(await fetchLlmRuntime());
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'LLM 작업 설정 로드 실패');
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function ensureProviderModels(provider: LlmProviderName) {
    if (provider === 'vllm' || providerModels[provider]?.length) return;
    try {
      const payload = await fetchProviderModels(provider);
      setProviderModels((current) => ({ ...current, [provider]: payload.models }));
    } catch {
      setProviderModels((current) => ({ ...current, [provider]: [] }));
    }
  }

  async function updateTask(taskId: string, patch: Partial<LlmTaskRoute>) {
    if (!runtime) return;
    const current = runtime.task_routes?.[taskId] || defaultTaskRoute(runtime);
    const nextRoute = { ...current, ...patch };
    if (patch.provider && patch.provider !== current.provider) {
      void ensureProviderModels(patch.provider);
    }
    const next: LlmRuntime = {
      ...runtime,
      task_routes: {
        ...(runtime.task_routes || {}),
        [taskId]: nextRoute,
      },
    };
    setRuntime(next);
    const saved = await saveLlmRuntime(next);
    setRuntime(saved);
    setMessage('작업별 LLM 설정을 저장했습니다. 선택한 모델이 실제 추론에 반영됩니다.');
  }

  const localOptions = useMemo(() => {
    const base = runtime?.local_model ? [runtime.local_model] : [];
    return [...base, ...LOCAL_MODELS].filter((model, index, arr) => arr.indexOf(model) === index);
  }, [runtime?.local_model]);

  function modelOptionsFor(route: LlmTaskRoute): string[] {
    if (route.route === 'local' || route.provider === 'vllm') {
      return localOptions;
    }
    return providerModels[route.provider] || [];
  }

  return (
    <section className="panel llm-task-routing-panel">
      <p className="eyebrow">LLM task routing</p>
      <h2>LLM 작업 설정</h2>
      <p className="muted small">
        작업별 route·provider·모델을 지정합니다. 모델을 비우면 provider 기본값(또는 로컬 모델 설정)을 사용합니다.
      </p>
      {!runtime ? <p className="muted">설정을 불러오는 중입니다.</p> : null}
      {runtime ? (
        <div className="llm-task-table" role="table" aria-label="작업별 LLM 설정">
          {TASKS.map((task) => {
            const route = runtime.task_routes?.[task.id] || defaultTaskRoute(runtime);
            const options = modelOptionsFor(route);
            return (
              <div className="llm-task-row" role="row" key={task.id}>
                <div className="llm-task-copy">
                  <strong>{task.label}</strong>
                  <span className="muted small">{task.description}</span>
                </div>
                <label>
                  Route
                  <select
                    value={route.route}
                    onChange={(e) => void updateTask(task.id, { route: e.target.value as LlmRuntimeRoute })}
                  >
                    <option value="local">local</option>
                    <option value="api">api</option>
                  </select>
                </label>
                <label>
                  Provider
                  <select
                    value={route.provider}
                    onFocus={() => void ensureProviderModels(route.provider)}
                    onChange={(e) => {
                      const provider = e.target.value as LlmProviderName;
                      void ensureProviderModels(provider);
                      void updateTask(task.id, { provider, model: '' });
                    }}
                  >
                    {PROVIDERS.map((provider) => (
                      <option key={provider} value={provider}>
                        {provider}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Model
                  <select
                    value={route.model || ''}
                    onFocus={() => void ensureProviderModels(route.provider)}
                    onChange={(e) => void updateTask(task.id, { model: e.target.value })}
                  >
                    <option value="">(기본값 사용)</option>
                    {options.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            );
          })}
        </div>
      ) : null}
      {message ? <p className="muted">{message}</p> : null}
    </section>
  );
}
