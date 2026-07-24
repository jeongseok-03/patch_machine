import { getAuthHeaders } from '../auth';
import { requestJson } from './http';
import type {
  ChatResponse,
  ChatSendOptions,
  ChatStreamHandlers,
  HuggingFaceModelSearchResult,
  LlmProviderName,
  LlmRuntime,
  LlmRuntimeRoute,
  LocalLlmStatus,
  ProviderModelPayload,
  TokenLimit,
  TokenLimitStatus,
} from './types';

export function fetchLlmRuntime(): Promise<LlmRuntime> {
  return requestJson<LlmRuntime>('/api/llm/runtime');
}

export function saveLlmRuntime(runtime: LlmRuntime): Promise<LlmRuntime> {
  return requestJson<LlmRuntime>('/api/llm/runtime', {
    method: 'PUT',
    body: JSON.stringify(runtime),
  });
}

export function fetchLocalLlmStatus(): Promise<LocalLlmStatus> {
  return requestJson<LocalLlmStatus>('/api/llm/local-status');
}

export function startLocalLlm(): Promise<LocalLlmStatus> {
  return requestJson<LocalLlmStatus>('/api/llm/local/start', { method: 'POST' });
}

export function stopLocalLlm(): Promise<LocalLlmStatus> {
  return requestJson<LocalLlmStatus>('/api/llm/local/stop', { method: 'POST' });
}

export function searchHuggingFaceModels(query: string): Promise<HuggingFaceModelSearchResult> {
  return requestJson<HuggingFaceModelSearchResult>('/api/llm/local/huggingface/search', {
    method: 'POST',
    body: JSON.stringify({ query, limit: 12 }),
  });
}

export function sendChatMessage(
  message: string,
  route: LlmRuntimeRoute,
  provider: LlmProviderName,
  options: string | ChatSendOptions = 'chat',
): Promise<ChatResponse> {
  const opts: ChatSendOptions = typeof options === 'string' ? { task: options } : options;
  return requestJson<ChatResponse>('/api/llm/chat', {
    method: 'POST',
    body: JSON.stringify({
      message,
      route,
      provider,
      task: opts.task ?? 'chat',
      attachment_ids: opts.attachmentIds ?? [],
      history_limit: opts.historyLimit ?? 8,
    }),
  });
}

export async function streamChatMessage(
  message: string,
  route: LlmRuntimeRoute,
  provider: LlmProviderName,
  handlers: ChatStreamHandlers,
  options: ChatSendOptions = {},
): Promise<void> {
  const response = await fetch('/api/llm/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({
      message,
      route,
      provider,
      task: options.task ?? 'chat',
      attachment_ids: options.attachmentIds ?? [],
      history_limit: options.historyLimit ?? 8,
    }),
  });
  if (!response.ok || !response.body) {
    const detail = response.body ? await response.text() : `${response.status} ${response.statusText}`;
    handlers.onError?.(detail);
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf('\n\n');
      let eventName = 'message';
      const dataLines: string[] = [];
      for (const line of rawEvent.split('\n')) {
        if (line.startsWith('event:')) eventName = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length === 0) continue;
      let parsed: unknown;
      try {
        parsed = JSON.parse(dataLines.join('\n'));
      } catch {
        continue;
      }
      if (eventName === 'meta') handlers.onMeta?.(parsed as never);
      else if (eventName === 'delta') handlers.onDelta?.((parsed as { text: string }).text);
      else if (eventName === 'done') handlers.onDone?.(parsed as ChatResponse);
      else if (eventName === 'error') handlers.onError?.((parsed as { detail: string }).detail);
    }
  }
}

export function fetchProviderModels(provider: string): Promise<ProviderModelPayload> {
  return requestJson<ProviderModelPayload>(`/api/llm/providers/${provider}/models`);
}

export function previewProviderModels(provider: string, apiKey: string): Promise<ProviderModelPayload> {
  return requestJson<ProviderModelPayload>(`/api/llm/providers/${provider}/models/preview`, {
    method: 'POST',
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export function fetchTokenLimits(): Promise<TokenLimitStatus> {
  return requestJson<TokenLimitStatus>('/api/llm/token-limits');
}

export function saveTokenLimits(payload: TokenLimit): Promise<TokenLimitStatus> {
  return requestJson<TokenLimitStatus>('/api/llm/token-limits', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}
