"""Workspace API: announcements (and, later, messenger/mail)."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from negotium.app.api._shared import _audit, _require
from negotium.app.container import Container


def create_workspace_router(container: Container) -> APIRouter:
    """Routes every employee's daily workspace uses."""
    router = APIRouter()

    @router.get("/workspace/announcements")
    async def list_announcements(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {"items": container.announcements.list()}

    @router.post("/workspace/announcements")
    async def create_announcement(
        payload: dict[str, object],
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        title = str(payload.get("title") or "").strip()
        body = str(payload.get("body") or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="공지 제목을 입력해 주세요.")
        record = container.announcements.create(
            title=title,
            body=body,
            author_id=actor,
            author_name=actor,
            pinned=bool(payload.get("pinned")),
        )
        _audit(
            container,
            actor=actor,
            action="workspace.announcement.create",
            target=record["id"],
            details={"title": title},
        )
        return {"ok": True, "item": record, "items": container.announcements.list()}

    @router.delete("/workspace/announcements/{announcement_id}")
    async def delete_announcement(
        announcement_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        if not container.announcements.delete(announcement_id):
            raise HTTPException(status_code=404, detail="공지를 찾을 수 없습니다.")
        _audit(
            container,
            actor=actor,
            action="workspace.announcement.delete",
            target=announcement_id,
            details={},
        )
        return {"ok": True, "items": container.announcements.list()}

    return router
