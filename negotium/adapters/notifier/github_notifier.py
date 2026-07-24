"""Post the agent's proposal as a comment on the originating GitHub issue."""

from __future__ import annotations

import asyncio
from typing import Any

from negotium.domain.entities import IssueEvent
from negotium.observability import get_logger


class GitHubNotifier:
    def __init__(self, *, token: str, client: object | None = None) -> None:
        self._token = token
        self._client = client
        self._log = get_logger(component="notifier.github")

    async def reply(self, event: IssueEvent, markdown: str) -> None:
        if event.source != "github":
            return
        try:
            issue_number = int(event.external_id)
        except ValueError:
            self._log.warning("github.notify.invalid_id", external_id=event.external_id)
            return
        await asyncio.to_thread(self._post, event, issue_number, markdown)

    def _post(self, event: IssueEvent, issue_number: int, markdown: str) -> None:
        client = self._resolve_client()
        if client is None:
            self._log.warning("github.notify.skipped_no_client")
            return
        try:
            repo = client.get_repo(event.repo.full_name)
            issue = repo.get_issue(number=issue_number)
            issue.create_comment(markdown)
            self._log.info(
                "github.notify.commented",
                repo=event.repo.full_name,
                issue=issue_number,
            )
        except Exception:
            self._log.exception(
                "github.notify.failed",
                repo=event.repo.full_name,
                issue=issue_number,
            )

    def _resolve_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._token:
            return None
        from github import Github

        self._client = Github(self._token)
        return self._client
