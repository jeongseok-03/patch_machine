import { useEffect, useMemo, useState } from 'react';

import { fetchProgress, type ProgressPayload } from '../api';

export default function ProgressLogPage() {
  const [progress, setProgress] = useState<ProgressPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('all');

  const statusCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const log of progress?.recent_logs ?? []) {
      const status = log.status || 'unknown';
      counts.set(status, (counts.get(status) ?? 0) + 1);
    }
    return counts;
  }, [progress]);

  const filteredLogs = useMemo(() => {
    const logs = progress?.recent_logs ?? [];
    if (statusFilter === 'all') return logs;
    return logs.filter((log) => (log.status || 'unknown') === statusFilter);
  }, [progress, statusFilter]);

  async function refresh() {
    try {
      setProgress(await fetchProgress());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '진행 로그 로드 실패');
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <section className="page-workspace">
      <div className="workspace-hero">
        <div className="panel">
          <p className="eyebrow">Progress</p>
          <h2>진행 로그</h2>
          <p className="muted">현재 상태는 bounded preview로 묶고, 최근 처리 로그는 상태 필터와 compact 카드로 확인합니다.</p>
          <button className="secondary-button" type="button" onClick={() => void refresh()}>
            새로고침
          </button>
          {error ? <p className="alert">{error}</p> : null}
        </div>
        <div className="compact-stat-strip">
          <div className="compact-stat">
            <strong>{progress?.queue_size ?? 0}</strong>
            <span>Queue size</span>
          </div>
          <div className="compact-stat">
            <strong>{progress?.queue_capacity ?? 0}</strong>
            <span>Capacity</span>
          </div>
          <div className="compact-stat">
            <strong>{progress?.recent_logs.length ?? 0}</strong>
            <span>Recent logs</span>
          </div>
        </div>
      </div>

      <div className="workspace-split">
        <div className="panel workspace-sidebar">
          <div className="sticky-panel-header">
            <p className="eyebrow">Status</p>
            <h2>현재 상태</h2>
          </div>
          <div className="bounded-preview">
            <pre>{progress?.current_status_md ?? '로딩 중...'}</pre>
          </div>
        </div>

        <div className="panel workspace-detail">
          <div className="sticky-panel-header">
            <p className="eyebrow">Archive</p>
            <h2>최근 처리 로그</h2>
            <div className="workspace-tabs" aria-label="Progress status filters">
              <button
                type="button"
                className={statusFilter === 'all' ? 'workspace-tab active' : 'workspace-tab'}
                onClick={() => setStatusFilter('all')}
              >
                전체 {progress?.recent_logs.length ?? 0}
              </button>
              {[...statusCounts.entries()].map(([status, count]) => (
                <button
                  type="button"
                  key={status}
                  className={statusFilter === status ? 'workspace-tab active' : 'workspace-tab'}
                  onClick={() => setStatusFilter(status)}
                >
                  {status} {count}
                </button>
              ))}
            </div>
          </div>
          <div className="compact-card-list bounded-list">
            {filteredLogs.map((log) => (
              <article className="log-card" key={log.path}>
                <strong>{log.title}</strong>
                <p>
                  {log.repo || 'unknown repo'} · {log.status || 'unknown'} · {log.llm_route || 'route -'}
                </p>
                <small>{log.path}</small>
              </article>
            ))}
            {!filteredLogs.length ? <p className="muted small">표시할 최근 처리 로그가 없습니다.</p> : null}
          </div>
        </div>
      </div>
    </section>
  );
}
