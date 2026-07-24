"""Send the proposal back to the originating Discord thread/channel."""

from __future__ import annotations

from negotium.domain.entities import IssueEvent
from negotium.observability import get_logger

_DISCORD_MESSAGE_LIMIT = 1900  # leave headroom for code fences


class DiscordNotifier:
    """Delivers markdown replies via an injected Discord client.

    The notifier accepts any object exposing ``send_message(channel_id, content,
    reply_to=...)``. That matches our ``DiscordBotAdapter`` interface while
    keeping this adapter free of discord.py imports at construction time.
    """

    def __init__(self, sender: object) -> None:
        self._sender = sender
        self._log = get_logger(component="notifier.discord")

    async def reply(self, event: IssueEvent, markdown: str) -> None:
        if event.source != "discord":
            return
        channel_id = event.metadata.get("channel_id")
        if not channel_id:
            self._log.warning("discord.notify.no_channel", event_id=str(event.event_id))
            return
        content = markdown
        if len(content) > _DISCORD_MESSAGE_LIMIT:
            content = (
                content[:_DISCORD_MESSAGE_LIMIT] + "\n... (truncated — 전체 근거는 archive MD 참고)"
            )
        await self._sender.send_message(  # type: ignore[attr-defined]
            channel_id=channel_id,
            content=content,
            reply_to=event.external_id,
        )
        self._log.info(
            "discord.notify.sent",
            channel_id=channel_id,
            event_id=str(event.event_id),
        )
