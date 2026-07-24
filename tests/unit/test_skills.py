"""Unit tests for the skill registry and runtime."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from negotium.app.services.skill_registry import get_skills, load_skills
from negotium.app.services.skill_runtime import SkillError, run_skill

SKILL_PROMPT = """---
id: test.prompt_skill
name: Test Prompt
description: a prompt skill
executor: prompt
required_permission: documents:write
output_format: auto
output_folder: documents
inputs:
  - name: title
    type: string
    required: true
---
Write about {{ title }}.
"""

SKILL_TOOL = """---
id: test.tool_skill
name: Test Tool
description: a tool skill
executor: tool
tool: memory.search_issues
required_permission: memory:read
inputs:
  - name: query
    type: string
    required: true
---
Search.
"""


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


def _container(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        settings=SimpleNamespace(archive_dir=tmp_path, workspace_dir=tmp_path),
        audit_log=_Audit(),
    )


def _write_skills(root: Path) -> None:
    (root / "test_prompt_skill").mkdir(parents=True)
    (root / "test_prompt_skill" / "SKILL.md").write_text(SKILL_PROMPT, encoding="utf-8")
    (root / "test_tool_skill").mkdir(parents=True)
    (root / "test_tool_skill" / "SKILL.md").write_text(SKILL_TOOL, encoding="utf-8")


def test_load_skills_parses_front_matter(tmp_path: Path) -> None:
    _write_skills(tmp_path)
    skills = load_skills(tmp_path)
    assert set(skills) == {"test.prompt_skill", "test.tool_skill"}
    prompt = skills["test.prompt_skill"]
    assert prompt.executor == "prompt"
    assert prompt.inputs[0].name == "title"
    assert "Write about" in prompt.instructions


def test_builtin_skills_are_loadable() -> None:
    skills = get_skills(refresh=True)
    assert "office.document_draft" in skills
    assert skills["office.document_draft"].executor == "prompt"


async def test_run_prompt_skill_writes_doc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_skills(tmp_path)
    monkeypatch.setattr(
        "negotium.app.services.skill_runtime.get_skill",
        lambda sid: load_skills(tmp_path).get(sid),
    )
    container = _container(tmp_path)

    async def _completion(prompt: str, image_parts: Any) -> str:
        assert "Subject" in prompt
        return "<!-- negotium:format=markdown -->\nGenerated body"

    result = await run_skill(
        container,
        "test.prompt_skill",
        {"title": "Subject"},
        actor="tester",
        completion=_completion,
    )
    assert result.status == "succeeded"
    assert result.output_format == "markdown"
    assert result.output_path.endswith(".md")
    assert (tmp_path / result.output_path).exists()
    assert container.audit_log.records


async def test_run_skill_missing_required_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_skills(tmp_path)
    monkeypatch.setattr(
        "negotium.app.services.skill_runtime.get_skill",
        lambda sid: load_skills(tmp_path).get(sid),
    )
    container = _container(tmp_path)
    with pytest.raises(SkillError):
        await run_skill(container, "test.prompt_skill", {}, completion=None)


async def test_run_tool_skill_delegates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_skills(tmp_path)
    monkeypatch.setattr(
        "negotium.app.services.skill_runtime.get_skill",
        lambda sid: load_skills(tmp_path).get(sid),
    )
    captured: dict[str, Any] = {}

    def _fake_call_tool(container: Any, tool: str, args: dict[str, Any]) -> Any:
        captured["tool"] = tool
        captured["args"] = args
        return SimpleNamespace(result={"hits": []}, guard_findings=[])

    monkeypatch.setattr("negotium.app.services.skill_runtime.call_tool", _fake_call_tool)
    container = _container(tmp_path)
    result = await run_skill(container, "test.tool_skill", {"query": "login bug"}, actor="tester")
    assert captured["tool"] == "memory.search_issues"
    assert captured["args"] == {"query": "login bug"}
    assert result.executor == "tool"
    assert result.tool_result == {"hits": []}


async def test_run_unknown_skill(tmp_path: Path) -> None:
    container = _container(tmp_path)
    with pytest.raises(SkillError):
        await run_skill(container, "does.not.exist", {})
