"""Workspace API: announcements (and, later, messenger/mail)."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from negotium.app.api._shared import _audit, _complete_office_task, _require
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

    @router.get("/workspace/channels")
    async def list_channels(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {"items": container.chat.list_channels()}

    @router.post("/workspace/channels")
    async def create_channel(
        payload: dict[str, str],
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        name = str(payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="채널 이름을 입력해 주세요.")
        try:
            record = container.chat.create_channel(
                name=name,
                description=str(payload.get("description") or "").strip(),
                created_by=actor,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return {"ok": True, "item": record, "items": container.chat.list_channels()}

    @router.get("/workspace/channels/{channel_id}/messages")
    async def list_messages(
        channel_id: str,
        after: str = "",
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        if not container.chat.channel_exists(channel_id):
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다.")
        return {"items": container.chat.list_messages(channel_id, after_id=after)}

    @router.post("/workspace/channels/{channel_id}/messages")
    async def post_message(
        channel_id: str,
        payload: dict[str, str],
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        text = str(payload.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="메시지를 입력해 주세요.")
        if not container.chat.channel_exists(channel_id):
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다.")
        record = container.chat.append_message(
            channel_id, author_id=actor, author_name=actor, text=text
        )
        return {"ok": True, "item": record}

    @router.post("/workspace/channels/{channel_id}/summary")
    async def summarize_channel(
        channel_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        messages = container.chat.list_messages(channel_id, limit=120)
        if not messages:
            raise HTTPException(status_code=404, detail="요약할 메시지가 없습니다.")
        lines = "\n".join(
            f"[{m.get('created_at', '')[:16]}] {m.get('author_name')}: {m.get('text')}"
            for m in messages
        )
        force_local = not bool(container.company_knowledge.scan_config().get("allow_cloud"))
        text = await _complete_office_task(
            container,
            (
                "다음은 사내 메신저 채널의 최근 대화입니다. 안 읽은 사람이 따라잡을 수 있게 "
                "핵심 논의, 결정사항, 해야 할 일을 한국어 불릿으로 짧게 요약하세요. 마크다운만 출력하세요.\n\n"
                + lines
            ),
            task="memory_summary",
            force_local=force_local,
            max_tokens=6000,
        )
        return {"summary": text}

    return router
