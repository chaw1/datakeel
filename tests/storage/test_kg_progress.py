# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Terminal graph failures preserve committed block progress and model accounting."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan
from datakeel.core.errors import ConflictError
from datakeel.kg.loader import get_profile
from datakeel.storage.harness_service import list_traces
from datakeel.worker.kg_execution import KGExecution
from tests.kg.integration_helpers import (
    execute_graph,
    install_adapter,
    pair_result,
    prepare_graph,
    text_dataset,
)

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.kg_contracts import ExtractionProfile
    from datakeel.core.kg_execution import KGDocument
    from datakeel.core.kg_models import ExtractionResult, TextBlock
    from datakeel.storage.database import Database


@pytest.mark.parametrize("known_price", [True, False])
def test_terminal_failure_retains_completed_blocks_and_all_billed_calls(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, known_price: bool
) -> None:
    """A later publication failure must not reset the first block or either provider charge."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget. A.", "Acme uses Widget. B."))
    profile = get_profile("cloud")
    if not known_price:
        profile = profile.model_copy(update={"model": "fixture-unknown"})

    def selected_profile(_id: str) -> ExtractionProfile:
        return profile

    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", selected_profile)
    result = pair_result().model_copy(update={"input_tokens": 80, "output_tokens": 25})
    install_adapter(monkeypatch, (result, result))

    class InterruptedExecution(KGExecution):
        """Inject failure between receiving a billed response and completing its product."""

        def _assemble(
            self, document: KGDocument, block: TextBlock, result: ExtractionResult
        ) -> None:
            if self.products:
                reason = "Generated publication failure after provider usage"
                raise ConflictError(reason)
            super()._assemble(document, block, result)

    monkeypatch.setattr("datakeel.worker.kg_runner.KGExecution", InterruptedExecution)
    plan = prepare_graph(db, dataset, "cloud")
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_graph(db, plan)
    traces = list_traces(db, run.id)
    assert run.status == "failed"
    assert (run.report.extracted, run.report.unexecuted, run.report.model_calls) == (1, 1, 2)
    assert (run.report.input_tokens, run.report.output_tokens) == (160, 50)
    expected = sum((trace.cost_usd for trace in traces), start=Decimal(0))
    assert expected > 0
    assert run.report.accounted_cost_usd == expected
    assert run.report.cost_usd == (expected if known_price else None)
