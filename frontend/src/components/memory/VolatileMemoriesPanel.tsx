import { deleteVolatileMemory, type VolatileMemory } from '../../api';

type Props = {
  memories: VolatileMemory[];
  onAfterChange: () => void | Promise<void>;
};

export default function VolatileMemoriesPanel({ memories, onAfterChange }: Props) {
  return (
    <div className="panel volatile-cache-panel">
      <p className="eyebrow">Volatile cache</p>
      <h2>휘발성 메모리 캐시</h2>
      <p className="muted small">갱신·압축은 위 패널에서 실행합니다. 여기서는 캐시된 항목을 확인·삭제합니다.</p>
      <div className="log-list">
        {memories.map((memory) => (
          <article className="log-card" key={`${memory.scope}-${memory.key}`}>
            <strong>
              {memory.scope}:{memory.key}
            </strong>
            <p>{memory.summary || '요약 없음'}</p>
            <button
              className="secondary-button"
              type="button"
              onClick={() => void deleteVolatileMemory(memory.scope, memory.key).then(() => onAfterChange())}
            >
              캐시 삭제
            </button>
          </article>
        ))}
      </div>
    </div>
  );
}
