"""Workspace API: announcements (and, later, messenger/mail)."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from negotium.app.api._shared import _audit, _complete_office_task, _require
from negotium.app.company_analysis import _parse_json_object
from negotium.app.container import Container
from negotium.app.mail_client import (
    fetch_inbox,
    fetch_message,
    send_mail,
    verify_account,
)
from negotium.archive.mail_accounts import MailAccount


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
        activity = container.chat.channel_activity()
        return {
            "items": [
                {**channel, **activity.get(str(channel.get("id")), {})}
                for channel in container.chat.list_channels()
            ]
        }

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

    @router.post("/workspace/channels/{channel_id}/messages/{message_id}/react")
    async def react_message(
        channel_id: str,
        message_id: str,
        payload: dict[str, str],
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        emoji = str(payload.get("emoji") or "").strip()
        if not emoji or len(emoji) > 8:
            raise HTTPException(status_code=400, detail="이모지가 필요합니다.")
        if not container.chat.channel_exists(channel_id):
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다.")
        container.chat.toggle_reaction(channel_id, message_id, author_id=actor, emoji=emoji)
        return {"ok": True}

    @router.delete("/workspace/channels/{channel_id}/messages/{message_id}")
    async def delete_message(
        channel_id: str,
        message_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        if not container.chat.delete_message(channel_id, message_id, author_id=actor):
            raise HTTPException(status_code=403, detail="본인 메시지만 삭제할 수 있습니다.")
        return {"ok": True}

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

    @router.get("/workspace/mail/account")
    async def get_mail_account(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        account = container.mail_accounts.read(actor)
        return account.masked() if account else {"configured": False}

    @router.put("/workspace/mail/account")
    def put_mail_account(
        payload: dict[str, object],
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        account = MailAccount.from_mapping(payload)
        if not (account.email and account.imap_host and account.password):
            raise HTTPException(
                status_code=400, detail="이메일, IMAP 서버, 비밀번호(앱 비밀번호)를 입력해 주세요."
            )
        try:
            verify_account(account)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"메일 서버 연결 실패: {exc}") from None
        container.mail_accounts.upsert(actor, account)
        _audit(
            container,
            actor=actor,
            action="workspace.mail.connect",
            target=account.email,
            details={"imap_host": account.imap_host},
        )
        return {"ok": True, **account.masked()}

    def _account_for(actor: str) -> MailAccount:
        account = container.mail_accounts.read(actor)
        if account is None:
            raise HTTPException(status_code=400, detail="먼저 메일 계정을 연결해 주세요.")
        return account

    @router.get("/workspace/mail/inbox")
    def mail_inbox(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        try:
            items = fetch_inbox(_account_for(actor))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"메일함을 불러오지 못했습니다: {exc}"
            ) from None
        return {"items": items}

    @router.get("/workspace/mail/message/{uid}")
    def mail_message(
        uid: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        try:
            message = fetch_message(_account_for(actor), uid)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"메일을 불러오지 못했습니다: {exc}"
            ) from None
        if message is None:
            raise HTTPException(status_code=404, detail="메일을 찾을 수 없습니다.")
        return message

    @router.post("/workspace/mail/triage")
    async def mail_triage(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        try:
            items = fetch_inbox(_account_for(actor))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"메일함을 불러오지 못했습니다: {exc}"
            ) from None
        if not items:
            return {"reply_needed": [], "fyi": [], "summary": "받은 메일이 없습니다."}
        lines = "\n".join(
            f"- uid={item['uid']} | 보낸이: {item['from']} | 제목: {item['subject']} | 내용: {item['snippet']}"
            for item in items
        )
        force_local = not bool(container.company_knowledge.scan_config().get("allow_cloud"))
        raw = await _complete_office_task(
            container,
            (
                "다음은 받은편지함 목록입니다. 답장이 필요한 메일과 참고만 하면 되는 메일을 분류하고 "
                "한 줄 요약을 만드세요. 광고/알림 메일은 무시해도 됩니다.\n"
                'JSON으로만 답하세요: {"reply_needed": ["uid"], "fyi": ["uid"], "summary": "오늘 메일 한 줄 요약"}\n\n'
                + lines
            ),
            task="memory_summary",
            force_local=force_local,
            max_tokens=6000,
        )
        parsed = _parse_json_object(raw) or {}
        return {
            "reply_needed": [str(u) for u in parsed.get("reply_needed") or []],
            "fyi": [str(u) for u in parsed.get("fyi") or []],
            "summary": str(parsed.get("summary") or ""),
        }

    @router.post("/workspace/mail/reply-draft")
    async def mail_reply_draft(
        payload: dict[str, str],
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        uid = str(payload.get("uid") or "")
        try:
            message = fetch_message(_account_for(actor), uid)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"메일을 불러오지 못했습니다: {exc}"
            ) from None
        if message is None:
            raise HTTPException(status_code=404, detail="메일을 찾을 수 없습니다.")
        force_local = not bool(container.company_knowledge.scan_config().get("allow_cloud"))
        profile = container.company_knowledge.company_profile()
        draft = await _complete_office_task(
            container,
            (
                "다음 메일에 대한 정중한 한국어 답장 초안을 작성하세요. 회사 맥락을 참고하되 "
                "확정되지 않은 약속은 하지 마세요. 답장 본문만 출력하세요.\n"
                f"회사 소개: {profile.get('organization', '')}\n\n"
                f"보낸이: {message['from']}\n제목: {message['subject']}\n본문:\n{message['body']}"
            ),
            task="memory_summary",
            force_local=force_local,
            max_tokens=6000,
        )
        return {"draft": draft, "to": message["from"], "subject": f"Re: {message['subject']}"}

    @router.post("/workspace/mail/send")
    def mail_send(
        payload: dict[str, str],
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        to = str(payload.get("to") or "").strip()
        subject = str(payload.get("subject") or "").strip()
        body = str(payload.get("body") or "")
        if not to or not subject:
            raise HTTPException(status_code=400, detail="받는 사람과 제목을 입력해 주세요.")
        account = _account_for(actor)
        if not account.smtp_host:
            raise HTTPException(
                status_code=400, detail="SMTP 서버가 설정되지 않아 보낼 수 없습니다."
            )
        try:
            send_mail(account, to=to, subject=subject, body=body)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"전송 실패: {exc}") from None
        _audit(
            container,
            actor=actor,
            action="workspace.mail.send",
            target=to,
            details={"subject": subject[:120]},
        )
        return {"ok": True}

    return router
