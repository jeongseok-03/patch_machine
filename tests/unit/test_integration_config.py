"""Persistence tests for the platform connector configuration store."""

from __future__ import annotations

from pathlib import Path

from negotium.archive.integration_config import (
    DiscordChannelBindingConfig,
    DiscordConnectorConfig,
    GitHubConnectorConfig,
    IntegrationConfigStore,
)


def test_integration_config_defaults_when_missing(archive_tmp: Path) -> None:
    store = IntegrationConfigStore(archive_tmp)

    config = store.read()

    assert config.github.enabled is False
    assert config.github.allowed_repos == []
    assert config.discord.enabled is False
    assert config.discord.channel_bindings == []


def test_integration_config_round_trips(archive_tmp: Path) -> None:
    store = IntegrationConfigStore(archive_tmp)

    updated = store.update_github(
        GitHubConnectorConfig(
            enabled=True,
            allowed_repos=["acme/marketing", "acme/docs"],
            trigger_label="patch",
            webhook_secret_present=True,
            app_token_present=True,
            event_forms=["issue", "pull_request"],
        )
    )

    assert updated.github.enabled is True
    assert "acme/marketing" in updated.github.allowed_repos
    assert updated.github.trigger_label == "patch"

    discord_updated = store.update_discord(
        DiscordConnectorConfig(
            enabled=True,
            bot_token_present=True,
            guild_allowlist=["123"],
            channel_bindings=[
                DiscordChannelBindingConfig(
                    guild_id="123",
                    channel_id="456",
                    channel_name="bug-reports",
                    repo="acme/marketing",
                ),
            ],
            command_forms=["bug_report"],
        )
    )

    assert discord_updated.discord.enabled is True
    assert discord_updated.discord.channel_bindings[0].channel_id == "456"

    reread = store.read()
    assert reread.github.enabled is True
    assert reread.discord.channel_bindings[0].channel_name == "bug-reports"
