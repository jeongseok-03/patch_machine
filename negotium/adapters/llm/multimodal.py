"""Translate normalized multimodal content parts into provider payloads.

The domain uses a small normalized content-part shape (see
``negotium.domain.ports``):

    {"type": "text", "text": "..."}
    {"type": "image", "mime": "image/png", "data": "<base64>"}

Each provider expects a different layout for image content. These helpers keep
that mapping in one place so the adapters stay thin and the conversions are
unit-testable.
"""

from __future__ import annotations

from typing import Any

from negotium.domain.ports import ContentPart, flatten_message_text


def to_openai_content(content: str | list[ContentPart]) -> str | list[dict[str, Any]]:
    """OpenAI chat-completions content parts.

    Text stays a plain string when no images are present (keeps requests
    identical to the legacy path); multimodal becomes a content-parts list.
    """

    if isinstance(content, str):
        return content
    parts: list[dict[str, Any]] = []
    for part in content:
        if part.get("type") == "text":
            parts.append({"type": "text", "text": str(part.get("text") or "")})
        elif part.get("type") == "image":
            mime = str(part.get("mime") or "image/png")
            data = str(part.get("data") or "")
            parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}})
        elif part.get("type") == "audio":
            parts.append(
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": str(part.get("data") or ""),
                        "format": str(part.get("format") or "mp3"),
                    },
                }
            )
    return parts


def to_anthropic_content(content: str | list[ContentPart]) -> str | list[dict[str, Any]]:
    """Anthropic Messages API content blocks."""

    if isinstance(content, str):
        return content
    blocks: list[dict[str, Any]] = []
    for part in content:
        if part.get("type") == "text":
            blocks.append({"type": "text", "text": str(part.get("text") or "")})
        elif part.get("type") == "image":
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": str(part.get("mime") or "image/png"),
                        "data": str(part.get("data") or ""),
                    },
                }
            )
        elif part.get("type") == "audio":
            # Anthropic Messages API has no audio input block; note the omission.
            blocks.append(
                {"type": "text", "text": "[audio attachment omitted: provider has no audio input]"}
            )
    return blocks


def to_gemini_parts(content: str | list[ContentPart]) -> list[dict[str, Any]]:
    """Gemini generateContent parts."""

    if isinstance(content, str):
        return [{"text": content}]
    parts: list[dict[str, Any]] = []
    for part in content:
        if part.get("type") == "text":
            parts.append({"text": str(part.get("text") or "")})
        elif part.get("type") in {"image", "audio"}:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": str(part.get("mime") or "application/octet-stream"),
                        "data": str(part.get("data") or ""),
                    }
                }
            )
    return parts


def to_text(content: str | list[ContentPart]) -> str:
    """Text-only flattening for providers without vision support."""

    return flatten_message_text(content)


__all__ = [
    "to_anthropic_content",
    "to_gemini_parts",
    "to_openai_content",
    "to_text",
]
