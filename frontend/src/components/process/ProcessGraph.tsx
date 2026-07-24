import type { ProcessPlanStep } from '../../api';

type Props = {
  steps: ProcessPlanStep[];
  selectedId: string | null;
  onSelect: (id: string) => void;
};

function statusClass(step: ProcessPlanStep): string {
  if (step.status === 'done') return 'graph-node done';
  if (step.runnable) return 'graph-node runnable';
  if (step.stage_state && step.stage_state.includes('승인')) return 'graph-node gated';
  return 'graph-node waiting';
}

export default function ProcessGraph({ steps, selectedId, onSelect }: Props) {
  if (steps.length === 0) {
    return <p className="muted">단계가 없습니다. 단계를 추가하거나 프로세스 설계를 생성하세요.</p>;
  }

  return (
    <div className="process-graph">
      <div className="graph-flow">
        {steps.map((step, index) => (
          <div className="graph-flow-item" key={step.id}>
            <button
              type="button"
              className={statusClass(step) + (selectedId === step.id ? ' selected' : '')}
              onClick={() => onSelect(step.id)}
            >
              <span className="graph-node-order">{step.queue_order || index + 1}</span>
              <span className="graph-node-title">{step.title}</span>
              <span className="graph-node-state">{step.stage_state || step.status}</span>
            </button>
            {index < steps.length - 1 ? <span className="graph-connector" aria-hidden /> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
