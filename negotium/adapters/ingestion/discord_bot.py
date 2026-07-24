"""Discord bot adapter.

Two triggers are supported:
  * ``/patch <description>`` slash command issued in any allowlisted guild.
  * Plain messages posted inside a channel pre-mapped to a repository via
    ``config/channel_map.yml``.

The adapter deliberately keeps discord.py imports lazy so test and offline
environments can load this module without the library being installed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from negotium.adapters.ingestion.channel_map import ChannelBinding, ChannelMap
from negotium.app.settings import DiscordSettings
from negotium.application.event_bus import EventBus, QueueFullError
from negotium.domain.entities import IssueEvent, RepoRef
from negotium.observability import get_logger


def normalize_discord_message(
    *,
    message_id: str,
    channel_id: str,
    guild_id: str,
    channel_name: str,
    author: str,
    content: str,
    repo: RepoRef,
    source_kind: str = "channel",
) -> IssueEvent:
    title = content.splitlines()[0][:120] if content.strip() else "(discord message)"
    return IssueEvent(
        source="discord",
        external_id=str(message_id),
        repo=repo,
        title=title,
        body=content,
        author=author,
        metadata={
            "channel_id": str(channel_id),
            "channel_name": channel_name,
            "guild_id": str(guild_id),
            "trigger": source_kind,
        },
    )


@dataclass
class DiscordBotAdapter:
    """Thin wrapper around a discord.py ``Client`` instance.

    Construction does *not* start the bot; call :meth:`start` from the app
    entrypoint. Tests exercise the normalization helpers directly without
    touching the Discord gateway.
    """

    settings: DiscordSettings
    bus: EventBus
    channel_map: ChannelMap
    client: Any | None = None

    def __post_init__(self) -> None:
        self._log = get_logger(component="ingestion.discord")
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if not self.settings.bot_token:
            self._log.info("discord.disabled")
            return
        if self.client is None:
            self.client = self._build_client()
        self._register_handlers()
        assert self.client is not None
        self._task = asyncio.create_task(self.client.start(self.settings.bot_token))
        self._log.info("discord.started")

    async def stop(self) -> None:
        if self.client is None:
            return
        try:
            await self.client.close()
        finally:
            if self._task is not None:
                self._task.cancel()

    async def send_message(
        self,
        *,
        channel_id: str,
        content: str,
        reply_to: str | None = None,
    ) -> None:
        if self.client is None:
            self._log.warning("discord.send.no_client")
            return
        try:
            channel = await self.client.fetch_channel(int(channel_id))
        except Exception:
            self._log.exception("discord.send.fetch_failed", channel_id=channel_id)
            return
        reference = None
        if reply_to is not None:
            try:
                reference = await channel.fetch_message(int(reply_to))
            except Exception:
                reference = None
        try:
            await channel.send(content=content, reference=reference)
        except Exception:
            self._log.exception("discord.send.failed", channel_id=channel_id)

    def _build_client(self) -> Any:
        from discord import Intents
        from discord.ext import commands

        intents = Intents.default()
        intents.message_content = True
        bot = commands.Bot(command_prefix="!", intents=intents)
        return bot

    def _register_handlers(self) -> None:
        bot = self.client
        assert bot is not None
        guild_allowlist = set(self.settings.guild_allowlist)

        @bot.event
        async def on_ready() -> None:
            self._log.info("discord.ready", user=str(getattr(bot.user, "name", "")))

        @bot.event
        async def on_message(message: Any) -> None:
            if message.author.bot:
                return
            guild_id = str(getattr(message.guild, "id", "")) if message.guild else ""
            if guild_allowlist and guild_id not in guild_allowlist:
                return
            channel_id = str(message.channel.id)
            channel_name = str(getattr(message.channel, "name", ""))
            binding = self.channel_map.by_channel_id(
                channel_id
            ) or self.channel_map.by_channel_name(guild_id, channel_name)
            if binding is None:
                return
            await self._enqueue_from_binding(
                binding=binding,
                message_id=str(message.id),
                channel_id=channel_id,
                channel_name=channel_name,
                guild_id=guild_id,
                author=str(message.author),
                content=str(message.content or ""),
                trigger="channel",
            )

        @bot.command(name="patch")
        async def patch_command(ctx: Any, *, description: str = "") -> None:
            guild_id = str(getattr(ctx.guild, "id", "")) if ctx.guild else ""
            if guild_allowlist and guild_id not in guild_allowlist:
                return
            channel_id = str(ctx.channel.id)
            channel_name = str(getattr(ctx.channel, "name", ""))
            binding = self.channel_map.by_channel_id(
                channel_id
            ) or self.channel_map.by_channel_name(guild_id, channel_name)
            if binding is None:
                await ctx.reply(
                    "이 채널은 아직 리포지토리와 매핑되지 않았습니다. `config/channel_map.yml` 을 확인해주세요."
                )
                return
            await self._enqueue_from_binding(
                binding=binding,
                message_id=str(ctx.message.id),
                channel_id=channel_id,
                channel_name=channel_name,
                guild_id=guild_id,
                author=str(ctx.author),
                content=description or ctx.message.content,
                trigger="slash",
            )
            await ctx.reply(
                "Negotium이 요청을 접수했습니다. 처리 결과는 이 채널에 답글로 올라옵니다."
            )

    async def _enqueue_from_binding(
        self,
        *,
        binding: ChannelBinding,
        message_id: str,
        channel_id: str,
        channel_name: str,
        guild_id: str,
        author: str,
        content: str,
        trigger: str,
    ) -> None:
        event = normalize_discord_message(
            message_id=message_id,
            channel_id=channel_id,
            guild_id=guild_id,
            channel_name=channel_name,
            author=author,
            content=content,
            repo=binding.repo,
            source_kind=trigger,
        )
        try:
            self.bus.publish_nowait(event)
        except QueueFullError:
            self._log.warning("discord.bus_full", channel_id=channel_id)
