# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Enforce measured package coverage, without excluding difficult paths."""

import xml.etree.ElementTree as ET
from fnmatch import fnmatch
from pathlib import Path

from rich.console import Console

CRITICAL_PACKAGES = (
    "core",
    "lineage",
    "actions",
    "worker",
    "harness",
    "agent",
    "runtime",
    "workflows",
    "ontology",
    "evidence",
    "operators/evidence",
    "catalog",
    "metrics",
    "ask",
    "cli/evidence_benchmark.py",
)
MINIMUM_COVERAGE = 90
STORAGE_IMPLEMENTATIONS = {
    "lineage": ("events.py", "lineage_service.py"),
    "actions": ("action_*.py", "file_state.py"),
    "worker": ("task_queue.py", "task_queries.py", "task_models.py", "task_terminal.py"),
    "harness": ("harness_*.py", "budget_*.py"),
    "agent": ("conversation_*.py",),
    "runtime": ("checkpoint_*.py",),
    "workflows": ("workflow_*.py",),
    "ontology": ("object_*.py", "tool_*.py"),
    "evidence": ("evidence_*.py",),
    "catalog": ("catalog_*.py",),
    "metrics": ("metric*.py",),
    "ask": ("ask_*.py",),
}


def belongs_to_package(name: str, package: str) -> bool:
    """Include transactional implementations when a domain uses storage services."""
    return (
        name == f"datakeel/{package}"
        or name.startswith(f"datakeel/{package}/")
        or any(
            fnmatch(name, f"datakeel/storage/{pattern}")
            for pattern in STORAGE_IMPLEMENTATIONS.get(package, ())
        )
    )


def main() -> None:
    """Read pytest-cov output and check every implemented critical package."""
    # This file is generated locally by pytest-cov in the preceding make target.
    report = ET.fromstring(Path("coverage.xml").read_text())  # noqa: S314
    files = report.findall(".//class")
    failures: list[str] = []
    for package in CRITICAL_PACKAGES:
        lines = [
            line
            for entry in files
            if belongs_to_package(
                "datakeel/" + entry.attrib["filename"].removeprefix("datakeel/"), package
            )
            for line in entry.findall("./lines/line")
        ]
        statements = len(lines)
        covered = sum(int(line.attrib["hits"]) > 0 for line in lines)
        percentage = 100 * covered / statements if statements else 0
        Console().print(f"{package}: {percentage:.2f}%")
        if percentage < MINIMUM_COVERAGE:
            failures.append(package)
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
