import { type TestRequirement } from '../../api';

type Props = {
  requirements?: TestRequirement[];
  frameworks?: unknown;
  patterns?: unknown;
  testPlan?: unknown;
  testDiffDraft?: unknown;
  testRunPreview?: unknown;
  notes?: unknown;
};

export default function AiTestWriterPanel({
  requirements = [],
  frameworks,
  patterns,
  testPlan,
  testDiffDraft,
  testRunPreview,
  notes,
}: Props) {
  return (
    <section>
      <h3>AI Test Writer</h3>
      <div className="log-list">
        {requirements.map((requirement) => (
          <article className="log-card" key={requirement.id || requirement.title}>
            <strong>{requirement.title}</strong>
            <p>
              Given {requirement.given || '-'} / When {requirement.when || '-'} / Then {requirement.then || '-'}
            </p>
            <small>
              {requirement.requirement_type} · {requirement.priority} · {requirement.status}
            </small>
          </article>
        ))}
        {!requirements.length ? <p className="muted small">분석 후 proposed test requirement가 표시됩니다.</p> : null}
      </div>
      {testPlan ? (
        <details>
          <summary>Test Plan</summary>
          <pre>{JSON.stringify(testPlan, null, 2)}</pre>
        </details>
      ) : null}
      {testDiffDraft ? (
        <details>
          <summary>테스트 코드 변경안</summary>
          <pre>{String(testDiffDraft)}</pre>
        </details>
      ) : null}
      {frameworks ? (
        <details>
          <summary>Detected Frameworks</summary>
          <pre>{JSON.stringify(frameworks, null, 2)}</pre>
        </details>
      ) : null}
      {patterns ? (
        <details>
          <summary>Existing Test Patterns</summary>
          <pre>{JSON.stringify(patterns, null, 2)}</pre>
        </details>
      ) : null}
      {testRunPreview ? (
        <details>
          <summary>Test Runner Preview</summary>
          <pre>{JSON.stringify(testRunPreview, null, 2)}</pre>
        </details>
      ) : null}
      {notes ? (
        <details>
          <summary>Writer Notes</summary>
          <pre>{JSON.stringify(notes, null, 2)}</pre>
        </details>
      ) : null}
    </section>
  );
}
