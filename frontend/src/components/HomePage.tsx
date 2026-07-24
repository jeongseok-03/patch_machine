import type { ApiStatus, OperationsMemory } from '../api';

export default function HomePage({
  memory,
  status,
  onAction,
}: {
  memory: OperationsMemory;
  status: ApiStatus | null;
  onAction: (page: string) => void;
}) {
  const queue = status ? `${status.queue_size}/${status.queue_capacity}` : '-';
  const memoryState = status?.operations_memory_configured ? '설정 완료' : '초기 상태';
  return (
    <section>
      <div className="hero-panel">
        <p className="eyebrow">AI Office BPA Console</p>
        <h1>회사 업무·문서·채용·인수인계를 AI로 굴리는 사내 콘솔</h1>
        <p className="lede">
          사내 메모리 엔진과 LLM 에이전트가 오피스워크를 자동화합니다. 경영진은 병목을 한눈에 보고,
          직원은 업무 맥락을 AI에게 그대로 물어볼 수 있습니다.
        </p>
      </div>
      <section className="guide-grid">
        <article className="guide-card">
          <p className="eyebrow">네고티움 영구메모리</p>
          <h3>{memory.company_name || '회사 미설정'}</h3>
          <p>{memory.office_project || '오피스 프로젝트와 진행 계획을 등록하면 모든 LLM 응답에 반영됩니다.'}</p>
          <button type="button" onClick={() => onAction('dashboard')}>운영 메모리 설정</button>
        </article>
        <article className="guide-card">
          <p className="eyebrow">시스템 상태</p>
          <h3>큐 {queue} · 메모리 {memoryState}</h3>
          <p>최근 업무 로그와 병목 요약을 업무 현황 페이지에서 확인할 수 있습니다.</p>
          <button type="button" onClick={() => onAction('work')}>업무 현황 보기</button>
        </article>
        <article className="guide-card">
          <p className="eyebrow">관리</p>
          <h3>API 키 · 권한 · 업로드</h3>
          <p>API 키 암호화 보관, 직급/권한, 문서 업로드를 관리자 페이지에서 처리합니다.</p>
          <button type="button" onClick={() => onAction('admin')}>관리 페이지 열기</button>
        </article>
      </section>
    </section>
  );
}
