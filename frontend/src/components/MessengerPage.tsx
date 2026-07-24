import { useCallback, useEffect, useRef, useState } from 'react';

import {
  createChannel,
  fetchChannels,
  fetchMessages,
  sendMessage,
  summarizeChannel,
  type AuthUser,
  type ChatChannel,
  type ChatMessage,
} from '../api';
import Button from './common/Button';

const POLL_MS = 3000;

export default function MessengerPage({ user }: { user: AuthUser }) {
  const [channels, setChannels] = useState<ChatChannel[]>([]);
  const [activeId, setActiveId] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [newChannel, setNewChannel] = useState('');
  const [summary, setSummary] = useState('');
  const [summaryBusy, setSummaryBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const listRef = useRef<HTMLDivElement | null>(null);
  const lastIdRef = useRef('');

  useEffect(() => {
    fetchChannels()
      .then((payload) => {
        setChannels(payload.items);
        if (payload.items.length && !activeId) setActiveId(payload.items[0].id);
      })
      .catch(() => setNotice('채널을 불러오지 못했습니다.'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadMessages = useCallback(
    async (channelId: string, incremental: boolean) => {
      try {
        const after = incremental ? lastIdRef.current : '';
        const payload = await fetchMessages(channelId, after);
        if (!payload.items.length) return;
        setMessages((current) => {
          const next = incremental ? [...current, ...payload.items] : payload.items;
          lastIdRef.current = next.length ? next[next.length - 1].id : '';
          return next.slice(-300);
        });
        window.setTimeout(() => {
          listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
        }, 30);
      } catch {
        /* polling errors are transient */
      }
    },
    [],
  );

  useEffect(() => {
    if (!activeId) return;
    setMessages([]);
    lastIdRef.current = '';
    setSummary('');
    void loadMessages(activeId, false);
    const timer = window.setInterval(() => void loadMessages(activeId, true), POLL_MS);
    return () => window.clearInterval(timer);
  }, [activeId, loadMessages]);

  async function submit() {
    const text = draft.trim();
    if (!text || !activeId) return;
    setDraft('');
    try {
      await sendMessage(activeId, text);
      await loadMessages(activeId, true);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '전송 실패');
    }
  }

  async function addChannel() {
    const name = newChannel.trim();
    if (!name) return;
    try {
      const result = await createChannel(name);
      setChannels(result.items);
      setNewChannel('');
      setActiveId(result.item.id);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '채널 생성 실패');
    }
  }

  async function summarize() {
    if (!activeId) return;
    setSummaryBusy(true);
    try {
      const result = await summarizeChannel(activeId);
      setSummary(result.summary);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '요약 실패');
    } finally {
      setSummaryBusy(false);
    }
  }

  const active = channels.find((channel) => channel.id === activeId);

  return (
    <section className="messenger-layout">
      <aside className="messenger-channels panel">
        <h3>채널</h3>
        <div className="messenger-channel-list">
          {channels.map((channel) => (
            <button
              type="button"
              key={channel.id}
              className={channel.id === activeId ? 'messenger-channel active' : 'messenger-channel'}
              onClick={() => setActiveId(channel.id)}
            >
              # {channel.name}
            </button>
          ))}
        </div>
        <div className="inline-input-row">
          <input
            value={newChannel}
            placeholder="새 채널 이름"
            onChange={(e) => setNewChannel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void addChannel();
            }}
          />
          <Button variant="secondary" onClick={() => void addChannel()}>추가</Button>
        </div>
      </aside>

      <div className="messenger-main panel">
        <div className="messenger-head">
          <div>
            <strong># {active?.name || '채널'}</strong>
            {active?.description ? <span className="muted"> · {active.description}</span> : null}
          </div>
          <Button variant="secondary" disabled={summaryBusy} onClick={() => void summarize()}>
            {summaryBusy ? '요약 중...' : 'AI 요약 (놓친 대화 따라잡기)'}
          </Button>
        </div>
        {summary ? (
          <div className="messenger-summary">
            <pre>{summary}</pre>
            <Button variant="secondary" onClick={() => setSummary('')}>닫기</Button>
          </div>
        ) : null}
        {notice ? <p className="alert">{notice}</p> : null}
        <div className="messenger-messages" ref={listRef}>
          {messages.length ? (
            messages.map((message) => (
              <div
                key={message.id}
                className={message.author_id === user.id ? 'chat-msg mine' : 'chat-msg'}
              >
                <div className="chat-msg-meta">
                  <strong>{message.author_name}</strong>
                  <span>{new Date(message.created_at).toLocaleTimeString()}</span>
                </div>
                <p>{message.text}</p>
              </div>
            ))
          ) : (
            <p className="muted messenger-empty">
              아직 메시지가 없습니다. 첫 메시지를 남겨보세요 — 여기 나눈 대화는 회사 기억에 저장되어
              나중에 "회사에 물어보기"로 찾을 수 있습니다.
            </p>
          )}
        </div>
        <div className="messenger-input">
          <textarea
            value={draft}
            rows={1}
            placeholder={`# ${active?.name || ''} 채널에 메시지 보내기`}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void submit();
              }
            }}
          />
          <Button onClick={() => void submit()}>보내기</Button>
        </div>
      </div>
    </section>
  );
}
