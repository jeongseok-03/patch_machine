"""Persistent token usage tracking and per-day/month limits."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import portalocker


@dataclass(frozen=True)
class TokenLimitConfig:
    enforcement_enabled: bool = True
    per_request_max_tokens: int = 4000
    daily_total_tokens: int = 200_000
    monthly_total_tokens: int = 4_000_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "enforcement_enabled": self.enforcement_enabled,
            "per_request_max_tokens": self.per_request_max_tokens,
            "daily_total_tokens": self.daily_total_tokens,
            "monthly_total_tokens": self.monthly_total_tokens,
        }

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> TokenLimitConfig:
        payload = payload or {}
        return cls(
            enforcement_enabled=bool(payload.get("enforcement_enabled", True)),
            per_request_max_tokens=int(payload.get("per_request_max_tokens", 4000) or 0),
            daily_total_tokens=int(payload.get("daily_total_tokens", 200_000) or 0),
            monthly_total_tokens=int(payload.get("monthly_total_tokens", 4_000_000) or 0),
        )


@dataclass(frozen=True)
class TokenUsageEntry:
    provider: str = ""
    model: str = ""
    task: str = ""
    actor: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    occurred_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "task": self.task,
            "actor": self.actor,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "occurred_at": self.occurred_at,
        }


@dataclass(frozen=True)
class TokenUsageSummary:
    daily_total: int = 0
    monthly_total: int = 0
    by_provider: dict[str, int] = field(default_factory=dict)
    by_task: dict[str, int] = field(default_factory=dict)
    by_actor: dict[str, int] = field(default_factory=dict)
    recent: list[TokenUsageEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "daily_total": self.daily_total,
            "monthly_total": self.monthly_total,
            "by_provider": dict(self.by_provider),
            "by_task": dict(self.by_task),
            "by_actor": dict(self.by_actor),
            "recent": [entry.to_dict() for entry in self.recent],
        }


class TokenLimitExceededError(RuntimeError):
    """Raised when the configured token budget would be exceeded."""

    def __init__(
        self,
        message: str,
        *,
        scope: str,
        limit: int,
        current: int,
        attempted: int,
    ) -> None:
        super().__init__(message)
        self.scope = scope
        self.limit = limit
        self.current = current
        self.attempted = attempted


class TokenUsageStore:
    """Per-day token usage with limits and historical entries."""

    def __init__(self, archive_dir: Path) -> None:
        self._root = archive_dir / "token_usage"
        self._limits_path = self._root / "limits.json"
        self._daily_dir = self._root / "daily"

    @property
    def limits_path(self) -> Path:
        return self._limits_path

    def read_limits(self) -> TokenLimitConfig:
        if not self._limits_path.exists():
            return TokenLimitConfig()
        try:
            payload = json.loads(self._limits_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return TokenLimitConfig()
        if not isinstance(payload, dict):
            return TokenLimitConfig()
        return TokenLimitConfig.from_mapping(payload)

    def write_limits(self, limits: TokenLimitConfig) -> TokenLimitConfig:
        self._limits_path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(self._limits_path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump(limits.to_dict(), fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        return limits

    def check_limits(
        self,
        *,
        attempted_tokens: int,
        now: datetime | None = None,
    ) -> None:
        limits = self.read_limits()
        if not limits.enforcement_enabled:
            return
        if limits.per_request_max_tokens > 0 and attempted_tokens > limits.per_request_max_tokens:
            raise TokenLimitExceededError(
                f"per-request token budget {limits.per_request_max_tokens} exceeded "
                f"(attempted {attempted_tokens})",
                scope="per_request",
                limit=limits.per_request_max_tokens,
                current=0,
                attempted=attempted_tokens,
            )
        moment = now or datetime.now(UTC)
        summary = self.summary(now=moment)
        if (
            limits.daily_total_tokens > 0
            and summary.daily_total + attempted_tokens > limits.daily_total_tokens
        ):
            raise TokenLimitExceededError(
                f"daily token budget {limits.daily_total_tokens} would be exceeded "
                f"(used {summary.daily_total}, attempted {attempted_tokens})",
                scope="daily",
                limit=limits.daily_total_tokens,
                current=summary.daily_total,
                attempted=attempted_tokens,
            )
        if (
            limits.monthly_total_tokens > 0
            and summary.monthly_total + attempted_tokens > limits.monthly_total_tokens
        ):
            raise TokenLimitExceededError(
                f"monthly token budget {limits.monthly_total_tokens} would be exceeded "
                f"(used {summary.monthly_total}, attempted {attempted_tokens})",
                scope="monthly",
                limit=limits.monthly_total_tokens,
                current=summary.monthly_total,
                attempted=attempted_tokens,
            )

    def record(
        self,
        *,
        provider: str,
        model: str,
        task: str,
        actor: str,
        prompt_tokens: int,
        completion_tokens: int,
        now: datetime | None = None,
    ) -> TokenUsageEntry:
        moment = now or datetime.now(UTC)
        entry = TokenUsageEntry(
            provider=provider,
            model=model,
            task=task,
            actor=actor,
            prompt_tokens=max(0, int(prompt_tokens or 0)),
            completion_tokens=max(0, int(completion_tokens or 0)),
            total_tokens=max(0, int(prompt_tokens or 0)) + max(0, int(completion_tokens or 0)),
            occurred_at=moment.isoformat(),
        )
        path = self._daily_path(moment)
        path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(path, "a", encoding="utf-8", timeout=5) as fh:
            fh.write(json.dumps(entry.to_dict(), ensure_ascii=False, sort_keys=True))
            fh.write("\n")
        return entry

    def summary(self, *, now: datetime | None = None, recent_limit: int = 50) -> TokenUsageSummary:
        moment = now or datetime.now(UTC)
        daily_entries = self._read_day(moment)
        month_entries: list[TokenUsageEntry] = []
        if self._daily_dir.exists():
            month_prefix = moment.strftime("%Y-%m")
            for path in sorted(self._daily_dir.glob(f"{month_prefix}-*.jsonl")):
                month_entries.extend(self._read_jsonl(path))
        daily_total = sum(entry.total_tokens for entry in daily_entries)
        monthly_total = sum(entry.total_tokens for entry in month_entries)
        by_provider: dict[str, int] = {}
        by_task: dict[str, int] = {}
        by_actor: dict[str, int] = {}
        for entry in month_entries:
            by_provider[entry.provider or "unknown"] = (
                by_provider.get(entry.provider or "unknown", 0) + entry.total_tokens
            )
            by_task[entry.task or "unknown"] = (
                by_task.get(entry.task or "unknown", 0) + entry.total_tokens
            )
            by_actor[entry.actor or "unknown"] = (
                by_actor.get(entry.actor or "unknown", 0) + entry.total_tokens
            )
        recent = list(reversed(daily_entries))[:recent_limit]
        return TokenUsageSummary(
            daily_total=daily_total,
            monthly_total=monthly_total,
            by_provider=by_provider,
            by_task=by_task,
            by_actor=by_actor,
            recent=recent,
        )

    def _daily_path(self, moment: datetime) -> Path:
        return self._daily_dir / f"{moment.strftime('%Y-%m-%d')}.jsonl"

    def _read_day(self, moment: datetime) -> list[TokenUsageEntry]:
        return self._read_jsonl(self._daily_path(moment))

    def _read_jsonl(self, path: Path) -> list[TokenUsageEntry]:
        if not path.exists():
            return []
        entries: list[TokenUsageEntry] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            entries.append(
                TokenUsageEntry(
                    provider=str(payload.get("provider") or ""),
                    model=str(payload.get("model") or ""),
                    task=str(payload.get("task") or ""),
                    actor=str(payload.get("actor") or ""),
                    prompt_tokens=int(payload.get("prompt_tokens") or 0),
                    completion_tokens=int(payload.get("completion_tokens") or 0),
                    total_tokens=int(payload.get("total_tokens") or 0),
                    occurred_at=str(payload.get("occurred_at") or ""),
                )
            )
        return entries
