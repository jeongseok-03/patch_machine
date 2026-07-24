"""Uploads API routes (split from the former monolithic router)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Header, UploadFile

from negotium.app.api._shared import (
    _audit,
    _require,
)
from negotium.app.container import Container


def create_uploads_router(container: Container) -> APIRouter:
    """Routes for the uploads domain."""
    router = APIRouter()

    @router.get("/uploads")
    async def list_uploads() -> dict[str, object]:
        return {"uploads": container.uploads.list()}

    @router.post("/uploads")
    async def upload_file(
        file: Annotated[UploadFile, File(...)],
        description: Annotated[str, Form()] = "",
        tags: Annotated[str, Form()] = "",
        work_title: Annotated[str, Form()] = "",
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "uploads:write")
        record = container.uploads.save(
            filename=file.filename or "upload.bin",
            source=file.file,
            description=description,
            tags=tags,
            work_title=work_title,
        )
        _audit(
            container,
            actor=actor,
            action="upload.create",
            target="upload",
            target_id=record.id,
            details={"path": record.path},
        )
        return {"ok": True, "upload": record.to_dict()}

    @router.delete("/uploads/{upload_id}")
    async def delete_upload(
        upload_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "uploads:write")
        ok = container.uploads.delete(upload_id)
        _audit(container, actor=actor, action="upload.delete", target="upload", target_id=upload_id)
        return {"ok": ok}

    return router
