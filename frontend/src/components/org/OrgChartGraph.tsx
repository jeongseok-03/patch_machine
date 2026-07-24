import type { DepartmentRecord, UserRecord } from '../../api';

type Props = {
  departments: DepartmentRecord[];
  users: UserRecord[];
  selectedId?: string;
  onSelect?: (id: string) => void;
};

type OrgNode = DepartmentRecord & { children: OrgNode[] };

function buildForest(departments: DepartmentRecord[]): OrgNode[] {
  const nodes = new Map<string, OrgNode>();
  departments.forEach((dept) => nodes.set(dept.id, { ...dept, children: [] }));
  const roots: OrgNode[] = [];
  nodes.forEach((node) => {
    const parentId = node.parent_id ?? '';
    const parent = parentId && parentId !== node.id ? nodes.get(parentId) : undefined;
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  });
  // Defensive: if a cycle hid every node, fall back to a flat layout.
  if (roots.length === 0 && departments.length > 0) {
    return departments.map((dept) => ({ ...dept, children: [] }));
  }
  return roots;
}

export default function OrgChartGraph({ departments, users, selectedId, onSelect }: Props) {
  if (departments.length === 0) {
    return <p className="muted">등록된 부서가 없습니다. 왼쪽에서 부서를 추가하면 조직도가 그려집니다.</p>;
  }

  function leadName(id?: string): string {
    if (!id) return '';
    return users.find((entry) => entry.id === id)?.display_name ?? id;
  }

  function renderNode(node: OrgNode) {
    const memberCount = users.filter((person) => person.department === node.id).length;
    const lead = leadName(node.lead_user_id);
    return (
      <li key={node.id}>
        <button
          type="button"
          className={'org-node' + (selectedId === node.id ? ' selected' : '')}
          onClick={() => onSelect?.(node.id)}
        >
          <span className="org-node-title">{node.name}</span>
          <span className="org-node-meta">
            {lead ? `리드 ${lead} · ` : ''}
            {memberCount}명
          </span>
        </button>
        {node.children.length ? <ul>{node.children.map(renderNode)}</ul> : null}
      </li>
    );
  }

  return (
    <div className="org-chart">
      <ul>{buildForest(departments).map(renderNode)}</ul>
    </div>
  );
}
