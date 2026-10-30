# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Merge mutation shard reports and judge the union with the unsharded gate's rules."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field
from rich.console import Console

from datakeel.core.harness_eval import EvalReport
from datakeel.core.models import BoundaryModel
from scripts.mutate import MUTATIONS
from scripts.mutation_models import MutationResult, TestMeasurement
from scripts.mutation_shards import select_mutations
from scripts.mutation_timeouts import EnvironmentFailure
from scripts.shard_spec import parse_shard

if TYPE_CHECKING:
    from collections.abc import Sequence

    from scripts.mutation_models import Mutation


class ShardReport(BoundaryModel):
    """One ``scripts/mutate.py --shard K/N --output`` report."""

    shard: str
    baseline: EvalReport | None
    image_baselines: list[TestMeasurement]
    mutations: list[MutationResult]
    environment_failures: list[EnvironmentFailure] = Field(default_factory=list)


def _report_problems(report: ShardReport, expected: tuple[Mutation, ...]) -> list[str]:
    name = f"shard {report.shard}"
    problems = [f"{name}: {failure.describe()}" for failure in report.environment_failures]
    if report.baseline is None or report.baseline.passed != report.baseline.total:
        problems.append(f"{name}: golden baseline is missing or not green")
    pytest_cases = [mutation for mutation in expected if mutation.runner == "pytest"]
    if len(report.image_baselines) != len(pytest_cases) or any(
        result.exit_code != 0 or result.passed != result.total for result in report.image_baselines
    ):
        problems.append(f"{name}: pytest baselines are incomplete or not green")
    measured = [result.name for result in report.mutations]
    if measured != [mutation.name for mutation in expected]:
        problems.append(
            f"{name}: measured {len(measured)} of its {len(expected)} catalog mutations"
        )
    survived = [result.name for result in report.mutations if not result.killed]
    if survived:
        problems.append(f"{name}: survived {survived}")
    return problems


def judge(
    reports: Sequence[ShardReport], count: int, catalog: Sequence[Mutation] = MUTATIONS
) -> list[str]:
    """List every reason the shards do not prove the whole catalog was killed exactly once."""
    specs = [parse_shard(report.shard) for report in reports]
    problems: list[str] = []
    if sorted(spec.index for spec in specs) != list(range(1, count + 1)) or any(
        spec.count != count for spec in specs
    ):
        problems.append(f"expected shards 1..{count} of {count}, found {[str(s) for s in specs]}")
    for report, spec in zip(reports, specs, strict=True):
        problems.extend(_report_problems(report, select_mutations(catalog, spec)))
    names = Counter(result.name for report in reports for result in report.mutations)
    catalog_names = Counter(mutation.name for mutation in catalog)
    if names != catalog_names:
        problems.append(
            f"merged reports cover {sum(names.values())} results for "
            f"{len(catalog_names)} catalog mutations"
        )
    return problems


def main() -> None:
    """Fail unless every shard is green at baseline and every catalog mutation was killed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    reports = [
        ShardReport.model_validate_json(path.read_text(encoding="utf-8")) for path in args.reports
    ]
    problems = judge(reports, args.count, MUTATIONS)
    results = [result for report in reports for result in report.mutations]
    killed = sum(result.killed for result in results)
    console = Console(soft_wrap=True, highlight=False)
    console.print(
        f"Mutation shards: {len(reports)}/{args.count}; measured {len(results)} of "
        f"{len(MUTATIONS)}; killed {killed}; survived {len(results) - killed}; environment "
        f"failures {sum(len(report.environment_failures) for report in reports)}",
        markup=False,
    )
    for problem in problems:
        console.print(f"Mutation gate failed: {problem}", markup=False)
    if args.output:
        order = {mutation.name: position for position, mutation in enumerate(MUTATIONS)}
        merged = {
            "shards": [report.model_dump(mode="json", exclude={"mutations"}) for report in reports],
            "mutations": [
                result.model_dump(mode="json")
                for result in sorted(results, key=lambda result: order.get(result.name, -1))
            ],
        }
        args.output.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
    raise SystemExit(bool(problems))


if __name__ == "__main__":
    main()
