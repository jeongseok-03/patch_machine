"""Tests for the announcements store."""

from __future__ import annotations

from pathlib import Path

from negotium.archive.announcements import AnnouncementStore


def test_announcements_create_list_delete(tmp_path: Path) -> None:
    store = AnnouncementStore(tmp_path)
    first = store.create(title="첫 공지", body="본문", author_id="admin", author_name="관리자")
    store.create(title="둘째 공지", body="", author_id="admin", author_name="관리자")
    pinned = store.create(
        title="고정 공지", body="중요", author_id="admin", author_name="관리자", pinned=True
    )
    items = store.list()
    assert [item["title"] for item in items][:2] == ["고정 공지", "둘째 공지"]
    assert pinned["pinned"] is True
    assert store.delete(first["id"]) is True
    assert store.delete("no-such") is False
    assert len(store.list()) == 2
