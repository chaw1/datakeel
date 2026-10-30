# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Prove that pytest shards together ran the complete collection exactly once."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from scripts.pytest_shards import (
    OUTCOMES_FILE,
    SELECTION_FILE,
    ShardOutcomes,
    ShardSelection,
    module_of,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_ACCEPTED = ("passed", "skipped")


def _shard_problems(
    full: ShardSelection, shards: Sequence[tuple[ShardSelection, ShardOutcomes | None]], count: int
) -> list[str]:
    problems: list[str] = []
    indexes = sorted(selection.shard.index for selection, _ in shards if selection.shard)
    if indexes != list(range(1, count + 1)):
        problems.append(f"expected shards 1..{count} once each, found {indexes}")
    for selection, outcomes in shards:
        name = "unsharded" if selection.shard is None else f"shard {selection.shard.index}"
        if selection.shard is not None and selection.shard.count != count:
            problems.append(f"{name} was planned for {selection.shard.count} shards, not {count}")
        if Counter(selection.collected) != Counter(full.collected):
            problems.append(f"{name} collected a different suite than the full collection")
        if outcomes is None:
            problems.append(f"{name} has no outcome evidence")
            continue
        unreported = set(selection.selected) - set(outcomes.outcomes)
        if unreported:
            problems.append(f"{name} never reported {len(unreported)} selected tests")
        failed = [node for node, outcome in outcomes.outcomes.items() if outcome not in _ACCEPTED]
        if failed:
            problems.append(f"{name} has {len(failed)} tests that did not pass or skip")
    return problems


def verify(
    full: ShardSelection, shards: Sequence[tuple[ShardSelection, ShardOutcomes | None]], count: int
) -> list[str]:
    """List every reason the shards are not one complete, duplicate-free run of ``full``."""
    problems = _shard_problems(full, shards, count)
    selected = Counter(node for selection, _ in shards for node in selection.selected)
    duplicates = sorted(node for node, seen in selected.items() if seen > 1)
    missing = sorted(set(full.collected) - set(selected))
    unexpected = sorted(set(selected) - set(full.collected))
    if duplicates:
        problems.append(f"{len(duplicates)} tests ran in more than one shard: {duplicates[:5]}")
    if missing:
        problems.append(f"{len(missing)} collected tests ran in no shard: {missing[:5]}")
    if unexpected:
        problems.append(f"{len(unexpected)} tests are absent from the full collection")
    owners = Counter(
        module
        for selection, _ in shards
        for module in {module_of(node) for node in selection.selected}
    )
    split = sorted(module for module, seen in owners.items() if seen > 1)
    if split:
        problems.append(f"{len(split)} modules were split across shards: {split[:5]}")
    return problems


def _load_selection(path: Path) -> ShardSelection:
    return ShardSelection.model_validate_json(path.read_text(encoding="utf-8"))


def _load_shards(root: Path) -> list[tuple[ShardSelection, ShardOutcomes | None]]:
    shards: list[tuple[ShardSelection, ShardOutcomes | None]] = []
    for selection_path in sorted(root.rglob(SELECTION_FILE)):
        outcomes_path = selection_path.with_name(OUTCOMES_FILE)
        selection = _load_selection(selection_path)
        outcomes = (
            _plain_outcomes(
                ShardOutcomes.model_validate_json(outcomes_path.read_text(encoding="utf-8")),
                selection,
            )
            if outcomes_path.is_file()
            else None
        )
        shards.append((selection, outcomes))
    return shards


def _plain_outcomes(outcomes: ShardOutcomes, selection: ShardSelection) -> ShardOutcomes:
    """Key reported results by the plain collection IDs the selection uses."""
    rename = selection.reported_as
    return ShardOutcomes(
        outcomes={rename.get(node, node): outcome for node, outcome in outcomes.outcomes.items()},
        durations={rename.get(node, node): spent for node, spent in outcomes.durations.items()},
    )


def summarize(shards: Sequence[tuple[ShardSelection, ShardOutcomes | None]]) -> Counter[str]:
    """Count final outcomes over every shard, the numbers compared with an unsharded run."""
    return Counter(
        outcome
        for _, outcomes in shards
        if outcomes is not None
        for outcome in outcomes.outcomes.values()
    )


def main() -> None:
    """Fail unless every collected test ran in exactly one shard and passed or skipped."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--count", type=int, required=True)
    args = parser.parse_args()
    full = _load_selection(args.collection / SELECTION_FILE)
    shards = _load_shards(args.shards)
    problems = verify(full, shards, args.count)
    totals = summarize(shards)
    console = Console(soft_wrap=True)
    console.print(
        f"Shards: {len(shards)}/{args.count}; collected {len(full.collected)}; "
        f"passed {totals['passed']}; skipped {totals['skipped']}; "
        f"passed+skipped {totals['passed'] + totals['skipped']}; "
        f"other outcomes {sum(totals.values()) - totals['passed'] - totals['skipped']}",
        markup=False,
    )
    for problem in problems:
        console.print(f"Shard check failed: {problem}", markup=False)
    raise SystemExit(bool(problems))


if __name__ == "__main__":
    main()
