import { getAuthHeaders } from '../auth';
import { requestJson } from './http';
import type {
  UploadRecord,
} from './types';

export function fetchUploads(): Promise<{ uploads: UploadRecord[] }> {
  return requestJson<{ uploads: UploadRecord[] }>('/api/uploads');
}

export async function uploadDocument(formData: FormData): Promise<{ ok: boolean; upload: UploadRecord }> {
  const response = await fetch('/api/uploads', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: formData,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as { ok: boolean; upload: UploadRecord };
}

export function deleteUpload(uploadId: string): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>(`/api/uploads/${uploadId}`, { method: 'DELETE' });
}
