import { FormEvent, useEffect, useState } from 'react';

import {
  fetchTokenLimits,
  saveTokenLimits,
  type TokenLimit,
  type TokenLimitStatus,
} from '../api';

const DEFAULT_LIMIT: TokenLimit = {
  enforcement_enabled: true,
  per_request_max_tokens: 4000,
  daily_total_tokens: 200_000,
  monthly_total_tokens: 4_000_000,
};

export default function TokenLimitsPage() {
  const [status, setStatus] = useState<TokenLimitStatus | null>(null);
  const [form, setForm] = useState<TokenLimit>(DEFAULT_LIMIT);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function refresh() {
    try {
      const next = await fetchTokenLimits();
      setStatus(next);
      setForm(next.limits);
    } catch (err) {
      setError(err instanceof Error ? err.message : '토큰 제한 정보를 불러오지 못했습니다.');
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    setError('');
    try {
      const next = await saveTokenLimits({
        enforcement_enabled: form.enforcement_enabled,
        per_request_max_tokens: Math.max(0, Number(form.per_request_max_tokens) || 0),
        daily_total_tokens: Math.max(0, Number(form.daily_total_tokens) || 0),
        monthly_total_tokens: Math.max(0, Number(form.monthly_total_tokens) || 0),
      });
      setStatus(next);
      setForm(next.limits);
      setMessage('토큰 제한 정책을 저장했습니다.');
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장에 실패했습니다.');
    } finally {
      setSaving(false);
    }
  }

  const usage = status?.usage;

  return (
    <section className="page-grid">
      <div className="panel">
        <p className="eyebrow">Token guardrail</p>
        <h2>토큰 사용량 제한</h2>
        <p className="muted">
          요청별 / 일별 / 월별 토큰 한도를 설정하고, LLM 호출 전후로 사용량을 추적합니다. 한도를 넘기면 백엔드는 429 Too
          Many Requests로 호출을 차단합니다.
        </p>
        <div className="token-limits-grid">
          <form className="connector-config-form" onSubmit={submit}>
            <label className="switch-row">
              <input
                type="checkbox"
                checked={form.enforcement_enabled}
                onChange={(event) =>
                  setForm({ ...form, enforcement_enabled: event.target.checked })
                }
              />
              <span>제한 정책을 강제 적용</span>
            </label>
            <label>
              요청별 최대 토큰 (max_tokens)
              <input
                type="number"
                min={0}
                value={form.per_request_max_tokens}
                onChange={(event) =>
                  setForm({ ...form, per_request_max_tokens: Number(event.target.value) || 0 })
                }
              />
            </label>
            <label>
              일일 합산 한도
              <input
                type="number"
                min={0}
                value={form.daily_total_tokens}
                onChange={(event) =>
                  setForm({ ...form, daily_total_tokens: Number(event.target.value) || 0 })
                }
              />
            </label>
            <label>
              월간 합산 한도
              <input
                type="number"
                min={0}
                value={form.monthly_total_tokens}
                onChange={(event) =>
                  setForm({ ...form, monthly_total_tokens: Number(event.target.value) || 0 })
                }
              />
            </label>
            <div className="switch-row">
              <button className="primary" type="submit" disabled={saving}>
                {saving ? '저장 중...' : '한도 저장'}
              </button>
              {message ? <span className="status-pill success">{message}</span> : null}
              {error ? <span className="status-pill warn">{error}</span> : null}
            </div>
          </form>
          <div className="token-summary-card">
            <h3>현재 사용량</h3>
            {usage ? (
              <dl>
                <dt>오늘 사용</dt>
                <dd>{usage.daily_total.toLocaleString()} tokens</dd>
                <dt>이번 달 사용</dt>
                <dd>{usage.monthly_total.toLocaleString()} tokens</dd>
                <dt>이번 달 한도</dt>
                <dd>{form.monthly_total_tokens.toLocaleString()} tokens</dd>
                <dt>일일 한도</dt>
                <dd>{form.daily_total_tokens.toLocaleString()} tokens</dd>
              </dl>
            ) : (
              <p className="muted small">사용량 데이터를 불러오는 중입니다.</p>
            )}
            <h4>provider 별 (이번 달)</h4>
            <ul>
              {usage
                ? Object.entries(usage.by_provider).map(([provider, value]) => (
                    <li key={`p-${provider}`}>
                      <strong>{provider}</strong> · {value.toLocaleString()} tokens
                    </li>
                  ))
                : null}
              {usage && Object.keys(usage.by_provider).length === 0 ? (
                <li className="muted small">아직 누적된 데이터가 없습니다.</li>
              ) : null}
            </ul>
            <h4>task 별 (이번 달)</h4>
            <ul>
              {usage
                ? Object.entries(usage.by_task).map(([task, value]) => (
                    <li key={`t-${task}`}>
                      <strong>{task}</strong> · {value.toLocaleString()} tokens
                    </li>
                  ))
                : null}
            </ul>
          </div>
        </div>
      </div>
      {usage && usage.recent.length > 0 ? (
        <div className="panel">
          <p className="eyebrow">Recent calls</p>
          <h2>최근 호출 내역</h2>
          <div className="log-list">
            {usage.recent.map((entry, index) => (
              <article className="log-card" key={`${entry.occurred_at}-${index}`}>
                <strong>
                  {entry.provider}/{entry.model || '(model)'} · {entry.task || 'chat'}
                </strong>
                <p>
                  prompt {entry.prompt_tokens.toLocaleString()} + completion{' '}
                  {entry.completion_tokens.toLocaleString()} = {entry.total_tokens.toLocaleString()}
                </p>
                <small>
                  {entry.actor || 'unknown'} · {entry.occurred_at}
                </small>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
