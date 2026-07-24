"""Persistent platform connector configuration for GitHub/Discord and friends."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import portalocker


@dataclass(frozen=True)
class GitHubConnectorConfig:
    enabled: bool = False
    allowed_repos: list[str] = field(default_factory=list)
    trigger_label: str = "negotium"
    webhook_secret_present: bool = False
    app_token_present: bool = False
    event_forms: list[str] = field(
        default_factory=lambda: ["issue", "pull_request", "repository", "push"]
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "allowed_repos": list(self.allowed_repos),
            "trigger_label": self.trigger_label,
            "webhook_secret_present": self.webhook_secret_present,
            "app_token_present": self.app_token_present,
            "event_forms": list(self.event_forms),
        }

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> GitHubConnectorConfig:
        payload = payload or {}
        repos = payload.get("allowed_repos") or []
        events = payload.get("event_forms") or [
            "issue",
            "pull_request",
            "repository",
            "push",
        ]
        return cls(
            enabled=bool(payload.get("enabled", False)),
            allowed_repos=[str(item).strip() for item in repos if str(item).strip()],
            trigger_label=str(payload.get("trigger_label") or "negotium"),
            webhook_secret_present=bool(payload.get("webhook_secret_present", False)),
            app_token_present=bool(payload.get("app_token_present", False)),
            event_forms=[str(item).strip() for item in events if str(item).strip()],
        )


@dataclass(frozen=True)
class DiscordChannelBindingConfig:
    guild_id: str
    channel_id: str
    channel_name: str
    repo: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "repo": self.repo,
        }

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> DiscordChannelBindingConfig:
        return cls(
            guild_id=str(payload.get("guild_id") or "").strip(),
            channel_id=str(payload.get("channel_id") or "").strip(),
            channel_name=str(payload.get("channel_name") or "").strip(),
            repo=str(payload.get("repo") or "").strip(),
        )


@dataclass(frozen=True)
class DiscordConnectorConfig:
    enabled: bool = False
    bot_token_present: bool = False
    guild_allowlist: list[str] = field(default_factory=list)
    channel_bindings: list[DiscordChannelBindingConfig] = field(default_factory=list)
    command_forms: list[str] = field(
        default_factory=lambda: ["bug_report", "thread_digest", "slash_command"]
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "bot_token_present": self.bot_token_present,
            "guild_allowlist": list(self.guild_allowlist),
            "channel_bindings": [item.to_dict() for item in self.channel_bindings],
            "command_forms": list(self.command_forms),
        }

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> DiscordConnectorConfig:
        payload = payload or {}
        bindings_raw = payload.get("channel_bindings") or []
        bindings = [
            DiscordChannelBindingConfig.from_mapping(item)
            for item in bindings_raw
            if isinstance(item, dict)
        ]
        guilds = payload.get("guild_allowlist") or []
        commands = payload.get("command_forms") or [
            "bug_report",
            "thread_digest",
            "slash_command",
        ]
        return cls(
            enabled=bool(payload.get("enabled", False)),
            bot_token_present=bool(payload.get("bot_token_present", False)),
            guild_allowlist=[str(item).strip() for item in guilds if str(item).strip()],
            channel_bindings=bindings,
            command_forms=[str(item).strip() for item in commands if str(item).strip()],
        )


@dataclass(frozen=True)
class IntegrationConfig:
    github: GitHubConnectorConfig = field(default_factory=GitHubConnectorConfig)
    discord: DiscordConnectorConfig = field(default_factory=DiscordConnectorConfig)

    def to_dict(self) -> dict[str, Any]:
        return {
            "github": self.github.to_dict(),
            "discord": self.discord.to_dict(),
        }

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> IntegrationConfig:
        payload = payload or {}
        return cls(
            github=GitHubConnectorConfig.from_mapping(
                payload.get("github") if isinstance(payload.get("github"), dict) else {}
            ),
            discord=DiscordConnectorConfig.from_mapping(
                payload.get("discord") if isinstance(payload.get("discord"), dict) else {}
            ),
        )


class IntegrationConfigStore:
    """JSON-backed connector configuration."""

    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "integrations" / "config.json"

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> IntegrationConfig:
        if not self._path.exists():
            return IntegrationConfig()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return IntegrationConfig()
        if not isinstance(payload, dict):
            return IntegrationConfig()
        return IntegrationConfig.from_mapping(payload)

    def write(self, config: IntegrationConfig) -> IntegrationConfig:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(self._path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump(config.to_dict(), fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        return config

    def update_github(self, github: GitHubConnectorConfig) -> IntegrationConfig:
        current = self.read()
        return self.write(IntegrationConfig(github=github, discord=current.discord))

    def update_discord(self, discord: DiscordConnectorConfig) -> IntegrationConfig:
        current = self.read()
        return self.write(IntegrationConfig(github=current.github, discord=discord))
