"""Encrypted local storage for external API keys."""

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


@dataclass(frozen=True)
class ApiKeyRecord:
    provider: str
    api_key: str = ""
    model: str = ""
    base_url: str = ""

    @classmethod
    def from_mapping(cls, provider: str, payload: dict[str, Any]) -> ApiKeyRecord:
        return cls(
            provider=provider,
            api_key=str(payload.get("api_key") or ""),
            model=str(payload.get("model") or ""),
            base_url=str(payload.get("base_url") or ""),
        )

    def to_dict(self) -> dict[str, str]:
        return {"api_key": self.api_key, "model": self.model, "base_url": self.base_url}


class SecretStore:
    """Small encrypted file store.

    This is an MVP envelope encryption scheme using PBKDF2 + HMAC-derived XOR
    stream. It avoids plaintext secrets in the repo archive and can be replaced
    by Fernet/KMS without changing API callers.
    """

    def __init__(self, archive_dir: Path, *, master_key: str) -> None:
        self._path = archive_dir / "secrets" / "api_keys.enc.json"
        self._master_key = master_key

    @staticmethod
    def local_master_key(archive_dir: Path) -> str:
        path = archive_dir / "secrets" / "local_master.key"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        key = secrets.token_urlsafe(48)
        with portalocker.Lock(path, "w", encoding="utf-8", timeout=5) as fh:
            fh.write(key)
            fh.write("\n")
        path.chmod(0o600)
        return key

    def list_masked(self) -> list[dict[str, object]]:
        payload = self._read_payload()
        providers = ["solar", "openai", "anthropic", "gemini", "together", "vllm"]
        return [
            {
                "provider": provider,
                "configured": bool((payload.get(provider) or {}).get("api_key")),
                "masked_value": _mask(str((payload.get(provider) or {}).get("api_key") or "")),
                "model": str((payload.get(provider) or {}).get("model") or ""),
                "base_url": str((payload.get(provider) or {}).get("base_url") or ""),
            }
            for provider in providers
        ]

    def has_secret(self, provider: str) -> bool:
        record = self.read(provider)
        return bool(record and record.api_key)

    def upsert(self, record: ApiKeyRecord) -> None:
        payload = self._read_payload()
        payload[record.provider] = record.to_dict()
        self._write_payload(payload)

    def delete(self, provider: str) -> None:
        payload = self._read_payload()
        payload.pop(provider, None)
        self._write_payload(payload)

    def read(self, provider: str) -> ApiKeyRecord | None:
        payload = self._read_payload()
        raw = payload.get(provider)
        if not isinstance(raw, dict):
            return None
        return ApiKeyRecord.from_mapping(provider, raw)

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
            raise ValueError("encrypted API key store failed integrity check")
        plaintext = _xor(ciphertext, _keystream(key, nonce, len(ciphertext)))
        loaded = json.loads(plaintext.decode("utf-8"))
        return loaded if isinstance(loaded, dict) else {}

    def _write_payload(self, payload: dict[str, Any]) -> None:
        if not self._master_key:
            raise ValueError("NG_SECRET_KEY is required to store API keys")
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
            raise ValueError("NG_SECRET_KEY is required to read API keys")
        return hashlib.pbkdf2_hmac("sha256", self._master_key.encode("utf-8"), salt, 200_000)


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    chunks: list[bytes] = []
    counter = 0
    while sum(len(chunk) for chunk in chunks) < length:
        chunks.append(hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(chunks)[:length]


def _xor(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right, strict=True))


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
