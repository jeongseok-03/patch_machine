"""Discord channel → repository mapping.

Loaded from YAML at startup so non-technical operators can edit the mapping
with a text editor, consistent with the MD-GitOps philosophy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from negotium.domain.entities import RepoRef


@dataclass(frozen=True, slots=True)
class ChannelBinding:
    guild_id: str
    channel_id: str
    channel_name: str
    repo: RepoRef


class ChannelMap:
    def __init__(self, bindings: list[ChannelBinding]) -> None:
        self._bindings = bindings
        self._by_channel_id = {b.channel_id: b for b in bindings}
        self._by_channel_name = {(b.guild_id, b.channel_name): b for b in bindings}

    @property
    def bindings(self) -> list[ChannelBinding]:
        return list(self._bindings)

    def by_channel_id(self, channel_id: str) -> ChannelBinding | None:
        return self._by_channel_id.get(channel_id)

    def by_channel_name(self, guild_id: str, channel_name: str) -> ChannelBinding | None:
        return self._by_channel_name.get((guild_id, channel_name))

    @classmethod
    def load(cls, path: Path) -> ChannelMap:
        if not path.exists():
            return cls([])
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        guilds = raw.get("guilds", {}) or {}
        bindings: list[ChannelBinding] = []
        for guild_id, guild_cfg in guilds.items():
            channels = (guild_cfg or {}).get("channels", {}) or {}
            for channel_key, channel_cfg in channels.items():
                repo_full = (channel_cfg or {}).get("repo")
                if not repo_full or "/" not in repo_full:
                    continue
                owner, name = repo_full.split("/", 1)
                default_branch = (channel_cfg or {}).get("default_branch", "main")
                bindings.append(
                    ChannelBinding(
                        guild_id=str(guild_id),
                        channel_id=str((channel_cfg or {}).get("channel_id", channel_key)),
                        channel_name=str(channel_key),
                        repo=RepoRef(owner=owner, name=name, default_branch=default_branch),
                    ),
                )
        return cls(bindings)
