"""Document generation service boundary."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from negotium.app.container import Container
    from negotium.app.schemas import GeneratedDocumentPayload, HiringRequest


async def generate_hiring_document(
    container: Container,
    payload: HiringRequest,
    *,
    kind: str,
    instruction: str,
) -> GeneratedDocumentPayload:
    from negotium.app.api import _generate_hiring_document

    return await _generate_hiring_document(container, payload, kind=kind, instruction=instruction)


def write_generated_doc(archive_dir: Path, *, folder: str, slug: str, markdown: str) -> str:
    from negotium.app.api import _write_generated_doc

    return _write_generated_doc(archive_dir, folder=folder, slug=slug, markdown=markdown)
