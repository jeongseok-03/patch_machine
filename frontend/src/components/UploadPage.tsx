import { FormEvent, useEffect, useState } from 'react';

import {
  deleteUpload,
  fetchUploads,
  readArchiveDocument,
  uploadDocument,
  type DocumentRead,
  type UploadRecord,
} from '../api';

const PREVIEWABLE_SUFFIXES = ['.md', '.markdown', '.txt', '.json', '.jsonl', '.yaml', '.yml'];

function isPreviewable(path: string): boolean {
  const lower = path.toLowerCase();
  return PREVIEWABLE_SUFFIXES.some((suffix) => lower.endsWith(suffix));
}

export default function UploadPage() {
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [preview, setPreview] = useState<DocumentRead | null>(null);
  const [previewError, setPreviewError] = useState('');

  async function refresh() {
    setUploads((await fetchUploads()).uploads);
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await uploadDocument(new FormData(event.currentTarget));
    event.currentTarget.reset();
    await refresh();
  }

  async function openPreview(path: string) {
    setPreviewError('');
    try {
      const next = await readArchiveDocument(path);
      setPreview(next);
    } catch (err) {
      setPreview(null);
      setPreviewError(err instanceof Error ? err.message : '문서 열람에 실패했습니다.');
    }
  }

  return (
    <section className="page-grid">
      <div className="panel">
        <p className="eyebrow">Uploads</p>
        <h2>문서 업로드</h2>
        <form className="memory-form" onSubmit={handleSubmit}>
          <input name="file" type="file" required />
          <input name="work_title" placeholder="업무명" />
          <input name="tags" placeholder="태그" />
          <textarea name="description" placeholder="설명" />
          <button type="submit">업로드</button>
        </form>
      </div>
      <div className="panel">
        <p className="eyebrow">Archive</p>
        <h2>업로드 목록</h2>
        {previewError ? <p className="alert" role="alert">{previewError}</p> : null}
        <div className="log-list">
          {uploads.map((upload) => (
            <article className="log-card" key={upload.id}>
              <strong>{upload.filename}</strong>
              <p>{upload.work_title || '업무 미지정'} · {upload.tags || '태그 없음'}</p>
              <small>{upload.path}</small>
              <div className="switch-row">
                {isPreviewable(upload.path) ? (
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => void openPreview(upload.path)}
                  >
                    미리보기
                  </button>
                ) : null}
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => deleteUpload(upload.id).then(refresh)}
                >
                  삭제
                </button>
              </div>
            </article>
          ))}
        </div>
      </div>
      {preview ? (
        <div className="panel">
          <p className="eyebrow">{preview.path}</p>
          <h2>문서 미리보기</h2>
          <p className="muted small">
            {preview.bytes.toLocaleString()} bytes · 수정 {preview.modified_at}
          </p>
          <div className="document-viewer">
            <pre>{preview.markdown}</pre>
          </div>
        </div>
      ) : null}
    </section>
  );
}
