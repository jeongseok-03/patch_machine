import { useState } from 'react';

import { login, requestAccount, setupAdmin, type AuthUser } from '../api';
import { setSessionToken } from '../auth';

type Props = {
  setupRequired: boolean;
  onAuthenticated: (user: AuthUser) => void;
};

export default function AuthPage({ setupRequired, onAuthenticated }: Props) {
  const [mode, setMode] = useState<'login' | 'request'>(setupRequired ? 'login' : 'login');
  const [form, setForm] = useState({ user_id: '', display_name: '', title: '', password: '' });
  const [message, setMessage] = useState('');

  async function submit() {
    setMessage('');
    try {
      if (setupRequired) {
        const session = await setupAdmin({ ...form, title: form.title || '관리자' });
        setSessionToken(session.token);
        onAuthenticated(session.user);
        return;
      }
      if (mode === 'login') {
        const session = await login({ user_id: form.user_id, password: form.password });
        setSessionToken(session.token);
        onAuthenticated(session.user);
        return;
      }
      await requestAccount(form);
      setMessage('계정 개설 요청을 보냈습니다. 관리자가 승인하면 로그인할 수 있습니다.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '인증 요청 실패');
    }
  }

  return (
    <main className="auth-layout">
      <section className="panel auth-panel">
        <img className="auth-logo" src="/negotium-logo.png" alt="Negotium" />
        <p className="eyebrow">{setupRequired ? 'Initial Admin Setup' : 'Login'}</p>
        <h1>{setupRequired ? '첫 관리자 계정 설정' : mode === 'login' ? '로그인' : '계정 개설 요청'}</h1>
        <div className="memory-form">
          <label>
            사용자 ID
            <input value={form.user_id} onChange={(event) => setForm({ ...form, user_id: event.target.value })} />
          </label>
          {setupRequired || mode === 'request' ? (
            <>
              <label>
                표시 이름
                <input
                  value={form.display_name}
                  onChange={(event) => setForm({ ...form, display_name: event.target.value })}
                />
              </label>
              <label>
                직함
                <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
              </label>
            </>
          ) : null}
          <label>
            비밀번호
            <input
              type="password"
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
            />
          </label>
          <button type="button" onClick={() => void submit()}>
            {setupRequired ? '관리자 생성' : mode === 'login' ? '로그인' : '요청 보내기'}
          </button>
          {!setupRequired ? (
            <button
              className="secondary-button"
              type="button"
              onClick={() => setMode(mode === 'login' ? 'request' : 'login')}
            >
              {mode === 'login' ? '계정 개설 요청' : '로그인으로 돌아가기'}
            </button>
          ) : null}
          {message ? <p className="muted">{message}</p> : null}
        </div>
      </section>
    </main>
  );
}
