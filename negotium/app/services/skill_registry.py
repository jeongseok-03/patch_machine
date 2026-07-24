"""Skill registry: load ``SKILL.md`` definitions into typed records.

A skill is a small Markdown file with YAML front-matter plus a body. Front-matter
declares how the skill is dispatched (executor, template/tool, permissions); the
body is human/agent-facing instructions (and, for ``prompt`` skills without a
``template``, the Jinja prompt itself).

Skills live under ``negotium/skills/<id>/SKILL.md``. They are the single
source of truth shared by the HTTP API, MCP Hub, CLI, and work-schedule automata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

SKILLS_ROOT = Path(__file__).resolve().parents[2] / "skills"

ExecutorKind = Literal["prompt", "tool", "cli"]

_SKILL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.\-]*$")


@dataclass(frozen=True)
class SkillInput:
    name: str
    type: str = "string"
    required: bool = False
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "description": self.description,
        }


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    executor: ExecutorKind
    category: str = "general"
    required_permission: str = ""
    risk: str = "low"
    template: str = ""
    tool: str = ""
    command: list[str] = field(default_factory=list)
    output_format: str = "auto"
    output_folder: str = "documents"
    task: str = "document_generation"
    inputs: list[SkillInput] = field(default_factory=list)
    instructions: str = ""

    def input_schema(self) -> dict[str, Any]:
        properties = {
            item.name: {"type": item.type, "description": item.description} for item in self.inputs
        }
        required = [item.name for item in self.inputs if item.required]
        return {"type": "object", "properties": properties, "required": required}

    def to_descriptor(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "executor": self.executor,
            "required_permission": self.required_permission,
            "risk": self.risk,
            "tool": self.tool,
            "output_format": self.output_format,
            "inputs": [item.to_dict() for item in self.inputs],
        }


def _split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text.strip()
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text.strip()
    block = text[3:end].strip()
    body = text[end + 4 :].strip()
    try:
        loaded = yaml.safe_load(block) or {}
    except yaml.YAMLError:
        return {}, body
    if not isinstance(loaded, dict):
        return {}, body
    return loaded, body


def _parse_inputs(raw: Any) -> list[SkillInput]:
    inputs: list[SkillInput] = []
    if not isinstance(raw, list):
        return inputs
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        inputs.append(
            SkillInput(
                name=name,
                type=str(item.get("type") or "string"),
                required=bool(item.get("required") or False),
                description=str(item.get("description") or ""),
            )
        )
    return inputs


def _skill_from_markdown(text: str) -> Skill | None:
    front, body = _split_front_matter(text)
    skill_id = str(front.get("id") or "").strip()
    executor = str(front.get("executor") or "").strip()
    if not skill_id or executor not in {"prompt", "tool", "cli"}:
        return None
    command_raw = front.get("command")
    command = [str(part) for part in command_raw] if isinstance(command_raw, list) else []
    return Skill(
        id=skill_id,
        name=str(front.get("name") or skill_id),
        description=str(front.get("description") or ""),
        executor=executor,  # type: ignore[arg-type]
        category=str(front.get("category") or "general"),
        required_permission=str(front.get("required_permission") or ""),
        risk=str(front.get("risk") or "low"),
        template=str(front.get("template") or ""),
        tool=str(front.get("tool") or ""),
        command=command,
        output_format=str(front.get("output_format") or "auto"),
        output_folder=str(front.get("output_folder") or "documents"),
        task=str(front.get("task") or "document_generation"),
        inputs=_parse_inputs(front.get("inputs")),
        instructions=body,
    )


def load_skills(root: Path | None = None) -> dict[str, Skill]:
    """Load all skills from ``<root>/<id>/SKILL.md`` files."""

    base = root or SKILLS_ROOT
    skills: dict[str, Skill] = {}
    if not base.exists():
        return skills
    for skill_file in sorted(base.glob("*/SKILL.md")):
        try:
            text = skill_file.read_text(encoding="utf-8")
        except OSError:
            continue
        skill = _skill_from_markdown(text)
        if skill is not None:
            skills[skill.id] = skill
    return skills


def _skill_to_markdown(skill: Skill) -> str:
    front: dict[str, Any] = {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "category": skill.category,
        "executor": skill.executor,
    }
    if skill.required_permission:
        front["required_permission"] = skill.required_permission
    front["risk"] = skill.risk
    if skill.template:
        front["template"] = skill.template
    if skill.tool:
        front["tool"] = skill.tool
    if skill.command:
        front["command"] = skill.command
    front["output_format"] = skill.output_format
    front["output_folder"] = skill.output_folder
    front["task"] = skill.task
    if skill.inputs:
        front["inputs"] = [item.to_dict() for item in skill.inputs]
    block = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
    body = (skill.instructions or "").strip()
    return f"---\n{block}\n---\n{body}\n"


def register_skill(skill: Skill, *, root: Path | None = None, overwrite: bool = False) -> Skill:
    """Persist a skill as ``<root>/<folder>/SKILL.md`` and refresh the cache."""

    if not _SKILL_ID_RE.match(skill.id):
        raise ValueError(
            "스킬 ID는 소문자/숫자로 시작하고 영숫자, 점(.), 밑줄(_), 하이픈(-)만 사용할 수 있습니다."
        )
    if not skill.name.strip():
        raise ValueError("스킬 이름은 필수입니다.")
    base = root or SKILLS_ROOT
    if not overwrite and skill.id in load_skills(base):
        raise ValueError(f"이미 존재하는 스킬 ID입니다: {skill.id}")
    folder_name = re.sub(r"[^a-z0-9]+", "_", skill.id.lower()).strip("_") or "skill"
    skill_dir = base / folder_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(_skill_to_markdown(skill), encoding="utf-8")
    _cached_skills.cache_clear()
    return skill


@lru_cache(maxsize=1)
def _cached_skills() -> dict[str, Skill]:
    return load_skills()


def get_skills(*, refresh: bool = False) -> dict[str, Skill]:
    if refresh:
        _cached_skills.cache_clear()
    return _cached_skills()


def get_skill(skill_id: str) -> Skill | None:
    return get_skills().get(skill_id)


__all__ = [
    "Skill",
    "SkillInput",
    "get_skill",
    "get_skills",
    "load_skills",
    "register_skill",
]
