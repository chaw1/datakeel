# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Readable and machine-readable evaluation output from the same measured report."""

from pathlib import Path
from typing import Literal

from rich.console import Console

from datakeel.storage.database import Database


def evaluate(
    db: Database,
    provider: Literal["fake", "openai", "anthropic"] = "fake",
    golden_dir: Path | None = None,
    *,
    json_output: bool = False,
) -> None:
    """Run a suite, show comparison and failures, and fail the command on regression."""
    # Offline recipient commands do not need the conversation engine or model SDKs.
    from datakeel.harness.evaluation import run_evaluation  # noqa: PLC0415

    report = run_evaluation(db, provider, golden_dir)
    console = Console()
    if json_output:
        console.print(
            report.model_dump_json(indent=2), markup=False, highlight=False, soft_wrap=True
        )
    else:
        console.print(f"Golden: {report.passed}/{report.total}; provider={report.provider}")
        console.print(f"Tokens: {report.total_tokens}; cost USD: {report.total_cost_usd}")
        if report.previous_id:
            console.print(
                f"Previous: {report.previous_id}; passed delta={report.passed_delta}; "
                f"token delta={report.token_delta}; cost delta={report.cost_delta}"
            )
        else:
            console.print("Previous: none (first run)")
        for case in report.cases:
            if not case.passed:
                console.print(f"FAIL {case.id}: {'; '.join(case.failures)}", markup=False)
    if report.passed != report.total:
        raise SystemExit(1)
