import type { ApiStatus } from '../api';

type Props = {
  loading: boolean;
  status: ApiStatus | null;
  onRefresh: () => void;
};

export default function SystemStatus({ loading, status, onRefresh }: Props) {
  const metricEntries = Object.entries(status?.metrics ?? {});

  return (
    <section className="panel status-panel">
      <div className="panel-heading">
        <p className="eyebrow">System Status</p>
        <h2>백엔드 상태</h2>
        <p>FastAPI 큐, 메트릭, 네고티움 영구메모리(운영) 설정 여부를 로컬 프론트엔드에서 확인합니다.</p>
      </div>

      <div className="status-list">
        <StatusItem label="API" value={loading ? '확인 중' : status?.ok ? '정상' : '오프라인'} />
        <StatusItem
          label="이벤트 큐"
          value={status ? `${status.queue_size} / ${status.queue_capacity}` : '-'}
        />
        <StatusItem
          label="네고티움 영구메모리"
          value={status?.operations_memory_configured ? '설정됨' : '초기화 상태'}
        />
      </div>

      <div className="metrics-box">
        <h3>Agent Metrics</h3>
        {metricEntries.length > 0 ? (
          <dl>
            {metricEntries.map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{String(value)}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p>아직 기록된 메트릭이 없습니다.</p>
        )}
      </div>

      <button className="secondary-button" type="button" onClick={onRefresh}>
        상태 새로고침
      </button>
    </section>
  );
}

function StatusItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
