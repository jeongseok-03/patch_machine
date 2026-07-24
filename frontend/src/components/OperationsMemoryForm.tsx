import { FormEvent, useEffect, useState } from 'react';

import { saveOperationsMemory, type OperationsMemory } from '../api';

type Props = {
  disabled: boolean;
  memory: OperationsMemory;
  onSaved: (memory: OperationsMemory) => void;
};

export default function OperationsMemoryForm({ disabled, memory, onSaved }: Props) {
  const [draft, setDraft] = useState<OperationsMemory>(memory);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setDraft(memory);
  }, [memory]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const saved = await saveOperationsMemory(draft);
      onSaved(saved);
      setMessage('네고티움 영구메모리를 저장했습니다.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '저장 중 오류가 발생했습니다.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel memory-panel">
      <div className="panel-heading">
        <p className="eyebrow">Operations Memory</p>
        <h2>네고티움 영구메모리 (대시보드)</h2>
        <p>
          회사 이름, 진행 계획, 핵심 업무 흐름, 사용 도구, 민감정보 정책을 저장합니다. 이 설정은 채용,
          인수인계, 문서 자동화, LLM 채팅의 기본 컨텍스트가 됩니다. 조직 구조(부서·직급·직원 배정)는
          인사관리 화면에서 별도로 관리합니다.
        </p>
      </div>

      <form className="memory-form" onSubmit={handleSubmit}>
        <label>
          회사 이름
          <input
            disabled={disabled || saving}
            value={draft.company_name}
            placeholder="예: Acme Retail"
            onChange={(event) => setDraft({ ...draft, company_name: event.target.value })}
          />
        </label>

        <label>
          오피스 프로젝트
          <input
            disabled={disabled || saving}
            value={draft.office_project}
            placeholder="예: 결제/환불 운영 자동화"
            onChange={(event) => setDraft({ ...draft, office_project: event.target.value })}
          />
        </label>

        <label>
          진행 중인 계획
          <textarea
            disabled={disabled || saving}
            value={draft.active_plan}
            placeholder="예: 이번 달은 고객 환불 중복 처리와 운영 로그 정리를 우선한다."
            onChange={(event) => setDraft({ ...draft, active_plan: event.target.value })}
          />
        </label>

        <label>
          핵심 업무 흐름
          <textarea
            disabled={disabled || saving}
            value={draft.key_workflows}
            placeholder="예: Discord 문서 접수 → 분류 → 담당자 지정 → 결과 보고"
            onChange={(event) => setDraft({ ...draft, key_workflows: event.target.value })}
          />
        </label>

        <label>
          사용 도구
          <textarea
            disabled={disabled || saving}
            value={draft.office_tools}
            placeholder="예: Discord, GitHub, Notion, Excel, PPT"
            onChange={(event) => setDraft({ ...draft, office_tools: event.target.value })}
          />
        </label>

        <label>
          민감정보 정책
          <textarea
            disabled={disabled || saving}
            value={draft.sensitive_policy}
            placeholder="예: 고객 정보와 내부 문서는 로컬 LLM만 사용, 외부 API 전송 금지"
            onChange={(event) => setDraft({ ...draft, sensitive_policy: event.target.value })}
          />
        </label>

        <div className="form-actions">
          <button disabled={disabled || saving} type="submit">
            {saving ? '저장 중...' : '네고티움 영구메모리 저장'}
          </button>
          {message ? <span className="form-message">{message}</span> : null}
        </div>
      </form>
    </section>
  );
}
