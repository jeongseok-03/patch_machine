"""Dynamic permanent-memory schema definitions and proposals."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import portalocker


@dataclass(frozen=True)
class MemorySchema:
    type_id: str
    display_name: str
    description: str = ""
    fields: list[dict[str, object]] = field(default_factory=list)
    retention_policy: str = "keep"
    sensitivity: str = "internal"
    delete_requires_approval: bool = True
    allowed_roles: list[str] = field(default_factory=lambda: ["owner", "manager"])
    created_by: str = ""
    updated_at: str = ""

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> MemorySchema:
        return cls(
            type_id=str(payload.get("type_id") or ""),
            display_name=str(payload.get("display_name") or ""),
            description=str(payload.get("description") or ""),
            fields=[item for item in payload.get("fields", []) if isinstance(item, dict)],
            retention_policy=str(payload.get("retention_policy") or "keep"),
            sensitivity=str(payload.get("sensitivity") or "internal"),
            delete_requires_approval=bool(payload.get("delete_requires_approval", True)),
            allowed_roles=[
                str(item) for item in payload.get("allowed_roles", ["owner", "manager"])
            ],
            created_by=str(payload.get("created_by") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "type_id": self.type_id,
            "display_name": self.display_name,
            "description": self.description,
            "fields": self.fields,
            "retention_policy": self.retention_policy,
            "sensitivity": self.sensitivity,
            "delete_requires_approval": self.delete_requires_approval,
            "allowed_roles": self.allowed_roles,
            "created_by": self.created_by,
            "updated_at": self.updated_at,
        }


class MemorySchemaStore:
    def __init__(self, archive_dir: Path) -> None:
        self._path = archive_dir / "memory" / "schema.json"
        self._proposals_path = archive_dir / "memory" / "schema_proposals.json"

    def list(self) -> list[dict[str, object]]:
        return [schema.to_dict() for schema in self._read_schemas()]

    def upsert(self, schema: MemorySchema, *, actor: str) -> MemorySchema:
        if not schema.type_id or not schema.display_name:
            raise ValueError("memory schema type_id and display_name are required")
        updated = MemorySchema.from_mapping(
            {
                **schema.to_dict(),
                "created_by": schema.created_by or actor,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        schemas = [
            existing for existing in self._read_schemas() if existing.type_id != updated.type_id
        ]
        schemas.append(updated)
        self._write_schemas(schemas)
        return updated

    def propose(self, *, actor: str, mode: str, proposal: dict[str, object]) -> dict[str, object]:
        proposals = self._read_proposals()
        payload = {
            "id": str(uuid4()),
            "actor": actor,
            "mode": mode,
            "proposal": proposal,
            "status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
            "decided_at": "",
            "decided_by": "",
        }
        proposals.append(payload)
        self._write_proposals(proposals)
        return payload

    def approve(self, proposal_id: str, *, actor: str) -> dict[str, object]:
        proposals = self._read_proposals()
        proposal = next((item for item in proposals if item["id"] == proposal_id), None)
        if proposal is None:
            raise ValueError("schema proposal not found")
        proposal["status"] = "approved"
        proposal["decided_at"] = datetime.now(UTC).isoformat()
        proposal["decided_by"] = actor
        raw_schema = proposal.get("proposal")
        if isinstance(raw_schema, dict) and "type_id" in raw_schema:
            self.upsert(MemorySchema.from_mapping(raw_schema), actor=actor)
        self._write_proposals(proposals)
        return proposal

    def proposals(self) -> list[dict[str, object]]:
        return self._read_proposals()

    def _read_schemas(self) -> list[MemorySchema]:
        if not self._path.exists():
            return []
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return []
        return [MemorySchema.from_mapping(item) for item in payload if isinstance(item, dict)]

    def _write_schemas(self, schemas: list[MemorySchema]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(self._path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump([schema.to_dict() for schema in schemas], fh, ensure_ascii=False, indent=2)
            fh.write("\n")

    def _read_proposals(self) -> list[dict[str, object]]:
        if not self._proposals_path.exists():
            return []
        payload = json.loads(self._proposals_path.read_text(encoding="utf-8"))
        return (
            [item for item in payload if isinstance(item, dict)]
            if isinstance(payload, list)
            else []
        )

    def _write_proposals(self, proposals: list[dict[str, object]]) -> None:
        self._proposals_path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(self._proposals_path, "w", encoding="utf-8", timeout=5) as fh:
            json.dump(proposals, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
