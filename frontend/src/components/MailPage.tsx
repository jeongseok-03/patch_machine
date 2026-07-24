import { useEffect, useState } from 'react';

import {
  draftMailReply,
  fetchMailAccount,
  fetchMailInbox,
  fetchMailMessage,
  saveMailAccount,
  sendMailMessage,
  triageMail,
  type MailDetail,
  type MailSummary,
  type MailTriage,
} from '../api';
import Button from './common/Button';
import FormActions from './common/FormActions';

const PRESETS: Array<[string, string, number, string, number]> = [
  ['네이버웍스', 'imap.worksmobile.com', 993, 'smtp.worksmobile.com', 465],
  ['네이버', 'imap.naver.com', 993, 'smtp.naver.com', 465],
  ['지메일', 'imap.gmail.com', 993, 'smtp.gmail.com', 465],
  ['다음', 'imap.daum.net', 993, 'smtp.daum.net', 465],
];

export default function MailPage() {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [form, setForm] = useState({
    email: '',
    imap_host: '',
    imap_port: 993,
    smtp_host: '',
    smtp_port: 465,
    username: '',
    password: '',
  });
  const [inbox, setInbox] = useState<MailSummary[]>([]);
  const [triage, setTriage] = useState<MailTriage | null>(null);
  const [message, setMessage] = useState<MailDetail | null>(null);
  const [compose, setCompose] = useState<{ to: string; subject: string; body: string } | null>(null);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    fetchMailAccount()
      .then((account) => {
        setConfigured(Boolean(account.configured));
        if (account.configured) void loadInbox();
      })
      .catch(() => setConfigured(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadInbox() {
    setBusy('inbox');
    setNotice('');
    try {
      const payload = await fetchMailInbox();
      setInbox(payload.items);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '메일함을 불러오지 못했습니다.');
    } finally {
      setBusy('');
    }
  }

  async function connect() {
    setBusy('connect');
    setNotice('');
    try {
      await saveMailAccount(form);
      setConfigured(true);
      await loadInbox();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '연결 실패');
    } finally {
      setBusy('');
    }
  }

  async function runTriage() {
    setBusy('triage');
    try {
      setTriage(await triageMail());
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'AI 분류 실패');
    } finally {
      setBusy('');
    }
  }

  async function openMessage(uid: string) {
    setBusy('open');
    try {
      setMessage(await fetchMailMessage(uid));
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '메일을 열지 못했습니다.');
    } finally {
      setBusy('');
    }
  }

  async function makeReply(uid: string) {
    setBusy('draft');
    try {
      const result = await draftMailReply(uid);
      setCompose({ to: result.to, subject: result.subject, body: result.draft });
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '답장 초안 실패');
    } finally {
      setBusy('');
    }
  }

  async function send() {
    if (!compose) return;
    setBusy('send');
    try {
      await sendMailMessage(compose);
      setCompose(null);
      setNotice('보냈습니다.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '전송 실패');
    } finally {
      setBusy('');
    }
  }

  const badge = (uid: string) => {
    if (!triage) return null;
    if (triage.reply_needed.includes(uid)) return <span className="mail-badge reply">답장 필요</span>;
    if (triage.fyi.includes(uid)) return <span className="mail-badge fyi">참고</span>;
    return null;
  };

  if (configured === null) {
    return <section className="panel">메일 설정을 확인하는 중...</section>;
  }

  if (!configured) {
    return (
      <section>
        <div className="hero-panel">
          <p className="eyebrow">메일</p>
          <h1>회사 메일 연결</h1>
          <p className="lede">
            쓰던 회사 메일(네이버웍스, 지메일 등)을 그대로 연결합니다. 메일은 원래 서버에 그대로 있고,
            이 화면에서 읽고 쓰고 AI 분류를 받는 것입니다. 비밀번호는 암호화되어 이 컴퓨터에만 저장됩니다.
          </p>
        </div>
        <article className="panel report-card">
          <div className="report-item-meta">
            {PRESETS.map(([name, imap, imapPort, smtp, smtpPort]) => (
              <button
                type="button"
                className="source-chip"
                key={name}
                onClick={() =>
                  setForm({ ...form, imap_host: imap, imap_port: imapPort, smtp_host: smtp, smtp_port: smtpPort })
                }
              >
                {name}
              </button>
            ))}
          </div>
          <div className="memory-form">
            <input placeholder="메일 주소" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <input placeholder="IMAP 서버 (예: imap.naver.com)" value={form.imap_host} onChange={(e) => setForm({ ...form, imap_host: e.target.value })} />
            <input placeholder="SMTP 서버 (예: smtp.naver.com)" value={form.smtp_host} onChange={(e) => setForm({ ...form, smtp_host: e.target.value })} />
            <input type="password" placeholder="비밀번호 (2단계 인증 사용 시 앱 비밀번호)" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <FormActions>
              <Button disabled={busy === 'connect'} onClick={() => void connect()}>
                {busy === 'connect' ? '연결 확인 중...' : '연결하기'}
              </Button>
            </FormActions>
          </div>
          {notice ? <p className="alert">{notice}</p> : null}
        </article>
      </section>
    );
  }

  return (
    <section>
      <div className="hero-panel">
        <p className="eyebrow">메일</p>
        <h1>받은편지함</h1>
        <FormActions>
          <Button disabled={busy === 'triage'} onClick={() => void runTriage()}>
            {busy === 'triage' ? 'AI가 읽는 중...' : 'AI 분류 (답할 것/참고할 것)'}
          </Button>
          <Button variant="secondary" disabled={busy === 'inbox'} onClick={() => void loadInbox()}>
            새로고침
          </Button>
        </FormActions>
        {triage?.summary ? <p className="lede">{triage.summary}</p> : null}
        {notice ? <p className="alert">{notice}</p> : null}
      </div>

      <div className="report-grid" style={{ gridTemplateColumns: '1fr' }}>
        {inbox.map((item) => (
          <article className="panel report-card mail-row" key={item.uid}>
            <div className="mail-row-head">
              <strong>{item.subject || '(제목 없음)'}</strong>
              {badge(item.uid)}
            </div>
            <p className="muted" style={{ margin: 0, fontSize: '0.82rem' }}>
              {item.from} · {item.date}
            </p>
            <p style={{ margin: 0 }}>{item.snippet}</p>
            <FormActions>
              <Button variant="secondary" onClick={() => void openMessage(item.uid)}>열기</Button>
              <Button variant="secondary" disabled={busy === 'draft'} onClick={() => void makeReply(item.uid)}>
                {busy === 'draft' ? '초안 작성 중...' : 'AI 답장 초안'}
              </Button>
            </FormActions>
          </article>
        ))}
        {!inbox.length ? <article className="panel report-empty"><p className="muted">받은 메일이 없습니다.</p></article> : null}
      </div>

      {message ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" onClick={() => setMessage(null)}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="folder-browser-head">
              <strong>{message.subject}</strong>
              <Button variant="secondary" onClick={() => setMessage(null)}>닫기</Button>
            </div>
            <p className="muted">{message.from} → {message.to} · {message.date}</p>
            <pre className="doc-preview">{message.body}</pre>
            <FormActions>
              <Button onClick={() => void makeReply(message.uid)}>AI 답장 초안</Button>
            </FormActions>
          </div>
        </div>
      ) : null}

      {compose ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="modal-panel">
            <div className="folder-browser-head">
              <strong>답장 보내기</strong>
              <Button variant="secondary" onClick={() => setCompose(null)}>닫기</Button>
            </div>
            <div className="memory-form">
              <input value={compose.to} onChange={(e) => setCompose({ ...compose, to: e.target.value })} />
              <input value={compose.subject} onChange={(e) => setCompose({ ...compose, subject: e.target.value })} />
              <textarea rows={10} value={compose.body} onChange={(e) => setCompose({ ...compose, body: e.target.value })} />
              <FormActions>
                <Button disabled={busy === 'send'} onClick={() => void send()}>
                  {busy === 'send' ? '보내는 중...' : '보내기'}
                </Button>
              </FormActions>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
