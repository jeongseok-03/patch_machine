import type { ConversationRecord } from '../../api';

type Props = {
  open: boolean;
  records: ConversationRecord[];
  onClose: () => void;
};

export default function ConversationHistoryModal({ open, records, onClose }: Props) {
  if (!open) return null;

  return (
    <div className="modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="modal-dialog modal-dialog-wide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="conv-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <h2 id="conv-modal-title">대화 기록</h2>
          <button type="button" className="secondary-button" onClick={onClose}>
            닫기
          </button>
        </header>
        <div className="modal-body scroll-y">
          {records.length === 0 ? (
            <p className="muted">저장된 대화가 없습니다.</p>
          ) : (
            <div className="log-list">
              {records.map((record) => (
                <article className="log-card" key={record.id}>
                  <strong>
                    {record.user_id} · {record.role}
                  </strong>
                  <p className="conv-content">{record.content}</p>
                </article>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
