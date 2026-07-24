"""Persistent operations memory for the company running Negotium."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from negotium.archive._store import read_json_file, write_json_file


@dataclass(frozen=True)
class OperationsMemory:
    """Human-editable operating context shown in the web UI and sent to agents."""

    company_name: str = ""
    office_project: str = ""
    active_plan: str = ""
    organization: str = ""
    departments: str = ""
    roles: str = ""
    key_workflows: str = ""
    office_tools: str = ""
    sensitive_policy: str = ""

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> OperationsMemory:
        return cls(
            company_name=str(payload.get("company_name") or ""),
            office_project=str(payload.get("office_project") or ""),
            active_plan=str(payload.get("active_plan") or ""),
            organization=str(payload.get("organization") or ""),
            departments=str(payload.get("departments") or ""),
            roles=str(payload.get("roles") or ""),
            key_workflows=str(payload.get("key_workflows") or ""),
            office_tools=str(payload.get("office_tools") or ""),
            sensitive_policy=str(payload.get("sensitive_policy") or ""),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "company_name": self.company_name,
            "office_project": self.office_project,
            "active_plan": self.active_plan,
            "organization": self.organization,
            "departments": self.departments,
            "roles": self.roles,
            "key_workflows": self.key_workflows,
            "office_tools": self.office_tools,
            "sensitive_policy": self.sensitive_policy,
        }

    def to_markdown(self) -> str:
        return "\n".join(
            [
                "## 운영 메모리",
                f"- 회사 이름: {self.company_name or '(미설정)'}",
                f"- 오피스 프로젝트: {self.office_project or '(미설정)'}",
                f"- 진행 중 계획: {self.active_plan or '(미설정)'}",
                f"- 조직 구조: {self.organization or '(미설정)'}",
                f"- 부서/팀: {self.departments or '(미설정)'}",
                f"- 주요 역할: {self.roles or '(미설정)'}",
                f"- 핵심 업무 흐름: {self.key_workflows or '(미설정)'}",
                f"- 사용 도구: {self.office_tools or '(미설정)'}",
                f"- 민감정보 정책: {self.sensitive_policy or '(미설정)'}",
            ]
        )


class OperationsMemoryStore:
    """File-backed operations memory.

    Missing files intentionally read as an empty memory so a new installation
    starts from a clean state until an operator saves values in the UI.
    """

    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "operations_memory.json"

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> OperationsMemory:
        payload = read_json_file(self._path, default=dict)
        if not payload:
            return OperationsMemory()
        if not isinstance(payload, dict):
            raise ValueError("operations memory must be a JSON object")
        return OperationsMemory.from_mapping(payload)

    def write(self, memory: OperationsMemory) -> None:
        payload: dict[str, object] = {
            **memory.to_dict(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        write_json_file(self._path, payload)
