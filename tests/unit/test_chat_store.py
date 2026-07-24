"""Tests for the built-in messenger store."""

from __future__ import annotations

from pathlib import Path

import pytest

from negotium.archive.chat_store import ChatStore


def test_default_channels_created(tmp_path: Path) -> None:
    store = ChatStore(tmp_path)
    channels = store.list_channels()
    assert [c["name"] for c in channels] == ["전체", "업무"]
    # idempotent
    assert len(store.list_channels()) == 2


def test_channel_create_and_duplicate(tmp_path: Path) -> None:
    store = ChatStore(tmp_path)
    record = store.create_channel(name="생산팀", description="", created_by="admin")
    assert store.channel_exists(record["id"])
    with pytest.raises(ValueError):
        store.create_channel(name="생산팀", description="", created_by="admin")


def test_messages_append_list_after(tmp_path: Path) -> None:
    store = ChatStore(tmp_path)
    channel = store.list_channels()[0]
    first = store.append_message(channel["id"], author_id="a", author_name="A", text="안녕하세요")
    store.append_message(channel["id"], author_id="b", author_name="B", text="단가 회의 3시입니다")
    assert len(store.list_messages(channel["id"])) == 2
    after = store.list_messages(channel["id"], after_id=first["id"])
    assert len(after) == 1 and after[0]["text"].startswith("단가")


def test_search_messages_across_channels(tmp_path: Path) -> None:
    store = ChatStore(tmp_path)
    channels = store.list_channels()
    store.append_message(
        channels[0]["id"], author_id="a", author_name="A", text="한마트 단가 인상 논의"
    )
    store.append_message(channels[1]["id"], author_id="b", author_name="B", text="점심 뭐 먹지")
    hits = store.search_messages("한마트 단가")
    assert len(hits) == 1
    assert hits[0]["channel_name"] == channels[0]["name"]
