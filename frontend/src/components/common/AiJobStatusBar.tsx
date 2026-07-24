import type { AiJobStatus } from '../../api';

type Props = {
  job: AiJobStatus | null;
  fallbackLabel?: string;
  onOpenResult?: (path: string) => void;
};

const STATUS_LABEL: Record<AiJobStatus['status'], string> = {
  queued: '요청 등록됨',
  running: '처리 중',
  succeeded: '완료',
  failed: '실패',
};

export default function AiJobStatusBar({ job, fallbackLabel = '대기 중', onOpenResult }: Props) {
  if (!job) {
    return (
      <div className="ai-job-status-bar">
        <span className="status-pill">{fallbackLabel}</span>
        <p className="muted small">AI 생성 요청을 보내면 등록/처리/완료 상태가 여기에 표시됩니다.</p>
      </div>
    );
  }

  return (
    <div className="ai-job-status-bar">
      <span className={`status-pill${job.status === 'failed' ? ' warn' : job.status === 'succeeded' ? ' success' : ''}`}>
        {STATUS_LABEL[job.status] || job.status}
      </span>
      <strong>{job.task}</strong>
      <p className="muted small">{job.input_summary || job.job_id}</p>
      {job.result_path ? (
        <button type="button" className="secondary-button" onClick={() => onOpenResult?.(job.result_path)}>
          결과 열람: {job.result_path}
        </button>
      ) : null}
      {job.error ? <span className="status-pill warn">{job.error}</span> : null}
      {job.used_sources.length ? (
        <p className="muted small">사용 source: {job.used_sources.slice(0, 5).join(', ')}</p>
      ) : null}
    </div>
  );
}
