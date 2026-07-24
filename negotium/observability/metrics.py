"""In-process metric counters. Exportable later via OpenTelemetry metrics API."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class AgentMetrics:
    """Very small counter set keyed by (agent, route)."""

    tokens_in: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    tokens_out: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    latency_ms: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    calls: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record(
        self,
        *,
        agent: str,
        route: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
    ) -> None:
        key = (agent, route)
        with self._lock:
            self.tokens_in[key] += tokens_in
            self.tokens_out[key] += tokens_out
            self.latency_ms[key] += latency_ms
            self.calls[key] += 1

    def snapshot(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {
                f"{agent}:{route}": {
                    "tokens_in": self.tokens_in[(agent, route)],
                    "tokens_out": self.tokens_out[(agent, route)],
                    "latency_ms": self.latency_ms[(agent, route)],
                    "calls": self.calls[(agent, route)],
                }
                for (agent, route) in self.calls
            }
