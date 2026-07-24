"""JSON API routes for the local frontend, aggregated from domain routers."""

from __future__ import annotations

from fastapi import APIRouter

# Re-exported for services/CLI that historically imported these helpers from here.
from negotium.app.api._shared import (
    _build_chat_messages,
    _complete_office_task,
    _complete_patchops_task,
    _complete_with_provider,
    _fetch_discord_status,
    _fetch_github_status,
    _generate_hiring_document,
    _initial_office_setup_prompt,
    _is_slash_command,
    _parse_chat_slash,
    _parse_initial_setup_result,
    _require,
    _resolve_runtime_model,
    _resolve_runtime_task,
    _resolve_task_model,
    _try_load_json_object,
    _update_user_volatile_memory_after_chat,
    _write_generated_doc,
)
from negotium.app.api.admin import create_admin_router
from negotium.app.api.agent import create_agent_router
from negotium.app.api.auth import create_auth_router
from negotium.app.api.documents import create_documents_router
from negotium.app.api.integrations import create_integrations_router
from negotium.app.api.llm import create_llm_router
from negotium.app.api.memory import create_memory_router
from negotium.app.api.patchops_execution import create_patchops_execution_router
from negotium.app.api.setup import create_setup_router
from negotium.app.api.uploads import create_uploads_router
from negotium.app.api.work import create_work_router
from negotium.app.container import Container

__all__ = [
    "_build_chat_messages",
    "_complete_office_task",
    "_complete_patchops_task",
    "_complete_with_provider",
    "_fetch_discord_status",
    "_fetch_github_status",
    "_generate_hiring_document",
    "_initial_office_setup_prompt",
    "_is_slash_command",
    "_parse_chat_slash",
    "_parse_initial_setup_result",
    "_require",
    "_resolve_runtime_model",
    "_resolve_runtime_task",
    "_resolve_task_model",
    "_try_load_json_object",
    "_update_user_volatile_memory_after_chat",
    "_write_generated_doc",
    "create_admin_router",
    "create_agent_router",
    "create_auth_router",
    "create_documents_router",
    "create_integrations_router",
    "create_llm_router",
    "create_memory_router",
    "create_operations_api_router",
    "create_patchops_execution_router",
    "create_setup_router",
    "create_uploads_router",
    "create_work_router",
]


def create_operations_api_router(container: Container) -> APIRouter:
    """Create frontend-facing API routes bound to the app container."""
    router = APIRouter(prefix="/api", tags=["frontend-api"])
    router.include_router(create_patchops_execution_router(container))
    router.include_router(create_auth_router(container))
    router.include_router(create_setup_router(container))
    router.include_router(create_uploads_router(container))
    router.include_router(create_documents_router(container))
    router.include_router(create_integrations_router(container))
    router.include_router(create_llm_router(container))
    router.include_router(create_work_router(container))
    router.include_router(create_agent_router(container))
    router.include_router(create_admin_router(container))
    router.include_router(create_memory_router(container))
    return router
