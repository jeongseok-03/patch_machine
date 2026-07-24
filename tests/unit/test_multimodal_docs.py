"""Unit tests for multimodal content mapping, attachment extraction, and output format."""

from __future__ import annotations

import base64
from pathlib import Path

from negotium.adapters.llm.catalog import model_supports_audio, model_supports_vision
from negotium.adapters.llm.multimodal import (
    to_anthropic_content,
    to_gemini_parts,
    to_openai_content,
    to_text,
)
from negotium.app.services.attachment_service import extract_attachment
from negotium.app.services.document_output import resolve_output_format, write_generated_doc
from negotium.domain.ports import audio_part, flatten_message_text, image_part, text_part

_PNG_1PX = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
).decode("ascii")


def test_text_only_content_passthrough_for_openai() -> None:
    assert to_openai_content("hello") == "hello"


def test_multimodal_content_maps_per_provider() -> None:
    content = [text_part("describe"), image_part(mime="image/png", data="ABC")]

    openai = to_openai_content(content)
    assert isinstance(openai, list)
    assert openai[0] == {"type": "text", "text": "describe"}
    assert openai[1]["type"] == "image_url"
    assert openai[1]["image_url"]["url"] == "data:image/png;base64,ABC"

    anthropic = to_anthropic_content(content)
    assert isinstance(anthropic, list)
    assert anthropic[1]["type"] == "image"
    assert anthropic[1]["source"]["data"] == "ABC"

    gemini = to_gemini_parts(content)
    assert gemini[0] == {"text": "describe"}
    assert gemini[1]["inline_data"]["data"] == "ABC"


def test_text_only_provider_drops_images() -> None:
    content = [text_part("hello"), image_part(mime="image/png", data="ABC")]
    flattened = to_text(content)
    assert "hello" in flattened
    assert "image omitted" in flattened
    assert flatten_message_text("plain") == "plain"


def test_model_supports_vision() -> None:
    assert model_supports_vision("openai", "gpt-4o") is True
    assert model_supports_vision("openai", "gpt-4.1-mini") is True
    assert model_supports_vision("anthropic", "claude-3-5-sonnet-latest") is True
    assert model_supports_vision("vllm", "Qwen/Qwen3-4B") is False
    assert model_supports_vision("openai", "") is False


def test_audio_content_maps_per_provider() -> None:
    content = [text_part("transcribe"), audio_part(mime="audio/mpeg", data="ZZZ")]

    openai = to_openai_content(content)
    assert isinstance(openai, list)
    assert openai[1]["type"] == "input_audio"
    assert openai[1]["input_audio"] == {"data": "ZZZ", "format": "mp3"}

    gemini = to_gemini_parts(content)
    assert gemini[1]["inline_data"] == {"mime_type": "audio/mpeg", "data": "ZZZ"}

    # Anthropic has no audio block; the part degrades to a text note.
    anthropic = to_anthropic_content(content)
    assert isinstance(anthropic, list)
    assert anthropic[1]["type"] == "text"
    assert "audio attachment omitted" in anthropic[1]["text"]

    # Text-only flattening notes the audio omission.
    assert "audio omitted" in to_text(content)


def test_model_supports_audio() -> None:
    assert model_supports_audio("openai", "gpt-4o-audio-preview") is True
    assert model_supports_audio("gemini", "gemini-2.0-flash") is True
    assert model_supports_audio("anthropic", "claude-sonnet-4") is False
    assert model_supports_audio("openai", "gpt-4o") is False
    assert model_supports_audio("vllm", "") is False


def test_extract_audio_attachment(tmp_path: Path) -> None:
    file = tmp_path / "voice.mp3"
    file.write_bytes(b"ID3fakeaudio")
    extracted = extract_attachment(file, archive_root=tmp_path)
    assert extracted.kind == "audio"
    assert extracted.has_audio
    assert extracted.mime == "audio/mpeg"
    assert extracted.audio_format == "mp3"


def test_resolve_output_format_reads_directive() -> None:
    text = "<!-- negotium:format=csv -->\na,b\n1,2"
    fmt, body = resolve_output_format(text)
    assert fmt == "csv"
    assert body == "a,b\n1,2"


def test_resolve_output_format_requested_overrides_directive() -> None:
    text = "<!-- negotium:format=csv -->\nbody"
    fmt, body = resolve_output_format(text, requested="json")
    assert fmt == "json"
    assert body == "body"


def test_resolve_output_format_defaults_to_markdown() -> None:
    fmt, body = resolve_output_format("just text")
    assert fmt == "markdown"
    assert body == "just text"


def test_write_generated_doc_uses_extension(tmp_path: Path) -> None:
    md_path = write_generated_doc(
        tmp_path, folder="documents", slug="t", markdown="# hi", output_format="markdown"
    )
    csv_path = write_generated_doc(
        tmp_path, folder="documents", slug="t", markdown="a,b", output_format="csv"
    )
    assert md_path.endswith(".md")
    assert csv_path.endswith(".csv")
    # Non-markdown content stays raw (no markdown header injected).
    assert (tmp_path / csv_path).read_text(encoding="utf-8").strip() == "a,b"


def test_extract_text_attachment(tmp_path: Path) -> None:
    file = tmp_path / "note.md"
    file.write_text("# Heading\ncontent", encoding="utf-8")
    extracted = extract_attachment(file, archive_root=tmp_path)
    assert extracted.kind == "text"
    assert "content" in extracted.text
    assert extracted.has_text


def test_extract_image_attachment(tmp_path: Path) -> None:
    file = tmp_path / "diagram.png"
    file.write_bytes(base64.b64decode(_PNG_1PX))
    extracted = extract_attachment(file, archive_root=tmp_path)
    assert extracted.kind == "image"
    assert extracted.has_image
    assert extracted.mime == "image/png"


def test_extract_missing_file(tmp_path: Path) -> None:
    extracted = extract_attachment(tmp_path / "nope.txt", archive_root=tmp_path)
    assert extracted.kind == "unsupported"
    assert extracted.note
