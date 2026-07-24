"""Built-in company messenger — channels and messages, file-backed.

Channels live in ``archive/chat/channels.json``; each channel's messages are
an append-only JSONL stream in ``archive/chat/<channel_id>.jsonl``. Messages
are part of the company memory: the Q&A engine searches them alongside
document summaries.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from negotium.archive._store import (
    append_jsonl_line,
    iter_jsonl_records,
    read_json_file,
    write_json_file,
)

DEFAULT_CHANNELS = [
    {"name": "전체", "description": "회사 전체 공지·잡담"},
    {"name": "업무", "description": "업무 논의"},
]


class ChatStore:
    """Channels + per-channel JSONL message streams."""

    def __init__(self, archive_dir: Path) -> None:
        self._dir = archive_dir / "chat"
        self._channels_path = self._dir / "channels.json"

    def _message_path(self, channel_id: str) -> Path:
        safe = "".join(ch for ch in channel_id if ch.isalnum() or ch in "-_")
        return self._dir / f"{safe}.jsonl"

    def list_channels(self) -> list[dict[str, Any]]:
        payload = read_json_file(self._channels_path, default=list)
        channels = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
        if not channels:
            channels = [
                {
                    "id": uuid.uuid4().hex[:10],
                    "name": entry["name"],
                    "description": entry["description"],
                    "created_by": "system",
                    "created_at": datetime.now(UTC).isoformat(),
                }
                for entry in DEFAULT_CHANNELS
            ]
            write_json_file(self._channels_path, channels)
        return channels

    def create_channel(self, *, name: str, description: str, created_by: str) -> dict[str, Any]:
        channels = self.list_channels()
        if any(channel.get("name") == name for channel in channels):
            raise ValueError("같은 이름의 채널이 이미 있습니다.")
        record = {
            "id": uuid.uuid4().hex[:10],
            "name": name,
            "description": description,
            "created_by": created_by,
            "created_at": datetime.now(UTC).isoformat(),
        }
        channels.append(record)
        write_json_file(self._channels_path, channels)
        return record

    def channel_exists(self, channel_id: str) -> bool:
        return any(channel.get("id") == channel_id for channel in self.list_channels())

    def append_message(
        self, channel_id: str, *, author_id: str, author_name: str, text: str
    ) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex[:12],
            "channel_id": channel_id,
            "author_id": author_id,
            "author_name": author_name,
            "text": text,
            "created_at": datetime.now(UTC).isoformat(),
        }
        append_jsonl_line(self._message_path(channel_id), record)
        return record

    def list_messages(
        self, channel_id: str, *, limit: int = 100, after_id: str = ""
    ) -> list[dict[str, Any]]:
        records = list(iter_jsonl_records(self._message_path(channel_id)))
        if after_id:
            for index, record in enumerate(records):
                if record.get("id") == after_id:
                    records = records[index + 1 :]
                    break
        return records[-limit:]

    def search_messages(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        tokens = [token.lower() for token in query.split() if len(token) >= 2]
        if not tokens:
            return []
        names = {channel["id"]: channel.get("name", "") for channel in self.list_channels()}
        scored: list[tuple[int, dict[str, Any]]] = []
        for channel_id, channel_name in names.items():
            for record in iter_jsonl_records(self._message_path(channel_id)):
                text = str(record.get("text") or "").lower()
                score = sum(text.count(token) for token in tokens)
                if score:
                    scored.append((score, {**record, "channel_name": channel_name}))
        scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("created_at") or "")))
        return [record for _, record in scored[:limit]]
