"""Integrations API routes (split from the former monolithic router)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from negotium.app.api._shared import (
    _audit,
    _fetch_discord_status,
    _fetch_github_status,
    _integration_config_payload,
    _require,
    _save_discord_secrets,
    _save_github_secrets,
)
from negotium.app.container import Container
from negotium.app.schemas.core import (
    DiscordConnectorPayload,
    GitHubConnectorPayload,
    IntegrationConfigPayload,
    IntegrationStatusPayload,
)
from negotium.app.schemas.issue_memory import (
    McpToolCallPayload,
)
from negotium.app.services.mcp_hub_service import (
    call_tool,
    handle_json_rpc,
    list_prompts,
    list_resources,
    list_tool_descriptors,
    read_resource,
    record_mcp_audit,
    render_mcp_prompt,
    required_permission,
)
from negotium.archive.integration_config import (
    DiscordChannelBindingConfig,
    DiscordConnectorConfig,
    GitHubConnectorConfig,
)


def create_integrations_router(container: Container) -> APIRouter:
    """Routes for the integrations domain."""
    router = APIRouter()

    @router.get("/mcp-hub/tools")
    async def list_mcp_hub_tools(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        tools = list_tool_descriptors()
        return {
            "tools": tools,
            "transport": "http-compatible+json-rpc+sse-skeleton",
            "count": len(tools),
        }

    @router.post("/mcp-hub/tools/{tool_name:path}")
    async def call_mcp_hub_tool(
        tool_name: str,
        payload: McpToolCallPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        permission = required_permission(tool_name)
        actor = _require(container, x_ng_user, permission)
        try:
            call_result = call_tool(container, tool_name, payload.arguments)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        record_mcp_audit(
            container,
            actor=actor,
            tool_name=tool_name,
            arguments=payload.arguments,
            result_summary=call_result.result_summary,
            risk_level=call_result.risk_level,
            policy=call_result.policy,
            guard_findings=call_result.guard_findings,
        )
        _audit(
            container,
            actor=actor,
            action="mcp_hub.tool_call",
            target="mcp_tool",
            target_id=tool_name,
            details={
                "tool_name": tool_name,
                "arguments": payload.arguments,
                "result_summary": call_result.result_summary,
                "risk_level": call_result.risk_level,
                "guard_findings": call_result.guard_findings,
            },
        )
        return {"ok": True, "tool": tool_name, "result": call_result.result}

    @router.get("/mcp-hub/resources")
    async def list_mcp_hub_resources(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        resources = list_resources(container)
        return {"resources": resources, "count": len(resources)}

    @router.get("/mcp-hub/resources/{resource_uri:path}")
    async def read_mcp_hub_resource(
        resource_uri: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        try:
            return read_resource(container, resource_uri)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @router.get("/mcp-hub/prompts")
    async def list_mcp_hub_prompts(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        prompts = list_prompts()
        return {"prompts": prompts, "count": len(prompts)}

    @router.get("/mcp-hub/audit")
    async def list_mcp_hub_audit(
        limit: int = 100,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "admin:users")
        records = container.mcp_audit.list(limit=limit)
        return {"records": records, "count": len(records)}

    @router.post("/mcp-hub/prompts/{prompt_name}")
    async def render_mcp_hub_prompt(
        prompt_name: str,
        payload: McpToolCallPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        try:
            prompt = render_mcp_prompt(prompt_name, payload.arguments, container)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return {"ok": True, "prompt": prompt}

    @router.post("/mcp")
    async def call_mcp_json_rpc(
        payload: dict[str, Any],
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        method = str(payload.get("method") or "")
        raw_params = payload.get("params")
        params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
        if method == "tools/call":
            tool_name = str(params.get("name") or "")
            actor = _require(container, x_ng_user, required_permission(tool_name))
            raw_arguments = params.get("arguments")
            arguments: dict[str, Any] = raw_arguments if isinstance(raw_arguments, dict) else {}
            try:
                call_result = call_tool(container, tool_name, arguments)
            except ValueError as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "error": {"code": -32602, "message": str(exc)},
                }
            record_mcp_audit(
                container,
                actor=actor,
                tool_name=tool_name,
                arguments=arguments,
                result_summary=call_result.result_summary,
                risk_level=call_result.risk_level,
                policy=call_result.policy,
                guard_findings=call_result.guard_findings,
            )
            return {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {
                    "content": [{"type": "json", "json": call_result.result}],
                    "isError": False,
                },
            }
        _require(container, x_ng_user, "work:read")
        return handle_json_rpc(container, payload)

    @router.get("/mcp/sse")
    async def mcp_sse(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> StreamingResponse:
        _require(container, x_ng_user, "work:read")

        async def events() -> AsyncIterator[str]:
            yield 'event: metadata\ndata: {"name":"patchnote-mcp-hub","transport":"sse-skeleton"}\n\n'
            yield 'event: heartbeat\ndata: {"ok":true}\n\n'

        return StreamingResponse(events(), media_type="text/event-stream")

    @router.get("/integrations/github")
    async def read_github_status() -> IntegrationStatusPayload:
        return await _fetch_github_status(container)

    @router.get("/integrations/discord")
    async def read_discord_status() -> IntegrationStatusPayload:
        return await _fetch_discord_status(container)

    @router.get("/integrations/config")
    async def read_integration_config(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> IntegrationConfigPayload:
        _require(container, x_ng_user, "admin:integrations")
        return _integration_config_payload(container)

    @router.put("/integrations/github")
    async def upsert_github_connector(
        payload: GitHubConnectorPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> IntegrationConfigPayload:
        actor = _require(container, x_ng_user, "admin:integrations")
        _save_github_secrets(container, payload)
        config = container.integration_config.update_github(
            GitHubConnectorConfig(
                enabled=payload.enabled,
                allowed_repos=[repo.strip() for repo in payload.allowed_repos if repo.strip()],
                trigger_label=payload.trigger_label.strip() or "negotium",
                webhook_secret_present=container.secret_store.has_secret("github_webhook"),
                app_token_present=container.secret_store.has_secret("github_app"),
                event_forms=[item.strip() for item in payload.event_forms if item.strip()]
                or ["issue", "pull_request", "repository", "push"],
            )
        )
        _audit(
            container,
            actor=actor,
            action="integration.github.update",
            target="integration",
            target_id="github",
        )
        return _integration_config_payload(container, config=config)

    @router.put("/integrations/discord")
    async def upsert_discord_connector(
        payload: DiscordConnectorPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> IntegrationConfigPayload:
        actor = _require(container, x_ng_user, "admin:integrations")
        _save_discord_secrets(container, payload)
        bindings: list[DiscordChannelBindingConfig] = []
        for binding in payload.channel_bindings:
            channel_id = binding.channel_id.strip()
            if not channel_id:
                continue
            bindings.append(
                DiscordChannelBindingConfig(
                    guild_id=binding.guild_id.strip(),
                    channel_id=channel_id,
                    channel_name=binding.channel_name.strip(),
                    repo=binding.repo.strip(),
                )
            )
        config = container.integration_config.update_discord(
            DiscordConnectorConfig(
                enabled=payload.enabled,
                bot_token_present=container.secret_store.has_secret("discord_bot"),
                guild_allowlist=[item.strip() for item in payload.guild_allowlist if item.strip()],
                channel_bindings=bindings,
                command_forms=[item.strip() for item in payload.command_forms if item.strip()]
                or ["bug_report", "thread_digest", "slash_command"],
            )
        )
        _audit(
            container,
            actor=actor,
            action="integration.discord.update",
            target="integration",
            target_id="discord",
        )
        return _integration_config_payload(container, config=config)

    return router
