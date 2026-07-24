"""Typer-based CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import typer
import uvicorn

from negotium.app.container import Container
from negotium.observability import configure_logging, get_logger

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Negotium CLI")


@app.command()
def serve(
    host: str | None = typer.Option(None, help="HTTP bind host (overrides settings)."),
    port: int | None = typer.Option(None, help="HTTP bind port (overrides settings)."),
) -> None:
    """Run the FastAPI server + background orchestrator + Discord bot."""
    container = Container.build()
    settings = container.settings
    configure_logging(settings.log_level)
    uvicorn.run(
        "negotium.app.main:create_app",
        host=host or settings.http_host,
        port=port or settings.http_port,
        factory=True,
        log_level=settings.log_level.lower(),
    )


@app.command("llm-gateway")
def llm_gateway(
    host: str | None = typer.Option(None, help="HTTP bind host (overrides settings)."),
    port: int | None = typer.Option(None, help="HTTP bind port (overrides settings)."),
) -> None:
    """Run the standalone external LLM gateway."""
    from negotium.app.settings import load_settings

    settings = load_settings()
    configure_logging(settings.log_level)
    uvicorn.run(
        "negotium.llm_gateway.app:create_app",
        host=host or settings.llm_gateway_host,
        port=port or settings.llm_gateway_port,
        factory=True,
        log_level=settings.log_level.lower(),
    )


@app.command()
def reindex(archive_dir: Path = typer.Option(Path("./archive"))) -> None:
    """Rebuild index MD files from existing archive logs.

    Useful when the archive is imported from another machine or after a manual
    edit.  The logic lives in ``ArchiveWriter`` so it mirrors the production
    write path exactly.
    """
    from negotium.archive.schema import parse_front_matter
    from negotium.archive.writer import ArchiveWriter

    writer = ArchiveWriter(archive_dir)
    count = 0
    for log_path in archive_dir.rglob("*.md"):
        try:
            rel_parts = log_path.relative_to(archive_dir).parts
        except ValueError:
            continue
        if len(rel_parts) < 3 or rel_parts[0] in {"index", "knowledge_base"}:
            continue
        if not rel_parts[0].isdigit():
            continue
        text = log_path.read_text(encoding="utf-8", errors="ignore")
        fm = parse_front_matter(text)
        if not fm:
            continue
        keywords = fm.get("keywords") or []
        modules = fm.get("modules") or []
        author = fm.get("author", "")
        writer.index.update(
            log_path=log_path,
            keywords=keywords,
            modules=modules,
            author=author,
        )
        count += 1
    writer.refresh_status()
    typer.echo(f"reindexed {count} log(s)")


@app.command("reset-state")
def reset_state(
    yes: bool = typer.Option(False, "--yes", help="Confirm destructive local state reset."),
    actor: str = typer.Option("cli", help="Actor name written to the audit log."),
    include_workspaces: bool = typer.Option(
        True,
        help="Also clear the configured workspace directory.",
    ),
) -> None:
    """Reset local memory, auth, secrets, documents, uploads, and workspaces."""
    from negotium.app.reset_state import reset_system_state
    from negotium.app.settings import load_settings

    if not yes:
        raise typer.BadParameter("reset-state is destructive; re-run with --yes to confirm")
    settings = load_settings()
    result = reset_system_state(
        archive_dir=settings.archive_dir,
        workspace_dir=settings.workspace_dir,
        actor=actor,
        include_workspaces=include_workspaces,
    )
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


skill_app = typer.Typer(no_args_is_help=True, help="List and run registered skills.")
app.add_typer(skill_app, name="skill")


@skill_app.command("list")
def skill_list() -> None:
    """List all registered skills."""
    from negotium.app.services.skill_registry import get_skills

    skills = get_skills()
    if not skills:
        typer.echo("등록된 스킬이 없습니다.")
        return
    for skill in skills.values():
        typer.echo(f"{skill.id}\t[{skill.executor}]\t{skill.name} — {skill.description}")


@skill_app.command("run")
def skill_run(
    skill_id: str = typer.Argument(..., help="Skill id to run."),
    inputs: list[str] = typer.Option([], "--input", "-i", help="Input as key=value (repeatable)."),
    actor: str = typer.Option("cli", help="Actor name for the audit log."),
) -> None:
    """Run a skill with key=value inputs."""
    import asyncio

    from negotium.app.api import _complete_office_task
    from negotium.app.services.skill_registry import get_skill
    from negotium.app.services.skill_runtime import SkillError, run_skill

    parsed: dict[str, str] = {}
    for raw in inputs:
        if "=" not in raw:
            raise typer.BadParameter(f"input must be key=value: {raw}")
        key, value = raw.split("=", 1)
        parsed[key.strip()] = value
    container = Container.build()
    skill = get_skill(skill_id)
    if skill is None:
        raise typer.BadParameter(f"unknown skill: {skill_id}")

    async def _completion(prompt: str, image_parts: list[dict[str, object]] | None) -> str:
        return await _complete_office_task(container, prompt, task=skill.task)

    async def _run() -> None:
        try:
            result = await run_skill(
                container, skill_id, dict(parsed), actor=actor, completion=_completion
            )
        except SkillError as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    asyncio.run(_run())


@app.command()
def replay(jsonl_path: Path) -> None:
    """Replay past events recorded as JSONL (one IssueEvent per line)."""
    import asyncio

    from negotium.domain.entities import IssueEvent

    container = Container.build()
    log = get_logger(component="cli.replay")

    async def _run() -> None:
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            event = IssueEvent.model_validate(payload)
            log.info("replay.event", event_id=str(event.event_id), source=event.source)
            await container.orchestrator.handle(event)

    asyncio.run(_run())


if __name__ == "__main__":
    app()
