"""Central prompt template storage and rendering."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

PROMPT_ROOT = Path(__file__).resolve().parent


class PromptStore:
    """Render managed prompt templates from the project prompt directory."""

    def __init__(self, root: Path = PROMPT_ROOT) -> None:
        self.root = root
        self._env = Environment(
            loader=FileSystemLoader(root),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
            autoescape=False,
        )

    def render(self, name: str, **context: object) -> str:
        try:
            template = self._env.get_template(name)
        except TemplateNotFound:
            template = self._env.get_template(f"agents/{name}")
        return template.render(**context)


_default_store = PromptStore()


def render(name: str, **context: object) -> str:
    return _default_store.render(name, **context)
