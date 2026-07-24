"""Shared helpers for writing AI-generated documents in AI-chosen formats.

Extracted so the HTTP API, the skill runtime, and the CLI all write documents
the same way and honor a leading ``<!-- negotium:format=... -->`` directive.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import portalocker

OUTPUT_FORMATS = {"markdown", "html", "csv", "json", "text"}
FORMAT_EXTENSIONS = {
    "markdown": "md",
    "html": "html",
    "csv": "csv",
    "json": "json",
    "text": "txt",
}
# "negotium" is accepted for backward compatibility with prompts/skills
# authored before the Negotium rename.
_FORMAT_DIRECTIVE_RE = re.compile(
    r"^\s*<!--\s*(?:negotium|negotium):format\s*=\s*([a-zA-Z]+)\s*-->\s*", re.IGNORECASE
)


def resolve_output_format(text: str, *, requested: str = "auto") -> tuple[str, str]:
    """Parse a leading format directive and return ``(format, body)``.

    The directive line is stripped from the body. An explicit ``requested``
    format (not ``auto``) overrides the directive's value.
    """

    body = text
    detected = ""
    match = _FORMAT_DIRECTIVE_RE.match(text)
    if match:
        candidate = match.group(1).lower()
        if candidate in OUTPUT_FORMATS:
            detected = candidate
        body = text[match.end() :]
    if requested and requested != "auto" and requested in OUTPUT_FORMATS:
        return requested, body.strip()
    if detected:
        return detected, body.strip()
    return "markdown", body.strip()


def write_generated_doc(
    archive_dir: Path,
    *,
    folder: str,
    slug: str,
    markdown: str,
    output_format: str = "markdown",
) -> str:
    safe_slug = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in slug).strip("_")
    safe_slug = safe_slug[:80] or "generated"
    created = datetime.now(UTC)
    fmt = output_format if output_format in OUTPUT_FORMATS else "markdown"
    extension = FORMAT_EXTENSIONS[fmt]
    relative = Path(folder) / f"{created.strftime('%Y%m%d_%H%M%S')}_{safe_slug}.{extension}"
    path = archive_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "markdown":
        body = f"# {slug}\n\n_생성: {created.isoformat()}_\n\n{markdown.strip()}\n"
    else:
        body = markdown.strip() + "\n"
    with portalocker.Lock(path, "w", encoding="utf-8", timeout=5) as fh:
        fh.write(body)
    return relative.as_posix()


__all__ = [
    "FORMAT_EXTENSIONS",
    "OUTPUT_FORMATS",
    "resolve_output_format",
    "write_generated_doc",
]
