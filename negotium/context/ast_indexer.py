"""AST-based code summarizer.

Uses ``tree-sitter-languages`` when available so we don't maintain per-language
grammars manually. When the library isn't installed (e.g. in the minimal test
environment) we degrade gracefully to a regex summary so downstream agents
still get *something* useful.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from negotium.observability import get_logger

_SUPPORTED_SUFFIXES = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
}


@dataclass
class FileSummary:
    path: Path
    language: str
    symbols: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


@dataclass
class AstSummary:
    files: list[FileSummary] = field(default_factory=list)
    truncated: bool = False

    def to_markdown(self) -> str:
        if not self.files:
            return "_(AST summary not available)_"
        lines: list[str] = []
        for fs in self.files:
            lines.append(f"- `{fs.path.as_posix()}` ({fs.language})")
            for sym in fs.symbols[:20]:
                lines.append(f"    - {sym}")
            if fs.imports:
                joined = ", ".join(fs.imports[:10])
                lines.append(f"    - imports: {joined}")
        if self.truncated:
            lines.append("- _(일부 파일은 토큰 예산으로 생략됨)_")
        return "\n".join(lines)


class AstIndexer:
    """Summarizes a small set of files for the agent prompt budget."""

    def __init__(
        self,
        *,
        token_budget: int = 6000,
        get_parser: Any | None = None,
    ) -> None:
        self._budget = token_budget
        self._get_parser = get_parser
        self._log = get_logger(component="context.ast_indexer")

    def summarize(self, paths: Iterable[Path]) -> AstSummary:
        summary = AstSummary()
        used = 0
        for path in paths:
            if used >= self._budget:
                summary.truncated = True
                break
            language = _SUPPORTED_SUFFIXES.get(path.suffix.lower())
            if language is None:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            fs = self._summarize_file(path, language, text)
            summary.files.append(fs)
            used += max(1, len(text) // 4)
        return summary

    def _summarize_file(self, path: Path, language: str, text: str) -> FileSummary:
        parser = self._resolve_parser(language)
        if parser is None:
            return self._regex_summary(path, language, text)
        try:
            tree = parser.parse(text.encode("utf-8"))
        except Exception:
            self._log.exception("ast_indexer.parse_failed", path=str(path))
            return self._regex_summary(path, language, text)
        symbols: list[str] = []
        imports: list[str] = []
        self._walk(tree.root_node, text, symbols, imports, language)
        return FileSummary(path=path, language=language, symbols=symbols, imports=imports)

    def _resolve_parser(self, language: str) -> Any | None:
        if self._get_parser is not None:
            try:
                return self._get_parser(language)
            except Exception:
                return None
        try:
            from tree_sitter_languages import get_parser
        except Exception:
            return None
        try:
            return get_parser(language)
        except Exception:
            return None

    @staticmethod
    def _walk(
        node: Any,
        source: str,
        symbols: list[str],
        imports: list[str],
        language: str,
    ) -> None:
        symbol_kinds = {
            "function_definition",
            "function_declaration",
            "method_definition",
            "class_definition",
            "class_declaration",
        }
        import_kinds = {
            "import_statement",
            "import_from_statement",
            "import_declaration",
        }
        stack: list[Any] = [node]
        while stack:
            current = stack.pop()
            node_type = getattr(current, "type", "")
            start = getattr(current, "start_byte", 0)
            end = getattr(current, "end_byte", 0)
            if node_type in symbol_kinds:
                snippet = source.encode("utf-8")[start:end].decode("utf-8", "ignore")
                first_line = snippet.splitlines()[0].strip() if snippet else ""
                if first_line:
                    symbols.append(first_line)
            elif node_type in import_kinds:
                snippet = source.encode("utf-8")[start:end].decode("utf-8", "ignore")
                imports.append(snippet.strip().splitlines()[0])
            children = getattr(current, "children", None)
            if children:
                stack.extend(reversed(children))

    @staticmethod
    def _regex_summary(path: Path, language: str, text: str) -> FileSummary:
        symbols: list[str] = []
        imports: list[str] = []
        if language == "python":
            for match in re.finditer(
                r"^\s*(?:async\s+)?(def|class)\s+[\w_]+.*$", text, re.MULTILINE
            ):
                symbols.append(match.group(0).strip())
            for match in re.finditer(
                r"^\s*(?:from\s+[\w\.]+\s+import\s+[^\n]+|import\s+[\w\.,\s]+)", text, re.MULTILINE
            ):
                imports.append(match.group(0).strip())
        elif language in {"typescript", "tsx", "javascript"}:
            for match in re.finditer(
                r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+[\w_$]+[^\n]*",
                text,
                re.MULTILINE,
            ):
                symbols.append(match.group(0).strip())
            for match in re.finditer(r"^\s*import\s+[^\n]+", text, re.MULTILINE):
                imports.append(match.group(0).strip())
        return FileSummary(path=path, language=language, symbols=symbols[:20], imports=imports[:10])
