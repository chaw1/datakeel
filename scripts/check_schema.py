# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check frozen schema ownership, transitional imports and infrastructure ratchets."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from configparser import ConfigParser
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from datakeel.core.schema import validate_contributions
from datakeel.persistence.canonical import canonical_schema
from datakeel.persistence.legacy import schema_contributions

if TYPE_CHECKING:
    from collections.abc import Iterator

BASELINE = Path("contracts/persistence/schema-baseline.json")
DATASET_SLICE_BUDGET = 4022
WORKER_SLICE_BUDGET = 1096
CANONICAL = Path("datakeel/persistence/canonical_tables.json")


def import_exceptions(source: str) -> tuple[str, ...]:
    """Count explicit application-layer exceptions without hiding new storage edges."""
    config = ConfigParser()
    config.read_string(source)
    return tuple(config["importlinter:contract:application-layers"]["ignore_imports"].splitlines())


def measurements() -> dict[str, int]:
    """Measure source lines, source files and explicit exception counts."""
    paths = sorted(Path("datakeel/storage").glob("*.py"))
    exceptions = tuple(
        line for line in import_exceptions(Path(".importlinter").read_text()) if line
    )
    return {
        "storage_lines": sum(len(path.read_text().splitlines()) for path in paths),
        "storage_files": len(paths),
        "import_exceptions": len(exceptions),
        "storage_exceptions": sum("datakeel.storage" in line for line in exceptions),
    }


def violations() -> list[str]:
    """Reject drift from the pre-implementation baseline, not from current imports."""
    baseline = json.loads(BASELINE.read_text())
    problems: list[str] = []
    if hashlib.sha256(CANONICAL.read_bytes()).hexdigest() != baseline["canonical_sha256"]:
        problems.append("Frozen canonical table-owner artifact changed")
    validate_contributions(schema_contributions(), canonical_schema())
    for key, actual in measurements().items():
        if actual > baseline["measurements"][key]:
            problems.append(f"{key}: {actual} exceeds frozen {baseline['measurements'][key]}")
    new = {str(path) for path in Path("datakeel/storage").glob("*.py")} - set(
        baseline["storage_paths"]
    )
    problems.extend(f"New storage infrastructure file: {path}" for path in sorted(new))
    schema_paths = [
        Path("datakeel/core/schema.py"),
        *(
            Path("datakeel/storage") / name
            for name in ("base.py", "database.py", "migrations.py", "pg_triggers.py")
        ),
        *(
            p
            for package in ("persistence", "dataset_store", "worker_store")
            for p in Path(f"datakeel/{package}").glob("*.py")
            if (package == "persistence" and p.name not in {"task_completion.py", "task_queue.py"})
            or p.name in {"__init__.py", "rows.py", "schema.py"}
        ),
    ]
    if (
        sum(len(path.read_text().splitlines()) for path in schema_paths)
        > baseline["schema_line_budget"]
    ):
        problems.append("Schema slice source exceeds the frozen 980-line budget")
    problems.extend(_dataset_budget_violations())
    worker_paths = [
        *(
            p
            for p in Path("datakeel/worker_store").glob("*.py")
            if p.name not in {"__init__.py", "rows.py", "schema.py"}
        ),
        Path("datakeel/persistence/task_completion.py"),
        Path("datakeel/persistence/task_queue.py"),
    ]
    if sum(len(p.read_text().splitlines()) for p in worker_paths) > WORKER_SLICE_BUDGET:
        problems.append("Worker slice source exceeds its frozen 1096-line budget")
    problems.extend(_row_import_violations(baseline["legacy_row_imports"]))
    problems.extend(_database_violations())
    return problems


def _dataset_budget_violations() -> list[str]:
    slice_paths = [
        p
        for package in ("datasets", "dataset_store")
        for p in Path(f"datakeel/{package}").glob("*.py")
        if p.name not in {"rows.py", "schema.py"}
    ]
    if sum(len(p.read_text().splitlines()) for p in slice_paths) > DATASET_SLICE_BUDGET:
        return ["Dataset slice source exceeds its frozen 4022-line budget"]
    return []


def _row_import_violations(allowed: dict[str, dict[str, list[str]]]) -> list[str]:
    problems: list[str] = []
    for path in Path("datakeel").rglob("*.py"):
        if path.parts[1] in {"persistence", "dataset_store", "worker_store"}:
            continue
        for module, name, line in _row_references(ast.parse(path.read_text())):
            if module == "datakeel.storage.database":
                problems.append(f"{path}:{line}: database Row re-export consumer")
            if module.startswith(("datakeel.dataset_store", "datakeel.worker_store")):
                permitted = set(allowed.get(str(path), {}).get(module, []))
                if name not in permitted:
                    problems.append(f"{path}:{line}: unlisted transitional Row import")
    return problems


def _row_references(tree: ast.AST) -> Iterator[tuple[str, str, int]]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                aliases[local] = alias.name if alias.asname else local
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{module}.{alias.name}"
                if alias.name.endswith("Row"):
                    yield module, alias.name, node.lineno
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.endswith("Row"):
            qualified = _qualified_attribute(node, aliases)
            if qualified is not None:
                module, _, name = qualified.rpartition(".")
                yield module, name, node.lineno


def _qualified_attribute(node: ast.Attribute, aliases: dict[str, str]) -> str | None:
    parts = [node.attr]
    value = node.value
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name) and value.id in aliases:
        return ".".join((aliases[value.id], *reversed(parts)))
    return None


def _database_violations() -> list[str]:
    problems: list[str] = []
    database = Path("datakeel/storage/database.py")
    for node in ast.walk(ast.parse(database.read_text())):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Row"):
            problems.append("storage.database defines a domain Row")
        if (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("datakeel.")
            and node.module
            not in {
                "datakeel.core.errors",
                "datakeel.core.schema",
                "datakeel.core.settings",
                "datakeel.storage.migrations",
            }
        ):
            problems.append("storage.database imports domain schema wiring")
    return problems


def main() -> None:
    """Optionally compare the packaged copy against the candidate-external frozen oracle."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path)
    args = parser.parse_args()
    problems = violations()
    if args.canonical is not None and args.canonical.read_bytes() != CANONICAL.read_bytes():
        problems.append("Candidate canonical differs from the external frozen table-owner list")
    Console().print("\n".join(problems) if problems else json.dumps(measurements(), sort_keys=True))
    raise SystemExit(bool(problems))


if __name__ == "__main__":
    main()
