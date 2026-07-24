"""Admin API routes (split from the former monolithic router)."""

from __future__ import annotations

from typing import Any

import portalocker
import yaml
from fastapi import APIRouter, Header, HTTPException, status

from negotium.adapters.llm.catalog import (
    require_provider,
)
from negotium.app.api._shared import (
    _access_control_payload,
    _audit,
    _default_base_url,
    _ensure_acl_keeps_admin_access,
    _masked_provider_payload,
    _require,
)
from negotium.app.container import Container
from negotium.app.schemas.core import (
    AccountRequestPayload,
    AdminCreateUserPayload,
    ApiKeyPayload,
    DepartmentPayload,
    DepartmentPermissionPayload,
    PositionPayload,
    RolePayload,
    UserPayload,
)
from negotium.app.services.context_firewall_service import (
    default_policy_payload,
    load_context_firewall_policy,
    record_firewall_audit,
    sanitize_context,
)
from negotium.archive.access_control import UserRecord
from negotium.archive.auth_store import RequestStatus
from negotium.archive.secret_store import ApiKeyRecord


def create_admin_router(container: Container) -> APIRouter:
    """Routes for the admin domain."""
    router = APIRouter()

    @router.post("/account-requests")
    async def create_account_request(payload: AccountRequestPayload) -> dict[str, object]:
        try:
            request = container.auth_store.request_account(
                user_id=payload.user_id.strip(),
                display_name=payload.display_name.strip(),
                title=payload.title.strip(),
                password=payload.password,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        _audit(
            container,
            actor="anonymous",
            action="account_request.create",
            target="account_request",
            target_id=request.id,
            details={"user_id": request.user_id},
        )
        return {"ok": True, "request": request.to_dict()}

    @router.post("/security/context-firewall/sanitize")
    async def sanitize_context_firewall(
        payload: dict[str, Any],
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        destination = str(payload.get("destination") or "frontier_llm")
        task_type = str(payload.get("task_type") or "manual_security_test")
        source_uri = str(payload.get("source_uri") or "")
        content = payload.get("content", payload.get("sources", payload))
        result = sanitize_context(
            content,
            destination=destination,
            task_type=task_type,
            source_uri=source_uri,
            policy=load_context_firewall_policy(container.settings.workspace_dir),
        )
        result = record_firewall_audit(
            container,
            result,
            actor=actor,
            agent_run_id=str(payload.get("agent_run_id") or ""),
            destination=destination,
            task_type=task_type,
        )
        return {"ok": True, "result": result.to_dict()}

    @router.get("/security/context-firewall/audit")
    async def list_context_firewall_audit(
        limit: int = 100,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "admin:users")
        records = container.context_firewall.list(limit=limit)
        return {"records": records, "count": len(records)}

    @router.get("/security/context-firewall/policy")
    async def read_context_firewall_policy(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "admin:users")
        return {"policy": default_policy_payload(container.settings.workspace_dir)}

    @router.put("/security/context-firewall/policy")
    async def save_context_firewall_policy(
        payload: dict[str, Any],
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        policy_path = container.settings.workspace_dir / ".patchnote-security.yml"
        body = {"context_firewall": payload.get("context_firewall") or payload}
        with portalocker.Lock(policy_path, "w", encoding="utf-8", timeout=5) as fh:
            fh.write(yaml.safe_dump(body, sort_keys=False, allow_unicode=True))
        _audit(
            container,
            actor=actor,
            action="context_firewall.policy_updated",
            target="security_policy",
            target_id=".patchnote-security.yml",
        )
        return {"ok": True, "policy": default_policy_payload(container.settings.workspace_dir)}

    @router.get("/org/roster")
    async def read_org_roster(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        acl = container.access_control.read()
        return {
            "users": [user for user in acl["users"] if user.get("active", True)],
            "departments": acl["departments"],
            "positions": acl["positions"],
        }

    @router.get("/admin/api-keys")
    async def list_api_keys(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "admin:api_keys")
        try:
            providers = _masked_provider_payload(container)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"providers": providers}

    @router.put("/admin/api-keys/{provider}")
    async def save_api_key(
        provider: str,
        payload: ApiKeyPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:api_keys")
        try:
            require_provider(provider)
            container.secret_store.upsert(
                ApiKeyRecord(
                    provider=provider,
                    api_key=payload.api_key.strip(),
                    model=payload.model.strip(),
                    base_url=_default_base_url(container, provider),
                )
            )
            _audit(
                container,
                actor=actor,
                action="api_key.upsert",
                target="api_key",
                target_id=provider,
                details={
                    "model": payload.model.strip(),
                    "configured": bool(payload.api_key.strip()),
                },
            )
            return {"ok": True, "providers": _masked_provider_payload(container)}
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @router.delete("/admin/api-keys/{provider}")
    async def delete_api_key(
        provider: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:api_keys")
        container.secret_store.delete(provider)
        _audit(
            container, actor=actor, action="api_key.delete", target="api_key", target_id=provider
        )
        return {"ok": True, "providers": _masked_provider_payload(container)}

    @router.get("/admin/access-control")
    async def read_access_control(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, Any]:
        _require(container, x_ng_user, "admin:users")
        return _access_control_payload(container)

    @router.post("/admin/roles")
    async def upsert_role(
        payload: RolePayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, Any]:
        actor = _require(container, x_ng_user, "admin:users")
        role = payload.to_record()
        _ensure_acl_keeps_admin_access(
            container.access_control.read(),
            roles_override=[role.to_dict()],
        )
        container.access_control.upsert_role(role)
        _audit(
            container,
            actor=actor,
            action="role.upsert",
            target="role",
            target_id=payload.id.strip(),
        )
        return _access_control_payload(container)

    @router.delete("/admin/roles/{role_id}")
    async def delete_role(
        role_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, Any]:
        actor = _require(container, x_ng_user, "admin:users")
        _ensure_acl_keeps_admin_access(
            container.access_control.read(),
            delete_role_id=role_id,
        )
        try:
            container.access_control.delete_role(role_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        _audit(container, actor=actor, action="role.delete", target="role", target_id=role_id)
        return _access_control_payload(container)

    @router.post("/admin/users")
    async def upsert_user(
        payload: UserPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, Any]:
        actor = _require(container, x_ng_user, "admin:users")
        acl = container.access_control.read()
        user = payload.to_record()
        _ensure_acl_keeps_admin_access(
            acl,
            users_override=[user.to_dict()],
        )
        container.access_control.upsert_user(user)
        _audit(
            container,
            actor=actor,
            action="user.upsert",
            target="user",
            target_id=payload.id.strip(),
        )
        return _access_control_payload(container)

    @router.post("/admin/users/create-login")
    async def create_login_user(
        payload: AdminCreateUserPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, Any]:
        actor = _require(container, x_ng_user, "admin:users")
        acl = container.access_control.read()
        user = payload.to_record()
        _ensure_acl_keeps_admin_access(
            acl,
            users_override=[user.to_dict()],
        )
        try:
            acl_user_exists = any(
                str(entry.get("id") or "") == user.id
                for entry in container.access_control.read().get("users", [])
            )
            if container.auth_store.has_user(user.id) and acl_user_exists:
                raise ValueError("login user id already exists")
            if container.auth_store.has_user(user.id):
                container.auth_store.delete_user(user.id)
            container.auth_store.create_user(
                user_id=user.id,
                display_name=user.display_name,
                password=payload.password,
                active=user.active,
            )
            container.access_control.upsert_user(user)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        _audit(
            container,
            actor=actor,
            action="user.create_login",
            target="user",
            target_id=user.id,
            details={
                "role_id": user.role_id,
                "department": user.department,
                "position_id": user.position_id,
            },
        )
        return {"ok": True, "access_control": _access_control_payload(container)}

    @router.delete("/admin/users/{user_id}")
    async def delete_user(
        user_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, Any]:
        actor = _require(container, x_ng_user, "admin:users")
        _ensure_acl_keeps_admin_access(
            container.access_control.read(),
            delete_user_id=user_id,
        )
        container.access_control.delete_user(user_id)
        container.auth_store.delete_user(user_id)
        _audit(container, actor=actor, action="user.delete", target="user", target_id=user_id)
        return _access_control_payload(container)

    @router.post("/admin/departments")
    async def upsert_department(
        payload: DepartmentPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, Any]:
        actor = _require(container, x_ng_user, "admin:users")
        try:
            container.access_control.upsert_department(payload.to_record())
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        _audit(
            container,
            actor=actor,
            action="department.upsert",
            target="department",
            target_id=payload.id.strip(),
        )
        return _access_control_payload(container)

    @router.delete("/admin/departments/{department_id}")
    async def delete_department(
        department_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, Any]:
        actor = _require(container, x_ng_user, "admin:users")
        container.access_control.delete_department(department_id)
        _audit(
            container,
            actor=actor,
            action="department.delete",
            target="department",
            target_id=department_id,
        )
        return _access_control_payload(container)

    @router.post("/admin/positions")
    async def upsert_position(
        payload: PositionPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, Any]:
        actor = _require(container, x_ng_user, "admin:users")
        try:
            container.access_control.upsert_position(payload.to_record())
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        _audit(
            container,
            actor=actor,
            action="position.upsert",
            target="position",
            target_id=payload.id.strip(),
        )
        return _access_control_payload(container)

    @router.delete("/admin/positions/{position_id}")
    async def delete_position(
        position_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, Any]:
        actor = _require(container, x_ng_user, "admin:users")
        container.access_control.delete_position(position_id)
        _audit(
            container,
            actor=actor,
            action="position.delete",
            target="position",
            target_id=position_id,
        )
        return _access_control_payload(container)

    @router.post("/admin/department-permissions")
    async def upsert_department_permission(
        payload: DepartmentPermissionPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, Any]:
        actor = _require(container, x_ng_user, "admin:users")
        try:
            container.access_control.upsert_department_permission(payload.to_record())
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        _audit(
            container,
            actor=actor,
            action="department_permission.upsert",
            target="department_permission",
            target_id=f"{payload.department_id}:{payload.position_id}",
        )
        return _access_control_payload(container)

    @router.get("/admin/account-requests")
    async def list_account_requests(
        status_filter: RequestStatus | None = None,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "admin:users")
        return {
            "requests": [
                request.to_dict()
                for request in container.auth_store.list_requests(status=status_filter)
            ]
        }

    @router.get("/admin/audit-log")
    async def list_audit_log(
        limit: int = 100,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "admin:users")
        return {"records": container.audit_log.list_recent(limit=max(1, min(limit, 500)))}

    @router.post("/admin/account-requests/{request_id}/approve")
    async def approve_account_request(
        request_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        admin_user = _require(container, x_ng_user, "admin:users")
        try:
            request = container.auth_store.decide_request(
                request_id,
                status="approved",
                decided_by=admin_user,
            )
            container.auth_store.create_user_with_hash(
                user_id=request.user_id,
                display_name=request.display_name,
                password_hash=request.password_hash,
            )
            container.access_control.upsert_user(
                UserRecord(
                    id=request.user_id,
                    display_name=request.display_name,
                    title=request.title,
                    role_id="viewer",
                    active=True,
                )
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        _audit(
            container,
            actor=admin_user,
            action="account_request.approve",
            target="account_request",
            target_id=request.id,
            details={"user_id": request.user_id},
        )
        return {"ok": True, "request": request.to_dict()}

    @router.post("/admin/account-requests/{request_id}/reject")
    async def reject_account_request(
        request_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        admin_user = _require(container, x_ng_user, "admin:users")
        try:
            request = container.auth_store.decide_request(
                request_id,
                status="rejected",
                decided_by=admin_user,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        _audit(
            container,
            actor=admin_user,
            action="account_request.reject",
            target="account_request",
            target_id=request.id,
            details={"user_id": request.user_id},
        )
        return {"ok": True, "request": request.to_dict()}

    return router
