"""Two-stage retriever over the MD archive.

Stage 1: narrow candidates using the Index MD files (O(#keywords)).
Stage 2: BM25 rerank the candidate bodies so the best logs bubble up.
"""

from __future__ import annotations

import re
from pathlib import Path

from negotium.archive.index import IndexManager
from negotium.domain.entities import IssueEvent
from negotium.observability import get_logger

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return [tok.lower() for tok in _TOKEN_RE.findall(text) if len(tok) > 2]


class MarkdownRetriever:
    """Combines the Index MD shortcut with a BM25 body rerank."""

    def __init__(
        self,
        *,
        archive_root: Path,
        index: IndexManager,
        bm25_top_k: int = 5,
        candidate_limit: int = 20,
    ) -> None:
        self._archive_root = archive_root
        self._index = index
        self._top_k = bm25_top_k
        self._candidate_limit = candidate_limit
        self._log = get_logger(component="context.md_retriever")

    def find_related(self, event: IssueEvent, *, limit: int | None = None) -> list[Path]:
        query_tokens = _tokenize(f"{event.title} {event.body} {' '.join(event.labels)}")
        if not query_tokens:
            return []
        keyword_hits = self._index.lookup_many(self._index.by_keyword.name, keys=query_tokens)
        module_hits = self._index.lookup_many(self._index.by_module.name, keys=query_tokens)
        candidates = self._collect_candidates(keyword_hits + module_hits)
        if not candidates:
            return []
        ranked = self._bm25_rank(query_tokens, candidates)
        top = ranked[: (limit or self._top_k)]
        return [path for path, _score in top]

    def _collect_candidates(self, relative_paths: list[str]) -> list[Path]:
        seen: dict[Path, None] = {}
        for rel in relative_paths:
            path = self._archive_root / rel
            if path.exists() and path.is_file():
                seen.setdefault(path, None)
            if len(seen) >= self._candidate_limit:
                break
        return list(seen.keys())

    def _bm25_rank(
        self,
        query_tokens: list[str],
        candidates: list[Path],
    ) -> list[tuple[Path, float]]:
        try:
            from rank_bm25 import BM25Okapi
        except Exception:
            self._log.warning("md_retriever.bm25_unavailable")
            return [(p, 0.0) for p in candidates]
        corpus: list[list[str]] = []
        for path in candidates:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = ""
            corpus.append(_tokenize(text))
        if not any(corpus):
            return [(p, 0.0) for p in candidates]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(query_tokens)
        ranked = sorted(
            zip(candidates, scores, strict=True), key=lambda pair: pair[1], reverse=True
        )
        return [(path, float(score)) for path, score in ranked]
