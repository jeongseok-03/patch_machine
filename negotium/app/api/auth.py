"""Auth API routes (split from the former monolithic router)."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status

from negotium.app.api._shared import (
    _audit,
    _extract_token,
    _resolve_authenticated_user,
    _user_payload,
)
from negotium.app.container import Container
from negotium.app.schemas.core import (
    AuthSessionPayload,
    CurrentUserPayload,
    LoginPayload,
    SetupAdminPayload,
    SetupStatusPayload,
)
from negotium.archive.access_control import UserRecord


def create_auth_router(container: Container) -> APIRouter:
    """Routes for the auth domain."""
    router = APIRouter()

    @router.get("/auth/setup-status")
    async def setup_status() -> SetupStatusPayload:
        return SetupStatusPayload(setup_required=container.auth_store.setup_required())

    @router.post("/auth/setup-admin")
    async def setup_admin(payload: SetupAdminPayload) -> AuthSessionPayload:
        if not container.auth_store.setup_required():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="admin user is already configured"
            )
        try:
            container.auth_store.create_user(
                user_id=payload.user_id.strip(),
                display_name=payload.display_name.strip(),
                password=payload.password,
            )
            container.access_control.upsert_user(
                UserRecord(
                    id=payload.user_id.strip(),
                    display_name=payload.display_name.strip(),
                    title=payload.title.strip() or "관리자",
                    role_id="owner",
                    active=True,
                )
            )
            token = container.auth_store.authenticate(payload.user_id.strip(), payload.password)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if token is None:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, detail="failed to create admin session"
            )
        _audit(
            container,
            actor=payload.user_id.strip(),
            action="auth.setup_admin",
            target="user",
            target_id=payload.user_id.strip(),
        )
        return AuthSessionPayload(
            token=token, user=_user_payload(container, payload.user_id.strip())
        )

    @router.post("/auth/login")
    async def login(payload: LoginPayload) -> AuthSessionPayload:
        token = container.auth_store.authenticate(payload.user_id.strip(), payload.password)
        if token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid user id or password")
        return AuthSessionPayload(
            token=token, user=_user_payload(container, payload.user_id.strip())
        )

    @router.post("/auth/logout")
    async def logout(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, bool]:
        token = _extract_token(x_ng_user)
        if token:
            container.auth_store.revoke_token(token)
        return {"ok": True}

    @router.get("/auth/me")
    async def me(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> CurrentUserPayload:
        user_id = _resolve_authenticated_user(container, x_ng_user)
        if user_id is None:
            return CurrentUserPayload(authenticated=False)
        return CurrentUserPayload(authenticated=True, user=_user_payload(container, user_id))

    return router
