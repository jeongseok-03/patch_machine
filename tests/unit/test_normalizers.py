"""Normalizer contract tests."""

from __future__ import annotations

import json
from pathlib import Path

from negotium.adapters.ingestion.discord_bot import normalize_discord_message
from negotium.adapters.ingestion.github_webhook import normalize_github_payload
from negotium.domain.entities import RepoRef

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_github_issue_opened_payload_maps_all_fields() -> None:
    payload = json.loads((FIXTURES / "github_issue_opened.json").read_text())
    event = normalize_github_payload("issues", payload)
    assert event is not None
    assert event.source == "github"
    assert event.external_id == "42"
    assert event.repo.full_name == "acme/payments"
    assert "negotium" in event.labels
    assert event.author == "qa-tester"
    assert event.metadata["html_url"].endswith("/issues/42")


def test_github_ignored_event_returns_none() -> None:
    payload = {"zen": "Speak like a human."}
    assert normalize_github_payload("ping", payload) is None


def test_github_bot_author_is_dropped() -> None:
    payload = {
        "action": "opened",
        "issue": {
            "number": 1,
            "title": "t",
            "body": "b",
            "user": {"login": "bot", "type": "Bot"},
            "labels": [],
        },
        "repository": {
            "name": "x",
            "default_branch": "main",
            "owner": {"login": "o"},
        },
    }
    assert normalize_github_payload("issues", payload) is None


def test_discord_message_normalizes() -> None:
    data = json.loads((FIXTURES / "discord_message.json").read_text())
    event = normalize_discord_message(
        message_id=data["message_id"],
        channel_id=data["channel_id"],
        guild_id=data["guild_id"],
        channel_name=data["channel_name"],
        author=data["author"],
        content=data["content"],
        repo=RepoRef(owner="acme", name="payments"),
    )
    assert event.source == "discord"
    assert event.external_id == "1103928172"
    assert event.metadata["channel_id"] == "987654321"
    assert event.metadata["channel_name"] == "bugs-payments"
    assert event.title.startswith("환불")
