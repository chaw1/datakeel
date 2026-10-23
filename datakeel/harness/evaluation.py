# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluate a versioned golden suite and persist its measured comparison report."""

from decimal import Decimal
from pathlib import Path
from typing import Literal

from datakeel.actions.policy import digest
from datakeel.core.harness_eval import EvalReport
from datakeel.core.models import new_id, utcnow
from datakeel.harness.cases import load_cases
from datakeel.harness.execution import run_case
from datakeel.storage.database import Database
from datakeel.storage.harness_evaluations import save_evaluation


def run_evaluation(
    db: Database,
    provider: Literal["fake", "openai", "anthropic"] = "fake",
    golden_dir: Path | None = None,
) -> EvalReport:
    """Run genuine conversations; real providers require an explicit configured switch."""
    cases = load_cases(golden_dir)
    results = [run_case(case, provider) for case in cases]
    report = EvalReport(
        id=new_id(),
        provider=provider,
        suite_digest=digest([case.model_dump(mode="json") for case in cases]),
        created_at=utcnow(),
        passed=sum(result.passed for result in results),
        total=len(results),
        cases=results,
        total_tokens=sum(result.tokens for result in results),
        total_cost_usd=sum((result.cost_usd for result in results), start=Decimal(0)),
    )
    return save_evaluation(db, report)
