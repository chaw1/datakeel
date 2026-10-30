# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Every mutation anchor names one exact line of today's source and an existing test file.

A shard applies its anchors with ``count(before) == 1``; an anchor whose code moved would only
fail inside CI's mutation job, so this catalog check runs with the ordinary tests.
"""

from pathlib import Path

from scripts.mutate import MUTATIONS

ROOT = Path(__file__).resolve().parents[2]


def test_every_anchor_occurs_exactly_once_and_names_an_existing_case() -> None:
    """Moved or duplicated guards and renamed test files are reported together by name."""
    problems: list[str] = []
    names = [mutation.name for mutation in MUTATIONS]
    problems.extend(
        f"duplicate name {name}" for name in sorted(set(names)) if names.count(name) > 1
    )
    for mutation in MUTATIONS:
        source = ROOT / "datakeel" / mutation.path
        if not source.is_file():
            problems.append(f"{mutation.name}: missing {mutation.path}")
            continue
        count = source.read_text(encoding="utf-8").count(mutation.before)
        if count != 1:
            problems.append(f"{mutation.name}: anchor occurs {count} times in {mutation.path}")
        if mutation.runner == "pytest":
            case = ROOT / mutation.case.split("::", 1)[0]
            if not case.is_file():
                problems.append(f"{mutation.name}: missing case file {case.name}")
    assert not problems, problems
