"""Patch records markdown store tests."""

from __future__ import annotations

from pathlib import Path

from negotium.archive.patch_records import PatchRecordStore


def test_patch_record_round_trip_writes_markdown_and_index(archive_tmp: Path) -> None:
    store = PatchRecordStore(archive_tmp)

    record = store.append(
        title="외부 커넥터 폼 추가",
        summary="GitHub/Discord 외부 설정 폼을 도입했습니다.",
        request="이슈 #42 의 요청 사항",
        plan=["스토어 추가", "API 연결", "UI 폼"],
        changed_files=["negotium/app/api/__init__.py"],
        verification=["uv run ruff check 통과"],
        follow_ups=["Notion 커넥터"],
        tags=["connector", "ui"],
        actor="owner",
        agent="cursor",
    )

    assert record.record_id
    assert record.relative_path.endswith(".md")
    assert (store.root / record.relative_path).exists()
    assert store.index_path.exists()

    listed = store.list()
    assert listed and listed[0].record_id == record.record_id

    loaded = store.get(record.record_id)
    assert loaded is not None
    assert loaded.title == "외부 커넥터 폼 추가"
    assert loaded.tags == ["connector", "ui"]

    markdown = store.read_markdown(record.record_id)
    assert markdown is not None
    assert "외부 커넥터 폼 추가" in markdown
    assert "negotium/app/api/__init__.py" in markdown


def test_patch_record_handles_string_inputs(archive_tmp: Path) -> None:
    store = PatchRecordStore(archive_tmp)

    record = store.append(
        title="간단 기록",
        summary="단일 라인 입력도 지원",
        plan=None,
        changed_files=["frontend/src/api.ts\nfrontend/src/App.tsx"],
        verification=[],
        follow_ups=None,
        tags=None,
    )

    assert record.changed_files == ["frontend/src/api.ts", "frontend/src/App.tsx"]
    assert record.tags == []
