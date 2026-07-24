const cards = [
  {
    title: '버그 리포트',
    body: '재현 단계, 기대 동작, 실제 동작을 GitHub Issue나 Discord 메시지로 남깁니다.',
  },
  {
    title: '패치 검증',
    body: '자동 생성된 Diff에 테스트 결과와 반례를 덧붙여 리뷰 품질을 높입니다.',
  },
  {
    title: '지식 축적',
    body: '처리 과정은 Markdown archive에 저장되어 다음 이슈의 컨텍스트로 재사용됩니다.',
  },
];

export default function ContributorGuide() {
  return (
    <section className="guide-section">
      <div>
        <p className="eyebrow">Open Collaboration</p>
        <h2>외부 참여자가 도울 수 있는 지점</h2>
      </div>

      <div className="guide-grid">
        {cards.map((card) => (
          <article className="guide-card" key={card.title}>
            <h3>{card.title}</h3>
            <p>{card.body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
