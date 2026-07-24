import {
  approveDeletionRequest,
  rejectDeletionRequest,
  type DeletionRequest,
} from '../../api';

type Props = {
  deletionRequests: DeletionRequest[];
  onRefresh: () => void | Promise<void>;
};

export default function MemoryGovernancePanel({ deletionRequests, onRefresh }: Props) {
  const pendingRequests = deletionRequests.filter((request) => request.status === 'pending');

  return (
    <div className="panel memory-governance-panel">
      <p className="eyebrow">Governance</p>
      <h2>삭제 요청 승인</h2>
      <p className="muted">
        사용자가 요청한 내부 정보 삭제를 검토하고 승인/거절합니다. 승인하면 tombstone 기록과 함께 가능한 원본 source가 즉시 삭제됩니다.
      </p>

      <details className="governance-details" open>
        <summary>삭제 요청 {pendingRequests.length ? `(${pendingRequests.length}건 대기)` : '(대기 없음)'}</summary>
        <div className="log-list">
          {deletionRequests.length === 0 ? <p className="muted small">삭제 요청이 없습니다.</p> : null}
          {deletionRequests.map((request) => (
            <article className="log-card" key={request.id}>
              <strong>{request.summary}</strong>
              <p>
                {request.status} · {request.target_type} · {request.source_path}
              </p>
              <small>요청자 {request.requester || '-'} · 사유 {request.reason || '-'}</small>
              {request.status === 'pending' ? (
                <>
                  <button type="button" onClick={() => void approveDeletionRequest(request.id).then(() => onRefresh())}>
                    삭제 승인
                  </button>
                  <button className="secondary-button" type="button" onClick={() => void rejectDeletionRequest(request.id).then(() => onRefresh())}>
                    거절
                  </button>
                </>
              ) : null}
            </article>
          ))}
        </div>
      </details>
    </div>
  );
}
