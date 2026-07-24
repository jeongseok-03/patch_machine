"""Repository test discovery and safe test-runner helpers for MCP tools."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

TEST_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}
SKIP_DIRS = {".git", ".venv", "node_modules", "dist", "build", ".mypy_cache", ".pytest_cache"}
ALLOWED_TEST_COMMANDS = {
    "python -m pytest -q",
    "python -m ruff check .",
    "python -m mypy negotium tests",
    "npm run build --prefix frontend",
}


def detect_test_frameworks(workspace_dir: Path) -> dict[str, Any]:
    files = _repo_files(workspace_dir)
    frameworks: list[str] = []
    if any(path.startswith("tests/") and path.endswith(".py") for path in files):
        frameworks.append("pytest")
    if any(path.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")) for path in files):
        frameworks.append("vitest_or_jest")
    if (workspace_dir / "pyproject.toml").exists():
        frameworks.append("ruff_mypy")
    if (workspace_dir / "frontend" / "package.json").exists():
        frameworks.append("vite_tsc")
    return {
        "frameworks": list(dict.fromkeys(frameworks)),
        "test_files": [path for path in files if _is_test_file(path)][:50],
        "configured": bool(frameworks),
    }


def find_existing_test_patterns(workspace_dir: Path, *, query: str = "") -> dict[str, Any]:
    files = _repo_files(workspace_dir)
    test_files = [path for path in files if _is_test_file(path)]
    needle = query.lower().strip()
    ranked: list[tuple[int, str]] = []
    for rel in test_files:
        score = 1
        if needle and needle in rel.lower():
            score += 3
        try:
            text = (workspace_dir / rel).read_text(encoding="utf-8", errors="ignore")[:5000].lower()
        except OSError:
            text = ""
        if needle and needle in text:
            score += 2
        ranked.append((score, rel))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    examples = []
    for _, rel in ranked[:8]:
        examples.append({"path": rel, "style_hints": _style_hints(workspace_dir / rel)})
    return {"patterns": examples, "total_test_files": len(test_files)}


def generate_test_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    title = str(arguments.get("title") or arguments.get("request") or "PatchOps regression test")
    return {
        "test_plan": [
            {
                "title": title,
                "type": str(arguments.get("requirement_type") or "regression"),
                "expected_before_patch": "fail_when_reproducible",
                "target_behavior": str(
                    arguments.get("then") or "Reported behavior no longer occurs."
                ),
            }
        ],
        "notes": [
            "MVP generates a plan and diff draft only; test file writes remain approval-gated."
        ],
    }


def run_test_command(workspace_dir: Path, *, command: str, dry_run: bool = True) -> dict[str, Any]:
    if command not in ALLOWED_TEST_COMMANDS:
        return {
            "ok": False,
            "dry_run": dry_run,
            "allowed": False,
            "command": command,
            "reason": "command is not in the PatchOps test runner allowlist",
        }
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "allowed": True,
            "command": command,
            "summary": "Command is allowlisted and ready for sandbox execution.",
        }
    completed = subprocess.run(
        command,
        cwd=workspace_dir,
        shell=True,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    output = (completed.stdout + "\n" + completed.stderr).strip()
    return {
        "ok": completed.returncode == 0,
        "dry_run": False,
        "allowed": True,
        "command": command,
        "exit_code": completed.returncode,
        "output_excerpt": output[:4000],
    }


def analyze_test_failure(arguments: dict[str, Any]) -> dict[str, Any]:
    output = str(arguments.get("output") or arguments.get("output_excerpt") or "")
    lower = output.lower()
    reasons = []
    if "assert" in lower:
        reasons.append("assertion_failure")
    if "importerror" in lower or "modulenotfounderror" in lower:
        reasons.append("import_or_dependency_failure")
    if "timeout" in lower:
        reasons.append("timeout")
    return {
        "failure_types": reasons or ["unknown"],
        "summary": output[:600] or "No failure output was provided.",
        "next_steps": [
            "Confirm the failing test maps to a TestRequirement.",
            "Check whether the failure is expected before applying the patch.",
        ],
    }


def _repo_files(root: Path) -> list[str]:
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix.lower() not in TEST_SUFFIXES and path.name not in {
            "pyproject.toml",
            "package.json",
        }:
            continue
        files.append(rel.as_posix())
        if len(files) >= 600:
            break
    return files


def _is_test_file(path: str) -> bool:
    lowered = path.lower()
    return (
        lowered.startswith("tests/")
        or "/tests/" in lowered
        or ".test." in lowered
        or ".spec." in lowered
        or "_test." in lowered
    )


def _style_hints(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:4000]
    except OSError:
        return []
    hints: list[str] = []
    if "pytest.fixture" in text:
        hints.append("uses pytest fixtures")
    if "TestClient" in text:
        hints.append("uses FastAPI TestClient")
    if "describe(" in text:
        hints.append("uses describe/it style")
    if "vi.mock" in text or "jest.mock" in text:
        hints.append("uses module mocks")
    return hints
