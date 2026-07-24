"""Skill runtime: dispatch a registered skill against the container.

Three executor kinds are supported:

* ``prompt`` — render the skill body (Jinja) with the supplied inputs, complete
  it with the office LLM via a caller-provided ``completion`` coroutine, then
  persist the result honoring the AI-chosen output format.
* ``tool`` — delegate to the MCP Hub ``call_tool`` dispatcher (reusing its
  permission, audit, and context-firewall handling).
* ``cli`` — run an allowlisted, read-only shell command in the workspace.

The runtime stays decoupled from the HTTP layer: the LLM completion is injected
so both the API and the CLI can supply their own implementation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from jinja2 import Environment, select_autoescape

from negotium.app.services.document_output import resolve_output_format, write_generated_doc
from negotium.app.services.mcp_hub_service import call_tool
from negotium.app.services.skill_registry import Skill, get_skill, get_skills

# Completion signature: (prompt, image_parts) -> generated text.
CompletionFn = Callable[[str, list[dict[str, Any]] | None], Awaitable[str]]

# Only these base commands may run via the cli executor (read-only by design).
CLI_ALLOWLIST = {"git", "ls", "cat", "rg", "pytest", "python", "uv"}

_jinja_env = Environment(autoescape=select_autoescape(enabled_extensions=()))


class SkillError(RuntimeError):
    """Raised when a skill cannot be dispatched (missing skill, bad inputs)."""


@dataclass
class SkillRunResult:
    skill_id: str
    executor: str
    status: str = "succeeded"
    output_text: str = ""
    output_path: str = ""
    output_format: str = ""
    tool_result: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "executor": self.executor,
            "status": self.status,
            "output_text": self.output_text,
            "output_path": self.output_path,
            "output_format": self.output_format,
            "tool_result": self.tool_result,
            "notes": self.notes,
        }


def _validate_inputs(skill: Skill, inputs: dict[str, Any]) -> None:
    missing = [item.name for item in skill.inputs if item.required and not inputs.get(item.name)]
    if missing:
        raise SkillError(f"skill '{skill.id}' missing required inputs: {', '.join(missing)}")


def _render_prompt_body(skill: Skill, inputs: dict[str, Any]) -> str:
    template = _jinja_env.from_string(skill.instructions or "")
    return template.render(**inputs).strip()


async def run_skill(
    container: Any,
    skill_id: str,
    inputs: dict[str, Any],
    *,
    actor: str = "system",
    completion: CompletionFn | None = None,
) -> SkillRunResult:
    skill = get_skill(skill_id)
    if skill is None:
        raise SkillError(f"unknown skill: {skill_id}")
    _validate_inputs(skill, inputs)

    if skill.executor == "tool":
        result = await _run_tool_skill(container, skill, inputs)
    elif skill.executor == "cli":
        result = _run_cli_skill(container, skill, inputs)
    else:
        result = await _run_prompt_skill(container, skill, inputs, completion=completion)

    _record_audit(container, skill, actor=actor, result=result)
    return result


async def _run_prompt_skill(
    container: Any,
    skill: Skill,
    inputs: dict[str, Any],
    *,
    completion: CompletionFn | None,
) -> SkillRunResult:
    if completion is None:
        raise SkillError(f"skill '{skill.id}' requires an LLM completion function")
    prompt = _render_prompt_body(skill, inputs)
    raw = await completion(prompt, None)
    resolved_format, body = resolve_output_format(raw, requested=skill.output_format)
    slug = str(inputs.get("title") or skill.id)
    path = write_generated_doc(
        container.settings.archive_dir,
        folder=skill.output_folder,
        slug=f"{skill.id}_{slug}",
        markdown=body,
        output_format=resolved_format,
    )
    return SkillRunResult(
        skill_id=skill.id,
        executor="prompt",
        output_text=body,
        output_path=path,
        output_format=resolved_format,
    )


async def _run_tool_skill(container: Any, skill: Skill, inputs: dict[str, Any]) -> SkillRunResult:
    if not skill.tool:
        raise SkillError(f"skill '{skill.id}' has no bound tool")
    call_result = call_tool(container, skill.tool, dict(inputs))
    return SkillRunResult(
        skill_id=skill.id,
        executor="tool",
        tool_result=call_result.result,
        notes=list(call_result.guard_findings),
    )


def _run_cli_skill(container: Any, skill: Skill, inputs: dict[str, Any]) -> SkillRunResult:
    import shlex
    import subprocess

    if not skill.command:
        raise SkillError(f"skill '{skill.id}' has no command")
    base = skill.command[0]
    if base not in CLI_ALLOWLIST:
        raise SkillError(f"skill '{skill.id}' command '{base}' is not allowlisted")
    extra_raw = inputs.get("args")
    extra: list[str] = []
    if isinstance(extra_raw, str) and extra_raw.strip():
        extra = shlex.split(extra_raw)
    elif isinstance(extra_raw, list):
        extra = [str(part) for part in extra_raw]
    argv = [*skill.command, *extra]
    workspace = getattr(container.settings, "workspace_dir", None)
    try:
        completed = subprocess.run(
            argv,
            cwd=str(workspace) if workspace else None,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return SkillRunResult(
            skill_id=skill.id,
            executor="cli",
            status="failed",
            output_text=str(exc),
        )
    output = (completed.stdout or "") + (completed.stderr or "")
    return SkillRunResult(
        skill_id=skill.id,
        executor="cli",
        status="succeeded" if completed.returncode == 0 else "failed",
        output_text=output[:20000],
        notes=[f"exit_code={completed.returncode}"],
    )


def run_cli_skill_sync(container: Any, skill: Skill, inputs: dict[str, Any]) -> dict[str, Any]:
    """Synchronous entry point for cli skills (used by the MCP Hub dispatcher)."""

    return _run_cli_skill(container, skill, inputs).to_dict()


def _record_audit(container: Any, skill: Skill, *, actor: str, result: SkillRunResult) -> None:
    audit = getattr(container, "audit_log", None)
    if audit is None:
        return
    try:
        audit.record(
            actor=actor,
            action="skill.run",
            target="skill",
            target_id=skill.id,
            details={
                "executor": skill.executor,
                "status": result.status,
                "output_path": result.output_path,
            },
        )
    except Exception:
        return


def list_skill_descriptors() -> list[dict[str, Any]]:
    return [skill.to_descriptor() for skill in get_skills().values()]


__all__ = [
    "SkillError",
    "SkillRunResult",
    "list_skill_descriptors",
    "run_skill",
]
