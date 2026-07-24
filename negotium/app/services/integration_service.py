"""Integration status service boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from negotium.app.container import Container
    from negotium.app.schemas import IntegrationStatusPayload


async def fetch_github_status(container: Container) -> IntegrationStatusPayload:
    from negotium.app.api import _fetch_github_status

    return await _fetch_github_status(container)


async def fetch_discord_status(container: Container) -> IntegrationStatusPayload:
    from negotium.app.api import _fetch_discord_status

    return await _fetch_discord_status(container)
