"""Multimodal attachment extraction for office document automation.

Uploaded files are stored as raw bytes by :class:`UploadStore`. This service
turns a stored upload into an :class:`ExtractedAttachment` that the document
automation pipeline can feed to an LLM:

* text-like files (md/txt/csv/tsv/xlsx) are flattened to text;
* PDFs are text-extracted with ``pypdf`` (falling back to image/OCR when the
  page text is empty, e.g. scanned PDFs are out of scope and reported);
* images are base64-encoded for vision passthrough, with an optional OCR text
  fallback when ``pytesseract``/``Pillow`` are installed.

The service never raises for unreadable files; it returns a best-effort record
with an explanatory note so the caller can surface it to the user.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from negotium.app.initial_setup import ParsedSetupFile, parse_setup_file

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".json", ".jsonl", ".yaml", ".yml"}
TABULAR_SUFFIXES = {".csv", ".tsv", ".xlsx"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac", ".mp4"}
PDF_SUFFIXES = {".pdf"}

_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

_AUDIO_MIME_BY_SUFFIX = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
    ".flac": "audio/flac",
    ".mp4": "audio/mp4",
}
_AUDIO_FORMAT_BY_SUFFIX = {
    ".mp3": "mp3",
    ".wav": "wav",
    ".m4a": "m4a",
    ".ogg": "ogg",
    ".webm": "webm",
    ".flac": "flac",
    ".mp4": "mp4",
}

_TEXT_CHAR_CAP = 12000
_PDF_CHAR_CAP = 20000


@dataclass(frozen=True)
class ExtractedAttachment:
    """Normalized representation of an uploaded attachment for LLM consumption."""

    filename: str
    path: str
    kind: str  # text | tabular | pdf | image | audio | unsupported
    text: str = ""
    image_b64: str = ""
    audio_b64: str = ""
    audio_format: str = ""
    mime: str = ""
    sensitive_hint: bool = False
    truncated: bool = False
    note: str = ""

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())

    @property
    def has_image(self) -> bool:
        return bool(self.image_b64)

    @property
    def has_audio(self) -> bool:
        return bool(self.audio_b64)

    def to_prompt_block(self) -> str:
        header = f"### 첨부: {self.filename} ({self.kind})"
        lines = [header]
        if self.note:
            lines.append(f"- 비고: {self.note}")
        if self.has_text:
            lines.append(self.text)
        elif self.has_image:
            lines.append("(이미지 첨부 — 비전 모델에 직접 전달됩니다.)")
        elif self.has_audio:
            lines.append("(오디오 첨부 — 오디오 지원 모델에 직접 전달됩니다.)")
        return "\n".join(lines).strip()


def extract_attachment(path: Path, *, archive_root: Path | None = None) -> ExtractedAttachment:
    """Extract text and/or image bytes from a stored upload file."""

    relative = path.relative_to(archive_root).as_posix() if archive_root else path.as_posix()
    if not path.exists() or not path.is_file():
        return ExtractedAttachment(
            filename=path.name,
            path=relative,
            kind="unsupported",
            note="파일을 찾을 수 없습니다.",
        )

    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return _extract_image(path, relative=relative, suffix=suffix)
    if suffix in AUDIO_SUFFIXES:
        return _extract_audio(path, relative=relative, suffix=suffix)
    if suffix in PDF_SUFFIXES:
        return _extract_pdf(path, relative=relative)
    if suffix in TABULAR_SUFFIXES:
        return _extract_tabular(path, relative=relative, archive_root=archive_root)
    if suffix in TEXT_SUFFIXES or suffix == "":
        return _extract_text(path, relative=relative, suffix=suffix)
    # Unknown binary type: try a defensive UTF-8 read, otherwise mark unsupported.
    try:
        text = path.read_text(encoding="utf-8")[:_TEXT_CHAR_CAP]
    except (UnicodeDecodeError, OSError):
        return ExtractedAttachment(
            filename=path.name,
            path=relative,
            kind="unsupported",
            note=f"지원하지 않는 형식({suffix or 'unknown'})이라 텍스트로 읽지 못했습니다.",
        )
    return ExtractedAttachment(
        filename=path.name,
        path=relative,
        kind="text",
        text=text,
        truncated=len(text) >= _TEXT_CHAR_CAP,
    )


def _extract_text(path: Path, *, relative: str, suffix: str) -> ExtractedAttachment:
    text = path.read_text(encoding="utf-8", errors="ignore")
    truncated = len(text) > _TEXT_CHAR_CAP
    return ExtractedAttachment(
        filename=path.name,
        path=relative,
        kind="text",
        text=text[:_TEXT_CHAR_CAP],
        truncated=truncated,
    )


def _extract_tabular(
    path: Path, *, relative: str, archive_root: Path | None
) -> ExtractedAttachment:
    try:
        parsed: ParsedSetupFile = parse_setup_file(path, archive_root=archive_root)
    except (RuntimeError, OSError, ValueError) as exc:
        return ExtractedAttachment(
            filename=path.name,
            path=relative,
            kind="tabular",
            note=f"표 형식 파일 파싱 실패: {exc}",
        )
    return ExtractedAttachment(
        filename=path.name,
        path=relative,
        kind="tabular",
        text=parsed.to_prompt_block(),
        sensitive_hint=parsed.sensitive_hint,
        truncated=len(parsed.rows) > 50,
    )


def _extract_pdf(path: Path, *, relative: str) -> ExtractedAttachment:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ExtractedAttachment(
            filename=path.name,
            path=relative,
            kind="pdf",
            note="PDF 추출에는 pypdf가 필요합니다. (pip install pypdf)",
        )
    try:
        reader = PdfReader(str(path))
        chunks: list[str] = []
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
            if sum(len(c) for c in chunks) >= _PDF_CHAR_CAP:
                break
        text = "\n\n".join(chunk for chunk in chunks if chunk.strip())
    except Exception as exc:
        return ExtractedAttachment(
            filename=path.name,
            path=relative,
            kind="pdf",
            note=f"PDF 파싱 실패: {exc}",
        )
    if not text.strip():
        return ExtractedAttachment(
            filename=path.name,
            path=relative,
            kind="pdf",
            note="텍스트 레이어가 없는 PDF(스캔본)로 보입니다. 이미지 OCR이 필요합니다.",
        )
    return ExtractedAttachment(
        filename=path.name,
        path=relative,
        kind="pdf",
        text=text[:_PDF_CHAR_CAP],
        truncated=len(text) > _PDF_CHAR_CAP,
    )


def _extract_image(path: Path, *, relative: str, suffix: str) -> ExtractedAttachment:
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    mime = _MIME_BY_SUFFIX.get(suffix, "image/png")
    ocr_text, ocr_note = _try_ocr(path)
    return ExtractedAttachment(
        filename=path.name,
        path=relative,
        kind="image",
        text=ocr_text,
        image_b64=encoded,
        mime=mime,
        note=ocr_note,
    )


def _extract_audio(path: Path, *, relative: str, suffix: str) -> ExtractedAttachment:
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    mime = _AUDIO_MIME_BY_SUFFIX.get(suffix, "audio/mpeg")
    fmt = _AUDIO_FORMAT_BY_SUFFIX.get(suffix, "mp3")
    return ExtractedAttachment(
        filename=path.name,
        path=relative,
        kind="audio",
        audio_b64=encoded,
        audio_format=fmt,
        mime=mime,
        note="오디오 첨부 — 오디오 지원 모델에서만 직접 해석됩니다.",
    )


def _try_ocr(path: Path) -> tuple[str, str]:
    """Best-effort OCR. Returns ``(text, note)``; both empty when OCR is unavailable."""

    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return "", ""
    try:
        with Image.open(path) as image:
            text = pytesseract.image_to_string(image)
    except Exception as exc:
        return "", f"OCR 시도 실패: {exc}"
    cleaned = text.strip()
    if not cleaned:
        return "", ""
    return cleaned[:_TEXT_CHAR_CAP], "이미지에서 OCR로 추출한 텍스트입니다."


def extract_attachments(
    paths: list[Path], *, archive_root: Path | None = None
) -> list[ExtractedAttachment]:
    return [extract_attachment(path, archive_root=archive_root) for path in paths]


__all__ = ["ExtractedAttachment", "extract_attachment", "extract_attachments"]
