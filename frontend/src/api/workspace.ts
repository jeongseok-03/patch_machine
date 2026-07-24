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
