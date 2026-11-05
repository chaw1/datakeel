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

from rich.console import Console

from datakeel.core.schema import validate_contributions
from datakeel.persistence.canonical import canonical_schema
from datakeel.persistence.legacy import schema_contributions

BASELINE = Path("contracts/persistence/schema-baseline.json")
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
        ),
    ]
    if (
        sum(len(path.read_text().splitlines()) for path in schema_paths)
        > baseline["schema_line_budget"]
    ):
        problems.append("Schema slice source exceeds the frozen 980-line budget")
    problems.extend(_row_import_violations(baseline["legacy_row_imports"]))
    problems.extend(_database_violations())
    return problems


def _row_import_violations(allowed: dict[str, dict[str, list[str]]]) -> list[str]:
    problems: list[str] = []
    for path in Path("datakeel").rglob("*.py"):
        if path.parts[1] in {"persistence", "dataset_store", "worker_store"}:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ImportFrom):
                continue
            rows = {alias.name for alias in node.names if alias.name.endswith("Row")}
            module = node.module or ""
            if module == "datakeel.storage.database" and rows:
                problems.append(f"{path}:{node.lineno}: database Row re-export consumer")
            if module in {"datakeel.dataset_store.rows", "datakeel.worker_store.rows"}:
                permitted = set(allowed.get(str(path), {}).get(module, []))
                if rows - permitted:
                    problems.append(f"{path}:{node.lineno}: unlisted transitional Row import")
    return problems


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
