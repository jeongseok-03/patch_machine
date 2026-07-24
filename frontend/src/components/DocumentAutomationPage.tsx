import { FormEvent, useEffect, useState } from 'react';

import {
  createOfficeDocument,
  fetchUploads,
  readArchiveDocument,
  uploadDocument,
  type AiJobStatus,
  type GeneratedDocument,
  type OfficeDocumentOutputFormat,
  type OfficeDocumentRequest,
  type ReadableContextBundle,
  type UploadRecord,
} from '../api';
import AiJobStatusBar from './common/AiJobStatusBar';
import ReadableContextWorkbench from './memory/ReadableContextWorkbench';

const emptyDocument: OfficeDocumentRequest = {
  document_type: 'meeting_minutes',
  title: '',
  source_text: '',
  audience: '',
};

const OUTPUT_FORMAT_OPTIONS: { value: OfficeDocumentOutputFormat; label: string }[] = [
  { value: 'auto', label: '자동 (AI가 형식 선택)' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'html', label: 'HTML' },
  { value: 'csv', label: 'CSV' },
  { value: 'json', label: 'JSON' },
  { value: 'text', label: '일반 텍스트' },
];

export default function DocumentAutomationPage() {
  const [draft, setDraft] = useState<OfficeDocumentRequest>(emptyDocument);
  const [result, setResult] = useState<GeneratedDocument | null>(null);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<AiJobStatus | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [query, setQuery] = useState('');
  const [bundle, setBundle] = useState<ReadableContextBundle | null>(null);
  const [outputFormat, setOutputFormat] = useState<OfficeDocumentOutputFormat>('auto');
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [attachmentIds, setAttachmentIds] = useState<string[]>([]);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState('');

  async function refreshUploads() {
    try {
      const data = await fetchUploads();
      setUploads(data.uploads);
    } catch {
      setUploads([]);
    }
  }

  useEffect(() => {
    void refreshUploads();
  }, []);

  function toggleAttachment(id: string) {
    setAttachmentIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    );
  }

  async function handleUpload(file: File) {
    setUploadBusy(true);
    setUploadError('');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('work_title', draft.title || '문서 자동화 첨부');
      form.append('description', '문서 자동화 첨부 파일');
      const res = await uploadDocument(form);
      await refreshUploads();
      setAttachmentIds((current) => [...current, res.upload.id]);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : '업로드 실패');
    } finally {
      setUploadBusy(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setJob({
      job_id: 'local-document-generation',
      task: 'document_generation',
      status: 'queued',
      actor: '',
      input_summary: draft.title,
      used_sources: [],
      result_path: '',
      error: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    try {
      setJob((current) => current ? { ...current, status: 'running', updated_at: new Date().toISOString() } : current);
      const next = await createOfficeDocument({
        ...draft,
        source_ids: selectedIds,
        query,
        source_limit: selectedIds.length || 20,
        include_volatile: false,
        token_budget: 6000,
        attachment_ids: attachmentIds,
        output_format: outputFormat,
      });
      setResult(next);
      setJob(next.ai_job ?? null);
    } catch (err) {
      setJob((current) =>
        current
          ? {
              ...current,
              status: 'failed',
              error: err instanceof Error ? err.message : '문서 생성 실패',
              updated_at: new Date().toISOString(),
            }
          : current,
      );
    } finally {
      setBusy(false);
    }
  }

  async function openResult(path: string) {
    const doc = await readArchiveDocument(path);
    setResult({ title: path, markdown: doc.markdown, path });
  }

  return (
    <section className="page-workspace">
      <div className="workspace-split">
      <div className="panel">
        <p className="eyebrow">Office Docs</p>
        <h2>문서 자동화</h2>
        <p className="muted">회의록, 보고서, 업무 요청서, PPT 초안을 Markdown으로 생성합니다.</p>
        <form className="memory-form" onSubmit={handleSubmit}>
          <label>
            문서 유형
            <select
              value={draft.document_type}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  document_type: event.target.value as OfficeDocumentRequest['document_type'],
                })
              }
            >
              <option value="meeting_minutes">회의록</option>
              <option value="report_draft">보고서 초안</option>
              <option value="work_request">업무 요청서</option>
              <option value="ppt_outline">PPT 초안</option>
            </select>
          </label>
          <label>
            제목
            <input
              value={draft.title}
              placeholder="예: 5월 문서 자동화 도입 보고"
              onChange={(event) => setDraft({ ...draft, title: event.target.value })}
            />
          </label>
          <label>
            대상 독자
            <input
              value={draft.audience}
              placeholder="예: 대표, 관리팀, 신규 담당자"
              onChange={(event) => setDraft({ ...draft, audience: event.target.value })}
            />
          </label>
          <label>
            원문/메모
            <textarea
              value={draft.source_text}
              placeholder="회의 내용, 보고할 사실, 업무 요청 배경을 붙여넣으세요."
              onChange={(event) => setDraft({ ...draft, source_text: event.target.value })}
            />
          </label>
          <label>
            출력 형식
            <select
              value={outputFormat}
              onChange={(event) =>
                setOutputFormat(event.target.value as OfficeDocumentOutputFormat)
              }
            >
              {OUTPUT_FORMAT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button disabled={busy} type="submit">{busy ? '생성 중...' : '문서 생성'}</button>
        </form>
        <AiJobStatusBar job={job} onOpenResult={(path) => void openResult(path)} />
      </div>
      <div className="panel">
        <p className="eyebrow">Generated</p>
        <h2>문서 결과</h2>
        {result ? (
          <>
            <p className="muted">
              저장 위치: {result.path}
              {result.output_format ? ` · 형식: ${result.output_format}` : ''}
            </p>
            {result.attachment_notes && result.attachment_notes.length > 0 ? (
              <ul className="muted small">
                {result.attachment_notes.map((note, index) => (
                  <li key={index}>{note}</li>
                ))}
              </ul>
            ) : null}
            <pre className="status-pre">{result.markdown}</pre>
          </>
        ) : (
          <p className="muted">아직 생성된 문서가 없습니다.</p>
        )}
      </div>
      </div>
      <details className="advanced-panel">
        <summary>파일 첨부 (이미지 / PDF / txt / md / 표)</summary>
        <p className="muted small">
          파일을 올리면 AI 모델이 직접 읽습니다. 이미지/PDF는 텍스트로 추출하거나, 비전 모델이 설정된
          경우 이미지를 그대로 전달합니다.
        </p>
        <label className="file-upload-label">
          파일 업로드
          <input
            type="file"
            disabled={uploadBusy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) {
                void handleUpload(file);
                event.target.value = '';
              }
            }}
          />
        </label>
        {uploadBusy ? <p className="muted small">업로드 중...</p> : null}
        {uploadError ? <p className="error-text small">{uploadError}</p> : null}
        {uploads.length === 0 ? (
          <p className="muted small">업로드된 파일이 없습니다.</p>
        ) : (
          <ul className="attachment-list">
            {uploads.map((upload) => (
              <li key={upload.id}>
                <label>
                  <input
                    type="checkbox"
                    checked={attachmentIds.includes(upload.id)}
                    onChange={() => toggleAttachment(upload.id)}
                  />
                  {upload.filename}
                  {upload.work_title ? <span className="muted small"> · {upload.work_title}</span> : null}
                </label>
              </li>
            ))}
          </ul>
        )}
      </details>
      <details className="advanced-panel">
        <summary>AI가 읽을 내부 정보 선택</summary>
        <p className="muted small">
          선택한 메모리/문서/패치 기록은 문서 생성 프롬프트에 서버에서 다시 조립되어 들어갑니다.
          {bundle ? ` 현재 미리보기: ${bundle.used_sources.length}개 source, 약 ${bundle.estimated_tokens.toLocaleString()} tokens` : ''}
        </p>
        <ReadableContextWorkbench
          query={query}
          onQueryChange={setQuery}
          selectedIds={selectedIds}
          onSelectedIdsChange={setSelectedIds}
          onBundlePreview={setBundle}
        />
      </details>
    </section>
  );
}
