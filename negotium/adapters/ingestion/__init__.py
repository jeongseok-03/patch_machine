"""Ingestion adapters normalize external events into ``IssueEvent``."""

from negotium.adapters.ingestion.discord_bot import DiscordBotAdapter
from negotium.adapters.ingestion.github_webhook import (
    GitHubWebhookRouter,
    normalize_github_payload,
)

__all__ = [
    "DiscordBotAdapter",
    "GitHubWebhookRouter",
    "normalize_github_payload",
]
