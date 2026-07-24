"""FastAPI router for GitHub webhooks.

Responsibilities:
- HMAC (``X-Hub-Signature-256``) validation.
- Repo allowlist + label gate enforcement.
- Normalization into :class:`IssueEvent`.
- Enqueue into the :class:`EventBus` without blocking the webhook response.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from negotium.app.settings import GitHubSettings
from negotium.application.event_bus import EventBus, QueueFullError
from negotium.domain.entities import IssueEvent, RepoRef
from negotium.observability import get_logger


def normalize_github_payload(event: str, payload: dict[str, Any]) -> IssueEvent | None:
    """Convert a raw GitHub webhook payload into an ``IssueEvent``.

    Returns ``None`` for events we do not care about (non-issue events, edits
    that don't affect trigger criteria, bot authors, etc.). The caller responds
    with 202 Accepted in either case so GitHub doesn't mark the webhook as
    failing.
    """
    if event != "issues":
        return None
    action = payload.get("action")
    if action not in {"opened", "reopened", "labeled", "edited"}:
        return None
    issue = payload.get("issue") or {}
    repo = payload.get("repository") or {}
    if not issue or not repo:
        return None
    owner = (repo.get("owner") or {}).get("login") or ""
    name = repo.get("name") or ""
    if not owner or not name:
        return None
    user = (issue.get("user") or {}).get("login") or "unknown"
    if (issue.get("user") or {}).get("type") == "Bot":
        return None
    labels = [label.get("name", "") for label in issue.get("labels", []) if label.get("name")]
    return IssueEvent(
        source="github",
        external_id=str(issue.get("number")),
        repo=RepoRef(
            owner=owner,
            name=name,
            default_branch=repo.get("default_branch", "main"),
        ),
        title=issue.get("title") or "(no title)",
        body=issue.get("body") or "",
        author=user,
        labels=labels,
        metadata={"html_url": issue.get("html_url", "")},
    )


class GitHubWebhookRouter:
    """Composes a FastAPI ``APIRouter`` with the dependencies injected.

    We wrap the router in a class so the DI container can pass the live bus
    and settings without relying on FastAPI-global state.
    """

    def __init__(self, *, bus: EventBus, settings: GitHubSettings) -> None:
        self._bus = bus
        self._settings = settings
        self._log = get_logger(component="ingestion.github")
        self.router = APIRouter()
        self.router.add_api_route(
            "/webhooks/github",
            self._handle,
            methods=["POST"],
            name="github_webhook",
        )

    async def _handle(
        self,
        request: Request,
        x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
        x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    ) -> JSONResponse:
        raw = await request.body()
        self._verify_signature(raw, x_hub_signature_256)
        if x_github_event == "ping":
            return JSONResponse({"ok": True, "pong": True})
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid json") from exc

        event = normalize_github_payload(x_github_event or "", payload)
        if event is None:
            return JSONResponse({"ok": True, "accepted": False, "reason": "ignored"})
        if not self._is_allowed(event):
            return JSONResponse({"ok": True, "accepted": False, "reason": "not_allowed"})

        try:
            envelope = self._bus.publish_nowait(event)
        except QueueFullError:
            return JSONResponse(
                {"ok": False, "reason": "queue_full"},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        self._log.info(
            "github.webhook.accepted",
            repo=event.repo.full_name,
            issue=event.external_id,
            trace_id=str(envelope.trace_id),
        )
        return JSONResponse({"ok": True, "accepted": True, "event_id": str(event.event_id)})

    def _verify_signature(self, raw_body: bytes, signature: str | None) -> None:
        secret = self._settings.webhook_secret.encode("utf-8")
        if not secret or secret == b"change-me":
            self._log.warning("github.webhook.no_secret_configured")
            return
        if not signature or not signature.startswith("sha256="):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing signature")
        provided = signature.split("=", 1)[1]
        expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided, expected):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid signature")

    def _is_allowed(self, event: IssueEvent) -> bool:
        allowlist = self._settings.allowed_repos
        if allowlist and event.repo.full_name not in allowlist:
            self._log.info(
                "github.webhook.repo_rejected",
                repo=event.repo.full_name,
            )
            return False
        label = self._settings.trigger_label
        if label and label not in event.labels:
            self._log.info(
                "github.webhook.label_missing",
                repo=event.repo.full_name,
                issue=event.external_id,
                required=label,
            )
            return False
        return True
