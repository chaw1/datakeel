# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject superlinear manifest merging using fourfold inputs and a real quadratic mutant."""

import argparse
import os
import statistics
from collections.abc import Callable, Iterator
from time import perf_counter

from rich.console import Console

from datakeel.core.models import FileItem
from datakeel.storage import version_diff
from scripts.scale_bench.common import fingerprint
from scripts.scale_bench.datasets import run as dataset_run
from scripts.scale_bench.isolation import isolated
from scripts.scale_bench.models import BenchModel, Config

_SMALL = 2048
_FACTOR = 4
_MAX_GROWTH = 9.0
_WINDOW_SECONDS = 0.035
_ORDERED_MERGE = version_diff.merge_pairs


class Growth(BenchModel):
    """Per-call medians and the machine-independent growth decision."""

    small_count: int
    large_count: int
    small_seconds: float
    large_seconds: float
    ratio: float
    passed: bool
    fixture_sha256: str


def _files(count: int) -> list[FileItem]:
    return [
        FileItem(id=f"file-{index:09d}", path="", filename=f"{index}.txt") for index in range(count)
    ]


def _per_call(operation: Callable[[], object]) -> float:
    elapsed, calls = 0.0, 0
    started = perf_counter()
    while elapsed < _WINDOW_SECONDS:
        operation()
        calls += 1
        elapsed = perf_counter() - started
    return elapsed / calls


def _measure(files: list[FileItem]) -> float:
    def merge() -> None:
        matched = sum(
            left == right for left, right in version_diff.merge_pairs(iter(files), iter(files))
        )
        if matched != len(files):
            message = "Merge lost file identities"
            raise AssertionError(message)

    return _per_call(merge)


def growth() -> Growth:
    """Measure alternating input sizes, with independent median windows to reduce noise."""
    small, large = _files(_SMALL), _files(_SMALL * _FACTOR)
    observations: tuple[list[float], list[float]] = ([], [])
    for index in range(3):
        order = (0, 1) if index % 2 == 0 else (1, 0)
        for which in order:
            observations[which].append(_measure((small, large)[which]))
    baseline, expanded = (statistics.median(values) for values in observations)
    ratio = expanded / baseline
    return Growth(
        small_count=len(small),
        large_count=len(large),
        small_seconds=baseline,
        large_seconds=expanded,
        ratio=ratio,
        passed=ratio <= _MAX_GROWTH,
        fixture_sha256=fingerprint(
            {"generator": "ordered-identities-v1", "small": _SMALL, "factor": _FACTOR}
        ),
    )


def _quadratic(
    before: Iterator[FileItem], after: Iterator[FileItem]
) -> Iterator[tuple[FileItem | None, FileItem | None]]:
    # Repeat identity lookup before each real merge result, preserving all merge behavior.
    left, right = list(before), list(after)
    for before_item, after_item in _ORDERED_MERGE(iter(left), iter(right)):
        value = before_item if before_item is not None else after_item
        if value is not None:
            next((item for item in left if item.id == value.id), None)
            next((item for item in right if item.id == value.id), None)
        yield before_item, after_item


class Mutation:
    """Temporarily inject a behavior-preserving quadratic implementation into production merge."""

    def __enter__(self) -> None:
        """Replace the production function for the negative-control measurement only."""
        self.original = version_diff.merge_pairs
        version_diff.merge_pairs = _quadratic

    def __exit__(self, *_args: object) -> None:
        """Restore the production function even when its assertion rejects the mutant."""
        version_diff.merge_pairs = self.original


def _scenario_smoke() -> None:
    stack = "postgres" if os.environ.get("DATAKEEL_TEST_DATABASE_URL") else "sqlite"
    with isolated(Config(scenario="B1", size="S", stack=stack, repeats=2)) as context:
        result = dataset_run(context)
    Console().print_json(result.model_dump_json())


def main() -> None:
    """Fail on a regression and prove that the identical validator rejects an O(n²) mutation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-mutation", action="store_true")
    parser.add_argument("--mutation", action="store_true")
    args = parser.parse_args()
    if args.mutation:
        with Mutation():
            result = growth()
    else:
        result = growth()
    Console().print_json(result.model_dump_json())
    if not result.passed:
        message = "Fourfold merge growth exceeded 9x"
        raise SystemExit(message)
    _scenario_smoke()
    if args.verify_mutation:
        with Mutation():
            mutant = growth()
        Console().print_json(mutant.model_dump_json())
        if mutant.passed:
            message = "Quadratic mutation escaped the complexity guard"
            raise SystemExit(message)
        Console().print("Quadratic mutation rejected by the same growth guard.")


if __name__ == "__main__":
    main()
