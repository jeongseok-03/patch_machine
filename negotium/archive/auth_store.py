"""Local password credentials, sessions, and account requests."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, TypedDict

import portalocker

SESSION_TTL = timedelta(hours=12)
PASSWORD_ITERATIONS = 200_000
RequestStatus = Literal["pending", "approved", "rejected"]


class AuthPayload(TypedDict):
    users: list[AuthUser]
    sessions: list[SessionRecord]
    requests: list[AccountRequest]


@dataclass(frozen=True)
class AuthUser:
    id: str
    display_name: str
    password_hash: str
    active: bool = True

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> AuthUser:
        return cls(
            id=str(payload.get("id") or ""),
            display_name=str(payload.get("display_name") or ""),
            password_hash=str(payload.get("password_hash") or ""),
            active=bool(payload.get("active", True)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "password_hash": self.password_hash,
            "active": self.active,
        }


@dataclass(frozen=True)
class SessionRecord:
    token_hash: str
    user_id: str
    expires_at: str

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> SessionRecord:
        return cls(
            token_hash=str(payload.get("token_hash") or ""),
            user_id=str(payload.get("user_id") or ""),
            expires_at=str(payload.get("expires_at") or ""),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "token_hash": self.token_hash,
            "user_id": self.user_id,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class AccountRequest:
    id: str
    user_id: str
    display_name: str
    title: str
    password_hash: str
    status: RequestStatus
    created_at: str
    decided_at: str = ""
    decided_by: str = ""

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> AccountRequest:
        status = str(payload.get("status") or "pending")
        if status not in {"pending", "approved", "rejected"}:
            status = "pending"
        return cls(
            id=str(payload.get("id") or ""),
            user_id=str(payload.get("user_id") or ""),
            display_name=str(payload.get("display_name") or ""),
            title=str(payload.get("title") or ""),
            password_hash=str(payload.get("password_hash") or ""),
            status=status,  # type: ignore[arg-type]
            created_at=str(payload.get("created_at") or ""),
            decided_at=str(payload.get("decided_at") or ""),
            decided_by=str(payload.get("decided_by") or ""),
        )

    def to_dict(self, *, include_password_hash: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "user_id": self.user_id,
            "display_name": self.display_name,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
        }
        if include_password_hash:
            payload["password_hash"] = self.password_hash
        return payload


class AuthStore:
    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "auth.json"

    def setup_required(self) -> bool:
        payload = self._read_payload()
        return not any(user.active for user in payload["users"])

    def has_user(self, user_id: str) -> bool:
        return any(user.id == user_id for user in self._read_payload()["users"])

    def delete_user(self, user_id: str) -> bool:
        payload = self._read_payload()
        before = len(payload["users"])
        payload["users"] = [user for user in payload["users"] if user.id != user_id]
        payload["sessions"] = [
            session for session in payload["sessions"] if session.user_id != user_id
        ]
        deleted = len(payload["users"]) != before
        if deleted:
            self._write_payload(payload)
        return deleted

    def create_user(
        self, *, user_id: str, display_name: str, password: str, active: bool = True
    ) -> None:
        self.create_user_with_hash(
            user_id=user_id,
            display_name=display_name,
            password_hash=_hash_password(password),
            active=active,
        )

    def create_user_with_hash(
        self,
        *,
        user_id: str,
        display_name: str,
        password_hash: str,
        active: bool = True,
    ) -> None:
        _validate_user_id(user_id)
        if not display_name.strip():
            raise ValueError("display name is required")
        payload = self._read_payload()
        users = [user for user in payload["users"] if user.id != user_id]
        users.append(AuthUser(user_id, display_name.strip(), password_hash, active))
        payload["users"] = users
        self._write_payload(payload)

    def authenticate(self, user_id: str, password: str) -> str | None:
        payload = self._read_payload()
        user = next((candidate for candidate in payload["users"] if candidate.id == user_id), None)
        if user is None or not user.active or not _verify_password(password, user.password_hash):
            return None
        token = secrets.token_urlsafe(32)
        sessions = _active_sessions(payload["sessions"])
        sessions.append(
            SessionRecord(
                token_hash=_hash_token(token),
                user_id=user.id,
                expires_at=(datetime.now(UTC) + SESSION_TTL).isoformat(),
            )
        )
        payload["sessions"] = sessions
        self._write_payload(payload)
        return token

    def resolve_token(self, token: str) -> str | None:
        if not token:
            return None
        payload = self._read_payload()
        token_hash = _hash_token(token)
        sessions = _active_sessions(payload["sessions"])
        changed = len(sessions) != len(payload["sessions"])
        match = next((session for session in sessions if session.token_hash == token_hash), None)
        if changed:
            payload["sessions"] = sessions
            self._write_payload(payload)
        if match is None:
            return None
        user = next(
            (candidate for candidate in payload["users"] if candidate.id == match.user_id), None
        )
        if user is None or not user.active:
            return None
        return user.id

    def revoke_token(self, token: str) -> None:
        token_hash = _hash_token(token)
        payload = self._read_payload()
        payload["sessions"] = [
            session for session in payload["sessions"] if session.token_hash != token_hash
        ]
        self._write_payload(payload)

    def request_account(
        self, *, user_id: str, display_name: str, title: str, password: str
    ) -> AccountRequest:
        _validate_user_id(user_id)
        if not display_name.strip():
            raise ValueError("display name is required")
        payload = self._read_payload()
        if any(user.id == user_id for user in payload["users"]):
            raise ValueError("user id already exists")
        if any(
            request.user_id == user_id and request.status == "pending"
            for request in payload["requests"]
        ):
            raise ValueError("account request is already pending")
        request = AccountRequest(
            id=secrets.token_urlsafe(12),
            user_id=user_id,
            display_name=display_name.strip(),
            title=title.strip(),
            password_hash=_hash_password(password),
            status="pending",
            created_at=datetime.now(UTC).isoformat(),
        )
        payload["requests"].append(request)
        self._write_payload(payload)
        return request

    def list_requests(self, *, status: RequestStatus | None = None) -> list[AccountRequest]:
        requests = self._read_payload()["requests"]
        if status is None:
            return requests
        return [request for request in requests if request.status == status]

    def decide_request(
        self, request_id: str, *, status: Literal["approved", "rejected"], decided_by: str
    ) -> AccountRequest:
        payload = self._read_payload()
        requests = payload["requests"]
        target = next((request for request in requests if request.id == request_id), None)
        if target is None:
            raise ValueError("account request not found")
        if target.status != "pending":
            raise ValueError("account request is already decided")
        decided = AccountRequest(
            id=target.id,
            user_id=target.user_id,
            display_name=target.display_name,
            title=target.title,
            password_hash=target.password_hash,
            status=status,
            created_at=target.created_at,
            decided_at=datetime.now(UTC).isoformat(),
            decided_by=decided_by,
        )
        payload["requests"] = [
            decided if request.id == request_id else request for request in requests
        ]
        self._write_payload(payload)
        return decided

    def _read_payload(self) -> AuthPayload:
        if not self._path.exists():
            return {"users": [], "sessions": [], "requests": []}
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return {"users": [], "sessions": [], "requests": []}
        payload = json.loads(raw)
        return {
            "users": [AuthUser.from_mapping(item) for item in payload.get("users", [])],
            "sessions": [SessionRecord.from_mapping(item) for item in payload.get("sessions", [])],
            "requests": [AccountRequest.from_mapping(item) for item in payload.get("requests", [])],
        }

    def _write_payload(
        self,
        payload: AuthPayload,
    ) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        rendered = {
            "users": [user.to_dict() for user in payload["users"]],
            "sessions": [session.to_dict() for session in payload["sessions"]],
            "requests": [
                request.to_dict(include_password_hash=True) for request in payload["requests"]
            ],
        }
        with portalocker.Lock(self._path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump(rendered, fh, ensure_ascii=False, indent=2)
            fh.write("\n")


def _hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            base64.b64decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(expected, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _active_sessions(sessions: list[SessionRecord]) -> list[SessionRecord]:
    now = datetime.now(UTC)
    active: list[SessionRecord] = []
    for session in sessions:
        try:
            expires_at = datetime.fromisoformat(session.expires_at)
        except ValueError:
            continue
        if expires_at > now:
            active.append(session)
    return active


def _validate_user_id(user_id: str) -> None:
    if not user_id or not all(char.isalnum() or char in "._-" for char in user_id):
        raise ValueError("user id may contain only letters, numbers, dot, underscore, and hyphen")
