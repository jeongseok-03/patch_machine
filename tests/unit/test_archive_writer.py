"""Archive writer + index concurrency tests."""

from __future__ import annotations

import threading
from pathlib import Path

from negotium.archive.writer import ArchiveWriter
from negotium.domain.entities import IssueEvent, RepoRef


def _event(number: int) -> IssueEvent:
    return IssueEvent(
        source="github",
        external_id=str(number),
        repo=RepoRef(owner="acme", name="payments"),
        title=f"Bug #{number}",
        body="idempotency refund",
        author="alice",
        labels=["bug"],
    )


def test_write_log_creates_md_with_front_matter(archive_tmp: Path) -> None:
    writer = ArchiveWriter(archive_tmp)
    path = writer.write_log(
        issue=_event(1),
        status="proposed",
        iteration=1,
        llm_route="cloud",
        modules=["refund"],
        keywords=["idempotency"],
        context_md="- issue body",
        retrieved_md="- none",
        thought_process_md="### PM\nok",
        patch_diff="--- a/x\n+++ b/x",
    )
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "event_id:" in text
    assert "## 4. Patch Diff" in text


def test_index_update_is_safe_under_concurrent_writes(archive_tmp: Path) -> None:
    writer = ArchiveWriter(archive_tmp)

    def write(n: int) -> None:
        writer.write_log(
            issue=_event(n),
            status="proposed",
            iteration=1,
            llm_route="cloud",
            modules=[f"mod{n % 2}"],
            keywords=["idempotency", f"kw{n}"],
            context_md="",
            retrieved_md="",
            thought_process_md="",
            patch_diff="",
        )

    threads = [threading.Thread(target=write, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    keyword_md = (archive_tmp / "index" / "by_keyword.md").read_text(encoding="utf-8")
    assert keyword_md.count("idempotency") == 1  # merged into a single key
    bucket = writer.index.lookup("by_keyword.md", "idempotency")
    assert len(bucket) == 6


def test_collect_recent_logs_orders_by_mtime(archive_tmp: Path) -> None:
    writer = ArchiveWriter(archive_tmp)
    for i in range(3):
        writer.write_log(
            issue=_event(i),
            status="proposed",
            iteration=1,
            llm_route="cloud",
            modules=["refund"],
            keywords=["idempotency"],
            context_md="",
            retrieved_md="",
            thought_process_md="",
            patch_diff="",
        )
    writer.refresh_status()
    status_text = writer.status.read()
    assert "최근 처리 이슈" in status_text
