import { useCallback, useEffect, useRef, useState } from 'react';

import {
  createChannel,
  deleteChatMessage,
  fetchChannels,
  fetchMessages,
  reactToMessage,
  sendMessage,
  summarizeChannel,
  type AuthUser,
  type ChatChannel,
  type ChatMessage,
} from '../api';
import Button from './common/Button';

const POLL_MS = 1500;
const QUICK_REACTIONS = ['👍', '❤️', '✅', '😂'];
const AVATAR_HUES = [212, 262, 152, 24, 330, 190, 92, 4];
const LAST_READ_KEY = 'ng-chat-last-read';

function avatarStyle(authorId: string) {
  let hash = 0;
  for (const ch of authorId) hash = (hash * 31 + ch.charCodeAt(0)) & 0xffff;
  const hue = AVATAR_HUES[hash % AVATAR_HUES.length];
  return { background: `hsl(${hue} 45% 42%)` };
}

function initials(name: string) {
  return name.trim().slice(0, 2) || '?';
}

function dayLabel(iso: string) {
  const date = new Date(iso);
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  if (sameDay) return '오늘';
  const yesterday = new Date(today.getTime() - 86_400_000);
  if (date.toDateString() === yesterday.toDateString()) return '어제';
  return date.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' });
}

function loadLastRead(): Record<string, string> {
  try {
    return JSON.parse(window.localStorage.getItem(LAST_READ_KEY) || '{}');
  } catch {
    return {};
  }
}

