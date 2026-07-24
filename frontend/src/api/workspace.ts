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
