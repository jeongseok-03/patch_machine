import { requestJson } from './http';

export type Announcement = {
  id: string;
  title: string;
  body: string;
  author_id: string;
  author_name: string;
  pinned: boolean;
  created_at: string;
};

export function fetchAnnouncements(): Promise<{ items: Announcement[] }> {
  return requestJson<{ items: Announcement[] }>('/api/workspace/announcements');
}

export function createAnnouncement(payload: {
  title: string;
  body: string;
  pinned?: boolean;
}): Promise<{ ok: boolean; items: Announcement[] }> {
  return requestJson<{ ok: boolean; items: Announcement[] }>('/api/workspace/announcements', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteAnnouncement(id: string): Promise<{ ok: boolean; items: Announcement[] }> {
  return requestJson<{ ok: boolean; items: Announcement[] }>(`/api/workspace/announcements/${id}`, {
    method: 'DELETE',
  });
}

export type ChatChannel = {
  id: string;
  name: string;
  description: string;
  created_by: string;
  created_at: string;
};

export type ChatMessage = {
  id: string;
  channel_id: string;
  author_id: string;
  author_name: string;
  text: string;
  created_at: string;
};

export function fetchChannels(): Promise<{ items: ChatChannel[] }> {
  return requestJson<{ items: ChatChannel[] }>('/api/workspace/channels');
}

export function createChannel(name: string, description = ''): Promise<{ ok: boolean; item: ChatChannel; items: ChatChannel[] }> {
  return requestJson<{ ok: boolean; item: ChatChannel; items: ChatChannel[] }>('/api/workspace/channels', {
    method: 'POST',
    body: JSON.stringify({ name, description }),
  });
}

export function fetchMessages(channelId: string, after = ''): Promise<{ items: ChatMessage[] }> {
  const suffix = after ? `?after=${encodeURIComponent(after)}` : '';
  return requestJson<{ items: ChatMessage[] }>(`/api/workspace/channels/${channelId}/messages${suffix}`);
}

export function sendMessage(channelId: string, text: string): Promise<{ ok: boolean; item: ChatMessage }> {
  return requestJson<{ ok: boolean; item: ChatMessage }>(`/api/workspace/channels/${channelId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}

export function summarizeChannel(channelId: string): Promise<{ summary: string }> {
  return requestJson<{ summary: string }>(`/api/workspace/channels/${channelId}/summary`, {
    method: 'POST',
  });
}

export type MailAccountInfo = {
  configured: boolean;
  email?: string;
  imap_host?: string;
  imap_port?: number;
  smtp_host?: string;
  smtp_port?: number;
  username?: string;
  password?: string;
};

export type MailSummary = {
  uid: string;
  subject: string;
  from: string;
  date: string;
  snippet: string;
};

export type MailDetail = MailSummary & { to: string; body: string };

export type MailTriage = { reply_needed: string[]; fyi: string[]; summary: string };

export function fetchMailAccount(): Promise<MailAccountInfo> {
  return requestJson<MailAccountInfo>('/api/workspace/mail/account');
}

export function saveMailAccount(payload: {
  email: string;
  imap_host: string;
  imap_port: number;
  smtp_host: string;
  smtp_port: number;
  username?: string;
  password: string;
}): Promise<MailAccountInfo> {
  return requestJson<MailAccountInfo>('/api/workspace/mail/account', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function fetchMailInbox(): Promise<{ items: MailSummary[] }> {
  return requestJson<{ items: MailSummary[] }>('/api/workspace/mail/inbox');
}

export function fetchMailMessage(uid: string): Promise<MailDetail> {
  return requestJson<MailDetail>(`/api/workspace/mail/message/${uid}`);
}

export function triageMail(): Promise<MailTriage> {
  return requestJson<MailTriage>('/api/workspace/mail/triage', { method: 'POST' });
}

export function draftMailReply(uid: string): Promise<{ draft: string; to: string; subject: string }> {
  return requestJson<{ draft: string; to: string; subject: string }>('/api/workspace/mail/reply-draft', {
    method: 'POST',
    body: JSON.stringify({ uid }),
  });
}

export function sendMailMessage(payload: { to: string; subject: string; body: string }): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>('/api/workspace/mail/send', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
