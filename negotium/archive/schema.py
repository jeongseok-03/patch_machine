"""MD log schema: YAML front-matter + Jinja-rendered body."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel, Field

_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    autoescape=False,
)


class LogFrontMatter(BaseModel):
    event_id: str
    source: str
    external_id: str
    repo: str
    status: str
    modules: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    iteration: int = 1
    created: datetime
    llm_route: str = "cloud"


def dump_front_matter(fm: LogFrontMatter) -> str:
    """Render front-matter with a stable key order."""
    data = fm.model_dump(mode="json")
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()


def render_log_markdown(
    *,
    front_matter: LogFrontMatter,
    context_md: str,
    retrieved_md: str,
    thought_process_md: str,
    patch_diff: str,
    human_review_md: str = "",
) -> str:
    template = _env.get_template("log_template.md.j2")
    rendered = template.render(
        front_matter=dump_front_matter(front_matter),
        context_md=context_md,
        retrieved_md=retrieved_md,
        thought_process_md=thought_process_md,
        patch_diff=patch_diff,
        human_review_md=human_review_md,
    )
    return rendered


def parse_front_matter(markdown: str) -> dict[str, Any]:
    """Utility to read front matter from an existing log (used by indexes)."""
    if not markdown.startswith("---"):
        return {}
    end = markdown.find("\n---", 3)
    if end == -1:
        return {}
    block = markdown[3:end].strip()
    loaded = yaml.safe_load(block) or {}
    if not isinstance(loaded, dict):
        return {}
    return loaded