export default function MessengerPage({ user }: { user: AuthUser }) {
  const [channels, setChannels] = useState<ChatChannel[]>([]);
  const [activeId, setActiveId] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [newChannel, setNewChannel] = useState('');
  const [summary, setSummary] = useState('');
  const [summaryBusy, setSummaryBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [lastRead, setLastRead] = useState<Record<string, string>>(loadLastRead);
  const listRef = useRef<HTMLDivElement | null>(null);
  const stickToBottom = useRef(true);

  const markRead = useCallback((channelId: string, at: string) => {
    setLastRead((current) => {
      if (!at || (current[channelId] || '') >= at) return current;
      const next = { ...current, [channelId]: at };
      window.localStorage.setItem(LAST_READ_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const refreshChannels = useCallback(async () => {
    try {
      const payload = await fetchChannels();
      setChannels(payload.items);
      setActiveId((current) => current || payload.items[0]?.id || '');
    } catch {
      setNotice('채널을 불러오지 못했습니다.');
    }
  }, []);

  useEffect(() => {
    void refreshChannels();
    const timer = window.setInterval(() => void refreshChannels(), 8000);
    return () => window.clearInterval(timer);
  }, [refreshChannels]);

  const loadMessages = useCallback(async (channelId: string) => {
    try {
      const payload = await fetchMessages(channelId);
      setMessages((current) => {
        const pending = current.filter(
          (message) => message.pending && !payload.items.some((item) => item.text === message.text && item.author_id === message.author_id),
        );
        return [...payload.items, ...pending];
      });
      const last = payload.items[payload.items.length - 1];
      if (last) markRead(channelId, last.created_at);
    } catch {
      /* transient */
    }
  }, [markRead]);

  useEffect(() => {
    if (!activeId) return;
    setMessages([]);
    setSummary('');
    stickToBottom.current = true;
    void loadMessages(activeId);
    const timer = window.setInterval(() => void loadMessages(activeId), POLL_MS);
    return () => window.clearInterval(timer);
  }, [activeId, loadMessages]);

  useEffect(() => {
    if (stickToBottom.current && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  function onScroll() {
    const el = listRef.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  }

  async function submit() {
    const text = draft.trim();
    if (!text || !activeId) return;
    setDraft('');
    stickToBottom.current = true;
    const optimistic: ChatMessage = {
      id: `pending-${Date.now()}`,
      channel_id: activeId,
      author_id: user.id,
      author_name: user.display_name,
      text,
      created_at: new Date().toISOString(),
      reactions: {},
      pending: true,
    };
    setMessages((current) => [...current, optimistic]);
    try {
      await sendMessage(activeId, text);
      await loadMessages(activeId);
    } catch (err) {
      setMessages((current) => current.filter((message) => message.id !== optimistic.id));
      setDraft(text);
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

  async function react(messageId: string, emoji: string) {
    if (!activeId) return;
    try {
      await reactToMessage(activeId, messageId, emoji);
      await loadMessages(activeId);
    } catch {
      /* ignore */
    }
  }

  async function remove(messageId: string) {
    if (!activeId) return;
    try {
      await deleteChatMessage(activeId, messageId);
      setMessages((current) => current.filter((message) => message.id !== messageId));
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '삭제 실패');
    }
  }

  const active = channels.find((channel) => channel.id === activeId);

  const rows: Array<
    | { kind: 'divider'; label: string; key: string }
    | { kind: 'message'; message: ChatMessage; grouped: boolean; key: string }
  > = [];
  let prev: ChatMessage | null = null;
  for (const message of messages) {
    const day = new Date(message.created_at).toDateString();
    if (!prev || new Date(prev.created_at).toDateString() !== day) {
      rows.push({ kind: 'divider', label: dayLabel(message.created_at), key: `d-${day}` });
    }
    const grouped =
      !!prev &&
      prev.author_id === message.author_id &&
      new Date(prev.created_at).toDateString() === day &&
      new Date(message.created_at).getTime() - new Date(prev.created_at).getTime() < 5 * 60_000;
    rows.push({ kind: 'message', message, grouped, key: message.id });
    prev = message;
  }

  return (
    <section className="messenger-layout">
      <aside className="messenger-channels panel">
        <h3>채널</h3>
        <div className="messenger-channel-list">
          {channels.map((channel) => {
            const unread =
              channel.id !== activeId &&
              !!channel.last_message_at &&
              (lastRead[channel.id] || '') < channel.last_message_at;
            return (
              <button
                type="button"
                key={channel.id}
                className={channel.id === activeId ? 'messenger-channel active' : 'messenger-channel'}
                onClick={() => setActiveId(channel.id)}
              >
                <span># {channel.name}</span>
                {unread ? <span className="unread-dot" aria-label="안 읽음" /> : null}
              </button>
            );
          })}
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
            {summaryBusy ? '요약 중...' : 'AI 요약'}
          </Button>
        </div>
        {summary ? (
          <div className="messenger-summary">
            <pre>{summary}</pre>
            <Button variant="secondary" onClick={() => setSummary('')}>닫기</Button>
          </div>
        ) : null}
        {notice ? <p className="alert">{notice}</p> : null}
        <div className="messenger-messages" ref={listRef} onScroll={onScroll}>
          {rows.length ? (
            rows.map((row) =>
              row.kind === 'divider' ? (
                <div className="chat-divider" key={row.key}>
                  <span>{row.label}</span>
                </div>
              ) : (
                <div
                  key={row.key}
                  className={[
                    'chat-line',
                    row.grouped ? 'grouped' : '',
                    row.message.pending ? 'pending' : '',
                  ].join(' ')}
                >
                  <div className="chat-avatar-slot">
                    {!row.grouped ? (
                      <span className="chat-avatar" style={avatarStyle(row.message.author_id)}>
                        {initials(row.message.author_name)}
                      </span>
                    ) : null}
                  </div>
                  <div className="chat-content">
                    {!row.grouped ? (
                      <div className="chat-msg-meta">
                        <strong>{row.message.author_name}</strong>
                        <span>
                          {new Date(row.message.created_at).toLocaleTimeString('ko-KR', {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      </div>
                    ) : null}
                    <p>{row.message.text}</p>
                    {Object.keys(row.message.reactions || {}).length ? (
                      <div className="chat-reactions">
                        {Object.entries(row.message.reactions || {}).map(([emoji, users]) => (
                          <button
                            type="button"
                            key={emoji}
                            className={users.includes(user.id) ? 'chat-reaction mine' : 'chat-reaction'}
                            onClick={() => void react(row.message.id, emoji)}
                          >
                            {emoji} {users.length}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  {!row.message.pending ? (
                    <div className="chat-hover-actions">
                      {QUICK_REACTIONS.map((emoji) => (
                        <button type="button" key={emoji} onClick={() => void react(row.message.id, emoji)}>
                          {emoji}
                        </button>
                      ))}
                      {row.message.author_id === user.id ? (
                        <button type="button" onClick={() => void remove(row.message.id)}>삭제</button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ),
            )
          ) : (
            <p className="muted messenger-empty">
              아직 메시지가 없습니다. 여기 나눈 대화는 회사 기억에 저장되어 "회사에 물어보기"로 찾을 수
              있습니다.
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
