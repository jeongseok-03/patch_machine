import { useState } from 'react';

type Props = {
  ids: string[];
  idToLabel: Record<string, string>;
  onReorder: (next: string[]) => void;
};

/** Draggable order for selected permanent source ids (compression priority). */
export default function SortableSourceOrder({ ids, idToLabel, onReorder }: Props) {
  const [draggingId, setDraggingId] = useState<string | null>(null);

  function moveById(activeId: string, overId: string) {
    if (activeId === overId) return;
    const oldIndex = ids.indexOf(activeId);
    const newIndex = ids.indexOf(overId);
    if (oldIndex < 0 || newIndex < 0) return;
    const next = [...ids];
    const [moved] = next.splice(oldIndex, 1);
    next.splice(newIndex, 0, moved);
    onReorder(next);
  }

  if (ids.length === 0) return null;

  return (
    <div className="compress-order-block">
      <p className="muted small">압축 우선순위 (드래그로 순서 변경)</p>
      <div className="compress-order-list">
        {ids.map((id, index) => (
          <div
            key={id}
            className={`compress-order-row${draggingId === id ? ' compress-order-row-dragging' : ''}`}
            draggable
            onDragStart={(event) => {
              setDraggingId(id);
              event.dataTransfer.effectAllowed = 'move';
              event.dataTransfer.setData('text/plain', id);
            }}
            onDragOver={(event) => {
              event.preventDefault();
              event.dataTransfer.dropEffect = 'move';
            }}
            onDrop={(event) => {
              event.preventDefault();
              const activeId = event.dataTransfer.getData('text/plain') || draggingId;
              if (activeId) moveById(activeId, id);
              setDraggingId(null);
            }}
            onDragEnd={() => setDraggingId(null)}
          >
            <span className="drag-handle" aria-hidden>
              ::
            </span>
            <span className="compress-order-label">{idToLabel[id] || id}</span>
            <span className="muted small">#{index + 1}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
