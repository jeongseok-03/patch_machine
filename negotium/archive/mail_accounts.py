"""Per-user mail account credentials, encrypted at rest.

Reuses the SecretStore envelope scheme (PBKDF2 + HMAC keystream) with its own
file so mail passwords never sit in plaintext inside ``archive/``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import portalocker

from negotium.archive.secret_store import _keystream, _xor


@dataclass(frozen=True)
class MailAccount:
    email: str = ""
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 465
    username: str = ""
    password: str = ""

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> MailAccount:
        return cls(
            email=str(payload.get("email") or ""),
            imap_host=str(payload.get("imap_host") or ""),
            imap_port=int(payload.get("imap_port") or 993),
            smtp_host=str(payload.get("smtp_host") or ""),
            smtp_port=int(payload.get("smtp_port") or 465),
            username=str(payload.get("username") or ""),
            password=str(payload.get("password") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "email": self.email,
            "imap_host": self.imap_host,
            "imap_port": self.imap_port,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "username": self.username,
            "password": self.password,
        }

    def masked(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload["password"] = "****" if self.password else ""
        payload["configured"] = bool(self.email and self.imap_host and self.password)
        return payload


class MailAccountStore:
    """Encrypted per-user mail credentials."""

    def __init__(self, archive_dir: Path, *, master_key: str) -> None:
        self._path = archive_dir / "secrets" / "mail_accounts.enc.json"
        self._master_key = master_key

    def read(self, user_id: str) -> MailAccount | None:
        payload = self._read_payload()
        raw = payload.get(user_id)
        if not isinstance(raw, dict):
            return None
        return MailAccount.from_mapping(raw)

    def upsert(self, user_id: str, account: MailAccount) -> None:
        payload = self._read_payload()
        payload[user_id] = account.to_dict()
        self._write_payload(payload)

    def delete(self, user_id: str) -> None:
        payload = self._read_payload()
        payload.pop(user_id, None)
        self._write_payload(payload)

    def _read_payload(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        envelope = json.loads(self._path.read_text(encoding="utf-8"))
        salt = base64.b64decode(envelope["salt"])
        nonce = base64.b64decode(envelope["nonce"])
        ciphertext = base64.b64decode(envelope["ciphertext"])
        digest = base64.b64decode(envelope["hmac"])
        key = self._derive_key(salt)
        expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, digest):
            raise ValueError("encrypted mail account store failed integrity check")
        plaintext = _xor(ciphertext, _keystream(key, nonce, len(ciphertext)))
        loaded = json.loads(plaintext.decode("utf-8"))
        return loaded if isinstance(loaded, dict) else {}

    def _write_payload(self, payload: dict[str, Any]) -> None:
        if not self._master_key:
            raise ValueError("NG_SECRET_KEY is required to store mail accounts")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(16)
        key = self._derive_key(salt)
        plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ciphertext = _xor(plaintext, _keystream(key, nonce, len(plaintext)))
        digest = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        envelope = {
            "salt": base64.b64encode(salt).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "hmac": base64.b64encode(digest).decode("ascii"),
        }
        with portalocker.Lock(self._path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump(envelope, fh, indent=2, sort_keys=True)
            fh.write("\n")

    def _derive_key(self, salt: bytes) -> bytes:
        if not self._master_key:
            raise ValueError("NG_SECRET_KEY is required to read mail accounts")
        return hashlib.pbkdf2_hmac("sha256", self._master_key.encode("utf-8"), salt, 200_000)
