"""PermanentMemoryStore.resolve_sources behavior."""

from __future__ import annotations

from pathlib import Path

from negotium.archive.permanent_memory import PermanentMemoryStore


def _write_patch_log(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_resolve_sources_preserves_request_order(tmp_path: Path) -> None:
    archive = tmp_path
    _write_patch_log(archive, "2026/04/first.md", "# First\none")
    _write_patch_log(archive, "2026/04/second.md", "# Second\ntwo")
    store = PermanentMemoryStore(archive)
    first = "2026/04/first.md"
    second = "2026/04/second.md"
    out = store.resolve_sources(query="", limit=10, source_ids=[second, first])
    assert [str(d["path"]) for d in out] == [second, first]


def test_resolve_sources_empty_ids_falls_back_to_search(tmp_path: Path) -> None:
    archive = tmp_path
    _write_patch_log(archive, "2026/04/only.md", "# Only\nneedle here")
    store = PermanentMemoryStore(archive)
    out = store.resolve_sources(query="needle", limit=10, source_ids=None)
    assert len(out) == 1
    assert "needle" in str(out[0]["excerpt"]).lower()


def test_resolve_sources_filters_unknown_ids(tmp_path: Path) -> None:
    archive = tmp_path
    _write_patch_log(archive, "2026/04/x.md", "# X\ncontent")
    store = PermanentMemoryStore(archive)
    out = store.resolve_sources(
        query="",
        limit=10,
        source_ids=["missing.md", "2026/04/x.md"],
    )
    assert len(out) == 1
    assert out[0]["path"] == "2026/04/x.md"
