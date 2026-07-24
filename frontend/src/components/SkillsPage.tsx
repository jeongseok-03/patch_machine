import { ChangeEvent, useEffect, useMemo, useState } from 'react';

import {
  createSkill,
  fetchSkills,
  runSkill,
  type SkillDescriptor,
  type SkillInputSchema,
  type SkillRunResult,
} from '../api';

const emptyDraft = {
  id: '',
  name: '',
  category: 'general',
  description: '',
  required_permission: '',
  instructions: '',
  inputsText: '',
};

type SkillTab = 'catalog' | 'run' | 'create';

function parseInputs(text: string): SkillInputSchema[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const required = line.endsWith('*');
      const name = (required ? line.slice(0, -1) : line).trim();
      return { name, type: 'string', required, description: '' };
    })
    .filter((entry) => entry.name);
}

function slugifySkillId(value: string): string {
  const cleaned = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_.-]+/g, '.')
    .replace(/^\.+|\.+$/g, '');
  return cleaned || 'custom.skill';
}

function parseMarkdownSkill(markdown: string): typeof emptyDraft {
  const raw = markdown.trim();
  const metadata: Record<string, string> = {};
  let body = raw;
  const frontmatter = raw.match(/^---\s*\n([\s\S]*?)\n---\s*\n?/);
  if (frontmatter) {
    body = raw.slice(frontmatter[0].length).trim();
    frontmatter[1].split('\n').forEach((line) => {
      const match = line.match(/^([A-Za-z0-9_.-]+)\s*:\s*(.*)$/);
      if (match) metadata[match[1].trim()] = match[2].trim().replace(/^["']|["']$/g, '');
    });
  }
  const title = metadata.name || metadata.title || body.match(/^#\s+(.+)$/m)?.[1]?.trim() || '새 스킬';
  const description =
    metadata.description ||
    body
      .split('\n')
      .map((line) => line.trim())
      .find((line) => line && !line.startsWith('#')) ||
    '';
  const placeholders = Array.from(body.matchAll(/\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g)).map(
    (match) => match[1],
  );
  const inputNames = Array.from(new Set(placeholders));
  const inputText = metadata.inputs
    ? metadata.inputs
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
        .join('\n')
    : inputNames.join('\n');

  return {
    id: metadata.id || slugifySkillId(title),
    name: title,
    category: metadata.category || 'general',
    description: description.slice(0, 240),
    required_permission: metadata.required_permission || metadata.permission || '',
    instructions: body || raw,
    inputsText: inputText,
  };
}

export default function SkillsPage() {
  const [skills, setSkills] = useState<SkillDescriptor[]>([]);
  const [selected, setSelected] = useState<SkillDescriptor | null>(null);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SkillRunResult | null>(null);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState(emptyDraft);
  const [creating, setCreating] = useState(false);
  const [createMsg, setCreateMsg] = useState('');
  const [activeTab, setActiveTab] = useState<SkillTab>('catalog');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');

  const categories = useMemo(
    () => ['all', ...Array.from(new Set(skills.map((skill) => skill.category || 'general'))).sort()],
    [skills],
  );

  const filteredSkills = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return skills.filter((skill) => {
      const categoryOk = category === 'all' || skill.category === category;
      const queryOk =
        !needle ||
        `${skill.id} ${skill.name} ${skill.description} ${skill.category}`.toLowerCase().includes(needle);
      return categoryOk && queryOk;
    });
  }, [category, query, skills]);

  async function loadSkills() {
    try {
      const data = await fetchSkills();
      setSkills(data.skills);
    } catch (err) {
      setError(err instanceof Error ? err.message : '스킬 목록을 불러오지 못했습니다.');
    }
  }

  useEffect(() => {
    void loadSkills();
  }, []);

  async function handleCreate() {
    if (!draft.id.trim() || !draft.name.trim() || !draft.instructions.trim()) {
      setCreateMsg('ID, 이름, 본문(프롬프트)은 필수입니다.');
      return;
    }
    setCreating(true);
    setCreateMsg('');
    try {
      const res = await createSkill({
        id: draft.id.trim(),
        name: draft.name.trim(),
        description: draft.description.trim(),
        category: draft.category.trim() || 'general',
        executor: 'prompt',
        required_permission: draft.required_permission.trim(),
        instructions: draft.instructions,
        inputs: parseInputs(draft.inputsText),
      });
      setSkills(res.skills);
      setDraft(emptyDraft);
      setCreateMsg(`스킬을 만들었습니다: ${res.skill.id}`);
    } catch (err) {
      setCreateMsg(err instanceof Error ? err.message : '스킬 생성 실패');
    } finally {
      setCreating(false);
    }
  }

  function selectSkill(skill: SkillDescriptor) {
    setSelected(skill);
    setActiveTab('run');
    setResult(null);
    setError('');
    const next: Record<string, string> = {};
    skill.inputs.forEach((input) => {
      next[input.name] = '';
    });
    setInputs(next);
  }

  async function handleMarkdownUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      setDraft(parseMarkdownSkill(text));
      setCreateMsg(`${file.name} 내용을 스킬 생성 폼으로 불러왔습니다. 검토 후 생성하세요.`);
      setActiveTab('create');
    } catch {
      setCreateMsg('skills.md 파일을 읽지 못했습니다.');
    } finally {
      event.target.value = '';
    }
  }

  async function handleRun() {
    if (!selected) return;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const payload: Record<string, unknown> = {};
      Object.entries(inputs).forEach(([key, value]) => {
        if (value !== '') payload[key] = value;
      });
      const res = await runSkill(selected.id, payload);
      setResult(res.result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '스킬 실행 실패');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-workspace">
      <div className="panel">
        <p className="eyebrow">Skills</p>
        <h2>스킬 관리</h2>
        <p className="muted">
          카탈로그 탐색, 실행, 제작을 탭으로 나눴습니다. <code>skills.md</code>를 업로드하면 스킬 생성 폼을 자동으로 채웁니다.
        </p>
        <nav className="skill-tab-nav" aria-label="스킬 화면 이동">
          <button
            type="button"
            className={activeTab === 'catalog' ? 'active' : ''}
            onClick={() => setActiveTab('catalog')}
          >
            카탈로그
          </button>
          <button
            type="button"
            className={activeTab === 'run' ? 'active' : ''}
            onClick={() => setActiveTab('run')}
          >
            실행
          </button>
          <button
            type="button"
            className={activeTab === 'create' ? 'active' : ''}
            onClick={() => setActiveTab('create')}
          >
            제작·업로드
          </button>
        </nav>
      </div>

      {activeTab === 'catalog' ? (
        <div className="panel">
          <p className="eyebrow">Skills</p>
          <h2>스킬 카탈로그</h2>
          <p className="muted">
            시스템 기능을 스킬 단위로 실행합니다. 오토마타(작업 스케줄)의 자동화 단계에서는
            <code> skill:&lt;id&gt; </code>로 연결됩니다.
          </p>
          <div className="skill-filter-bar">
            <input
              value={query}
              placeholder="스킬 이름, ID, 설명 검색"
              onChange={(event) => setQuery(event.target.value)}
            />
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              {categories.map((item) => (
                <option key={item} value={item}>
                  {item === 'all' ? '전체 카테고리' : item}
                </option>
              ))}
            </select>
          </div>
          {skills.length === 0 ? (
            <p className="muted">등록된 스킬이 없습니다.</p>
          ) : (
            <ul className="attachment-list skill-catalog-list">
              {filteredSkills.map((skill) => (
                <li key={skill.id}>
                  <button
                    type="button"
                    className={selected?.id === skill.id ? 'skill-item active' : 'skill-item'}
                    onClick={() => selectSkill(skill)}
                  >
                    <strong>{skill.name}</strong>
                    <span className="muted small">
                      {skill.id} · {skill.executor} · {skill.category} · risk {skill.risk}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}

      {activeTab === 'run' ? (
        <div className="panel">
          <p className="eyebrow">Run</p>
          <h2>스킬 실행</h2>
          {selected ? (
            <>
              <p className="muted">{selected.description}</p>
              <div className="memory-form">
                {selected.inputs.map((input) => (
                  <label key={input.name}>
                    {input.name}
                    {input.required ? ' *' : ''}
                    <input
                      value={inputs[input.name] ?? ''}
                      placeholder={input.description}
                      onChange={(event) =>
                        setInputs((current) => ({ ...current, [input.name]: event.target.value }))
                      }
                    />
                  </label>
                ))}
                <button type="button" disabled={busy} onClick={() => void handleRun()}>
                  {busy ? '실행 중...' : '스킬 실행'}
                </button>
              </div>
              {error ? <p className="error-text small">{error}</p> : null}
              {result ? (
                <div>
                  <p className="muted">
                    상태: {result.status}
                    {result.output_path ? ` · 저장: ${result.output_path}` : ''}
                  </p>
                  <pre className="status-pre">
                    {result.output_text ||
                      JSON.stringify(result.tool_result, null, 2) ||
                      '(출력 없음)'}
                  </pre>
                </div>
              ) : null}
            </>
          ) : (
            <p className="muted">카탈로그에서 스킬을 선택하세요.</p>
          )}
        </div>
      ) : null}

      {activeTab === 'create' ? (
      <div className="panel">
        <p className="eyebrow">Create / Upload</p>
        <h2>스킬 제작·업로드</h2>
        <p className="muted">
          프롬프트형 스킬을 직접 등록합니다. 본문은 Jinja 템플릿이며 <code>{'{{ 입력명 }}'}</code>으로 입력값을 사용합니다.
          작업 스케줄 자동화에서는 <code>skill:&lt;id&gt;</code>로 연결됩니다.
        </p>
        <div className="skill-upload-box">
          <strong>skills.md로 만들기</strong>
          <p className="muted small">
            Markdown 파일을 넣으면 제목, 설명, 프롬프트 본문, <code>{'{{ 입력명 }}'}</code> 변수를 읽어 아래 폼을 채웁니다.
            YAML front matter의 <code>id</code>, <code>category</code>, <code>inputs</code>도 지원합니다.
          </p>
          <label className="file-upload-label compact">
            <span>skills.md 업로드</span>
            <input accept=".md,.markdown,text/markdown,text/plain" type="file" onChange={handleMarkdownUpload} />
          </label>
        </div>
        <div className="memory-form org-form">
          <div className="org-form-row">
            <label>
              스킬 ID
              <input
                placeholder="예: office.weekly_report"
                value={draft.id}
                onChange={(event) => setDraft({ ...draft, id: event.target.value })}
              />
            </label>
            <label>
              이름
              <input
                placeholder="예: 주간 보고서 작성"
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              />
            </label>
          </div>
          <div className="org-form-row">
            <label>
              카테고리
              <input
                placeholder="general"
                value={draft.category}
                onChange={(event) => setDraft({ ...draft, category: event.target.value })}
              />
            </label>
            <label>
              필요 권한 (선택)
              <input
                placeholder="예: documents:write"
                value={draft.required_permission}
                onChange={(event) => setDraft({ ...draft, required_permission: event.target.value })}
              />
            </label>
          </div>
          <label>
            설명
            <input
              placeholder="스킬이 하는 일을 한 줄로 설명"
              value={draft.description}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
            />
          </label>
          <label>
            입력 (한 줄에 하나, 필수는 끝에 * 표시)
            <textarea
              placeholder={'title*\ntopic'}
              value={draft.inputsText}
              onChange={(event) => setDraft({ ...draft, inputsText: event.target.value })}
            />
          </label>
          <label>
            본문 (프롬프트)
            <textarea
              placeholder={'{{ title }} 주제로 보고서를 작성하세요.'}
              value={draft.instructions}
              onChange={(event) => setDraft({ ...draft, instructions: event.target.value })}
            />
          </label>
          <div className="form-actions">
            <button type="button" disabled={creating} onClick={() => void handleCreate()}>
              {creating ? '생성 중...' : '스킬 생성'}
            </button>
          </div>
          {createMsg ? <p className="muted">{createMsg}</p> : null}
        </div>
      </div>
      ) : null}
    </section>
  );
}
