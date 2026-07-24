import type { OperationsMemory, WorkMemory } from '../../api';

type EditMode = 'permanent' | 'volatile';

type Props = {
  mode: EditMode;
  onModeChange: (mode: EditMode) => void;
  operations: OperationsMemory;
  setOperations: (v: OperationsMemory) => void;
  work: WorkMemory;
  setWork: (v: WorkMemory) => void;
  onSave: () => void | Promise<void>;
  message: string;
};

export default function WorkMemoryEditSection({
  mode,
  onModeChange,
  operations,
  setOperations,
  work,
  setWork,
  onSave,
  message,
}: Props) {
  return (
    <div className="panel memory-edit-panel">
      <p className="eyebrow">메모리 수정</p>
      <h2>네고티움 메모리 편집</h2>
      <div className="segmented-control" role="tablist" aria-label="편집할 메모리 종류">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'permanent'}
          className={mode === 'permanent' ? 'segment active' : 'segment'}
          onClick={() => onModeChange('permanent')}
        >
          네고티움 영구메모리
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'volatile'}
          className={mode === 'volatile' ? 'segment active' : 'segment'}
          onClick={() => onModeChange('volatile')}
        >
          휘발성 작업 메모리
        </button>
      </div>

      {mode === 'permanent' ? (
        <div className="memory-form" role="tabpanel">
          <p className="muted small">
            운영 메모리(회사·조직·정책)입니다. LLM과 에이전트가 참조하는 네고티움 영구메모리입니다.
          </p>
          <input
            placeholder="회사 이름"
            value={operations.company_name}
            onChange={(e) => setOperations({ ...operations, company_name: e.target.value })}
          />
          <textarea
            placeholder="핵심 업무 흐름"
            value={operations.key_workflows}
            onChange={(e) => setOperations({ ...operations, key_workflows: e.target.value })}
          />
          <textarea
            placeholder="민감정보 정책"
            value={operations.sensitive_policy}
            onChange={(e) => setOperations({ ...operations, sensitive_policy: e.target.value })}
          />
        </div>
      ) : (
        <div className="memory-form" role="tabpanel">
          <textarea placeholder="목표" value={work.goals} onChange={(e) => setWork({ ...work, goals: e.target.value })} />
          <textarea
            placeholder="진행 프로젝트"
            value={work.active_projects}
            onChange={(e) => setWork({ ...work, active_projects: e.target.value })}
          />
          <textarea
            placeholder="현재 집중"
            value={work.current_focus}
            onChange={(e) => setWork({ ...work, current_focus: e.target.value })}
          />
          <textarea placeholder="블로커" value={work.blockers} onChange={(e) => setWork({ ...work, blockers: e.target.value })} />
          <textarea
            placeholder="결정사항"
            value={work.decisions}
            onChange={(e) => setWork({ ...work, decisions: e.target.value })}
          />
          <textarea placeholder="리스크" value={work.risks} onChange={(e) => setWork({ ...work, risks: e.target.value })} />
          <textarea
            placeholder="다음 액션"
            value={work.next_actions}
            onChange={(e) => setWork({ ...work, next_actions: e.target.value })}
          />
        </div>
      )}

      <div className="form-actions">
        <button type="button" onClick={() => void onSave()}>
          메모리 저장
        </button>
        {message ? <p className="form-message">{message}</p> : null}
      </div>
    </div>
  );
}
