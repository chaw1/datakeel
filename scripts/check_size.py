# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Enforce source-size limits independently of style rules."""

import ast
from pathlib import Path

from rich.console import Console

PYTHON_FILE_LIMIT = 400
TEST_FILE_LIMIT = 600
FUNCTION_LIMIT = 60
COMPONENT_LIMIT = 300
AGENT_PACKAGE_LIMIT = 1500


def violations() -> list[str]:
    """Find oversized hand-written Python and TypeScript components."""
    problems: list[str] = []
    for root in ("datakeel", "tests", "scripts", "examples"):
        for path in Path(root).rglob("*.py"):
            source = path.read_text()
            limit = TEST_FILE_LIMIT if root == "tests" else PYTHON_FILE_LIMIT
            if len(source.splitlines()) > limit:
                problems.append(f"{path}: file exceeds {limit} lines")
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    length = (node.end_lineno or node.lineno) - node.lineno + 1
                    if length > FUNCTION_LIMIT:
                        problems.append(f"{path}:{node.lineno}: {node.name} has {length} lines")
    problems.extend(
        f"{path}: component exceeds {COMPONENT_LIMIT} lines"
        for path in Path("web/src").rglob("*.tsx")
        if len(path.read_text().splitlines()) > COMPONENT_LIMIT
    )
    agent_lines = sum(
        len(path.read_text().splitlines()) for path in Path("datakeel/agent").rglob("*.py")
    )
    if agent_lines > AGENT_PACKAGE_LIMIT:
        problems.append(f"datakeel/agent: {agent_lines} lines exceeds {AGENT_PACKAGE_LIMIT}")
    return problems


def main() -> None:
    """Fail a local or CI check when implementation grows beyond its limits."""
    problems = violations()
    Console().print("\n".join(problems) if problems else "Source size limits passed.")
    raise SystemExit(bool(problems))


if __name__ == "__main__":
    main()
