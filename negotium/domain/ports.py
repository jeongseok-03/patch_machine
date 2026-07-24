"""Port interfaces (Hexagonal architecture).

Upstream ports are driven by external systems (ingestion sources) and push
``IssueEvent`` into the domain. Downstream ports are driven by the domain to
reach external systems (LLM, Git, filesystem archive, messaging surfaces).

All adapters in ``negotium.adapters`` implement one of these protocols.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from negotium.domain.entities import (
    IssueEvent,
    LlmRoute,
    PatchProposal,
    RepoRef,
    ReviewVerdict,
    WorkSpec,
)


@runtime_checkable
class IssueSource(Protocol):
    """Upstream port: yields normalized issue events from a channel."""

    async def listen(self) -> AsyncIterator[IssueEvent]:  # pragma: no cover - interface
        ...


@runtime_checkable
class CodeRepository(Protocol):
    """Access to a source repository snapshot."""

    def snapshot(self, repo: RepoRef) -> Path: ...

    def read_file(self, repo: RepoRef, relative_path: str) -> str: ...

    def list_paths(self, repo: RepoRef, *, globs: Sequence[str] | None = None) -> list[Path]: ...


class LlmResponse:
    """Value object for an LLM completion. Kept simple to avoid coupling to any SDK."""

    __slots__ = ("completion_tokens", "model", "prompt_tokens", "route", "text")

    def __init__(
        self,
        *,
        text: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        route: LlmRoute = "cloud",
        model: str = "",
    ) -> None:
        self.text = text
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.route = route
        self.model = model


# A multimodal content part is a small normalized dict that adapters translate
# into provider-native payloads. Three shapes are supported:
#   {"type": "text", "text": "..."}
#   {"type": "image", "mime": "image/png", "data": "<base64>"}
#   {"type": "audio", "mime": "audio/mpeg", "data": "<base64>", "format": "mp3"}
ContentPart = dict[str, Any]


class LlmMessage:
    """Minimal chat message structure usable across providers.

    ``content`` is either a plain string (the common case) or a list of
    normalized :data:`ContentPart` dicts for multimodal (text + image) input.
    Text-only adapters flatten image parts away via :func:`flatten_message_text`.
    """

    __slots__ = ("content", "role")

    def __init__(self, role: str, content: str | list[ContentPart]) -> None:
        self.role = role
        self.content = content


def text_part(text: str) -> ContentPart:
    return {"type": "text", "text": text}


def image_part(*, mime: str, data: str) -> ContentPart:
    return {"type": "image", "mime": mime, "data": data}


def audio_part(*, mime: str, data: str, fmt: str = "") -> ContentPart:
    return {"type": "audio", "mime": mime, "data": data, "format": fmt or _audio_format(mime)}


def _audio_format(mime: str) -> str:
    mapping = {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/flac": "flac",
        "audio/mp4": "mp4",
        "audio/m4a": "m4a",
        "audio/x-m4a": "m4a",
    }
    return mapping.get(mime.lower(), "mp3")


def is_multimodal_content(content: str | list[ContentPart]) -> bool:
    return isinstance(content, list)


def flatten_message_text(content: str | list[ContentPart]) -> str:
    """Collapse multimodal content to plain text for text-only providers.

    Image parts are replaced with a short placeholder so the model is at least
    aware an image was attached but omitted.
    """

    if isinstance(content, str):
        return content
    rendered: list[str] = []
    for part in content:
        if part.get("type") == "text":
            rendered.append(str(part.get("text") or ""))
        elif part.get("type") == "image":
            rendered.append("[image omitted: text-only model]")
        elif part.get("type") == "audio":
            rendered.append("[audio omitted: text/vision-only model]")
    return "\n".join(chunk for chunk in rendered if chunk)


@runtime_checkable
class LlmProvider(Protocol):
    """Downstream port: unified chat-completion interface."""

    async def complete(
        self,
        messages: Sequence[LlmMessage],
        *,
        route: LlmRoute = "cloud",
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LlmResponse: ...


@runtime_checkable
class ArchiveStore(Protocol):
    """Persistence of MD logs, indexes and rolling status file."""

    def write_log(
        self,
        *,
        issue: IssueEvent,
        workspec: WorkSpec,
        proposal: PatchProposal,
        verdict: ReviewVerdict,
        status: str,
    ) -> Path: ...

    def update_indexes(
        self,
        *,
        log_path: Path,
        keywords: Sequence[str],
        modules: Sequence[str],
        author: str,
    ) -> None: ...

    def update_status(self, *, summary_md: str) -> None: ...

    def read_recent(self, k: int = 5) -> list[Path]: ...

    def search_by_keywords(self, keywords: Sequence[str], *, limit: int = 20) -> list[Path]: ...


@runtime_checkable
class Notifier(Protocol):
    """Downstream port: reply to the originating channel."""

    async def reply(self, event: IssueEvent, markdown: str) -> None: ...
