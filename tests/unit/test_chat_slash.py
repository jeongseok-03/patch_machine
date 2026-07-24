"""Unit tests for chat slash-command parsing helpers."""

from __future__ import annotations

from negotium.app.api import _is_slash_command, _parse_chat_slash


def test_is_slash_command_detects_leading_slash() -> None:
    assert _is_slash_command("/skills") is True
    assert _is_slash_command("  /office.summarize hi") is True
    assert _is_slash_command("hello /not-a-command") is False


def test_parse_slash_extracts_id_and_kv_and_free_text() -> None:
    skill_id, inputs = _parse_chat_slash("/office.document_draft title=주간보고 이번 주 업무 정리")
    assert skill_id == "office.document_draft"
    assert inputs["title"] == "주간보고"
    # Free text is exposed under common input names.
    assert inputs["source_text"] == "이번 주 업무 정리"
    assert inputs["text"] == "이번 주 업무 정리"


def test_parse_slash_quoted_values() -> None:
    skill_id, inputs = _parse_chat_slash('/x title="여러 단어 제목" body text')
    assert skill_id == "x"
    assert inputs["title"] == "여러 단어 제목"
    assert inputs["text"] == "body text"


def test_parse_slash_only_id() -> None:
    skill_id, inputs = _parse_chat_slash("/skills")
    assert skill_id == "skills"
    assert inputs == {}
