# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject persistence-row references outside the storage implementation."""

import ast
from pathlib import Path

from rich.console import Console


def violations() -> list[str]:
    """Find row classes leaking into application or domain modules."""
    problems: list[str] = []
    for path in Path("datakeel").rglob("*.py"):
        if "storage" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "datakeel.storage"
            ):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.Attribute):
                names = [node.attr]
            problems.extend(
                f"{path}:{node.lineno}: persistence row {name} leaves storage"
                for name in names
                if name.endswith("Row")
            )
    return problems


def main() -> None:
    """Fail the gate when storage records escape their transactional boundary."""
    problems = violations()
    Console().print("\n".join(problems) if problems else "Storage row boundaries passed.")
    raise SystemExit(bool(problems))


if __name__ == "__main__":
    main()
