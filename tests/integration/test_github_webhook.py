"""Integration test: POST to /webhooks/github → EventBus enqueue."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from negotium.adapters.ingestion.github_webhook import GitHubWebhookRouter
from negotium.app.settings import GitHubSettings
from negotium.application.event_bus import EventBus

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
_SECRET = "topsecret"


def _sign(payload: bytes) -> str:
    return "sha256=" + hmac.new(_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _make_app(bus: EventBus, *, allowlist: list[str] | None = None) -> FastAPI:
    settings = GitHubSettings(
        webhook_secret=_SECRET,
        allowed_repos=allowlist or [],
        trigger_label="negotium",
    )
    router = GitHubWebhookRouter(bus=bus, settings=settings)
    app = FastAPI()
    app.include_router(router.router)
    return app


def test_valid_signature_enqueues_event() -> None:
    bus = EventBus(max_size=8)
    app = _make_app(bus)
    client = TestClient(app)

    raw_body = (FIXTURES / "github_issue_opened.json").read_bytes()
    headers = {
        "X-Hub-Signature-256": _sign(raw_body),
        "X-GitHub-Event": "issues",
        "Content-Type": "application/json",
    }
    resp = client.post("/webhooks/github", headers=headers, content=raw_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is True
    assert bus.size == 1


def test_invalid_signature_returns_401() -> None:
    bus = EventBus(max_size=8)
    app = _make_app(bus)
    client = TestClient(app)

    raw_body = (FIXTURES / "github_issue_opened.json").read_bytes()
    headers = {
        "X-Hub-Signature-256": "sha256=deadbeef",
        "X-GitHub-Event": "issues",
        "Content-Type": "application/json",
    }
    resp = client.post("/webhooks/github", headers=headers, content=raw_body)
    assert resp.status_code == 401
    assert bus.size == 0


def test_missing_label_is_rejected_but_200() -> None:
    bus = EventBus(max_size=8)
    app = _make_app(bus)
    client = TestClient(app)
    payload = json.loads((FIXTURES / "github_issue_opened.json").read_text())
    payload["issue"]["labels"] = [{"name": "bug"}]
    raw_body = json.dumps(payload).encode("utf-8")
    headers = {
        "X-Hub-Signature-256": _sign(raw_body),
        "X-GitHub-Event": "issues",
        "Content-Type": "application/json",
    }
    resp = client.post("/webhooks/github", headers=headers, content=raw_body)
    assert resp.status_code == 200
    assert resp.json()["accepted"] is False
    assert bus.size == 0


def test_allowlist_blocks_unknown_repo() -> None:
    bus = EventBus(max_size=8)
    app = _make_app(bus, allowlist=["other/one"])
    client = TestClient(app)
    raw_body = (FIXTURES / "github_issue_opened.json").read_bytes()
    headers = {
        "X-Hub-Signature-256": _sign(raw_body),
        "X-GitHub-Event": "issues",
        "Content-Type": "application/json",
    }
    resp = client.post("/webhooks/github", headers=headers, content=raw_body)
    assert resp.status_code == 200
    assert resp.json()["accepted"] is False
    assert bus.size == 0
