import { FormEvent, useState } from 'react';

import { searchIssueMemory, type IssueCluster } from '../../api';

type Props = {
  initialQuery?: string;
  clusters?: IssueCluster[];
  onMessage?: (message: string) => void;
};

export default function IssueMemoryPanel({ initialQuery = '', clusters, onMessage }: Props) {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<IssueCluster[]>(clusters ?? []);
  const [busy, setBusy] = useState(false);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      const payload = await searchIssueMemory(query, 8);
      setResults(payload.clusters);
    } catch (err) {
      onMessage?.(err instanceof Error ? err.message : 'Issue Memory 검색 실패');
    } finally {
      setBusy(false);
    }
  }

  const visible = clusters ?? results;

  return (
    <section>
      <h3>Issue Memory</h3>
      {!clusters ? (
        <form className="inline-form" onSubmit={handleSearch}>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="issue, repo, feature 검색" />
          <button type="submit" disabled={busy}>
            {busy ? '검색 중...' : '검색'}
          </button>
        </form>
      ) : null}
      <div className="log-list">
        {visible.map((cluster) => (
          <article className="log-card" key={cluster.id}>
            <strong>{cluster.title}</strong>
            <p>{cluster.summary || '요약 없음'}</p>
            <small>
              {cluster.status} · severity {cluster.severity} · issues {cluster.canonical_issue_ids?.length ?? 0}
            </small>
          </article>
        ))}
        {!visible.length ? <p className="muted small">아직 관련 issue cluster가 없습니다.</p> : null}
      </div>
    </section>
  );
}
