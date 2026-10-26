# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Transcription estimates and actual charges consume explicit synthetic tariffs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan
from datakeel.core.harness_pricing import ModelPrice, PriceTable
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.auto_helpers import install_visual, visual_profile
from tests.worker.image_helpers import image_dataset, prepare_image

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.mark.parametrize("known", [True, False])
def test_auto_tariff_when_known_or_missing_remains_truthful_in_plan_and_report(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, known: bool
) -> None:
    """A made-up tariff proves quoted costs, while a missing model price remains unknown."""
    dataset = image_dataset(db, tmp_path)
    profile = visual_profile(monkeypatch)
    table = PriceTable(
        version_date=date(2026, 1, 1),
        currency="USD",
        unit="per_million_tokens",
        models=[
            ModelPrice(
                model=profile.model if known else "other-fixture-model",
                provider="openai",
                input=Decimal(2),
                output=Decimal(4),
                cache_read=Decimal(0),
                cache_write=Decimal(2),
                source="Synthetic test tariff; not a quoted provider price",
            )
        ],
    )

    def load(_path: Path, _model: type[PriceTable]) -> PriceTable:
        return table

    monkeypatch.setattr("datakeel.storage.kg_pricing.load_contract", load)
    _, requests = install_visual(monkeypatch, {dataset.files[0].sha256: 0.2})
    install_adapter(monkeypatch, (pair_result(),))
    plan = prepare_image(db, dataset)
    estimate = plan.impact.transcription_estimate
    assert estimate is not None
    assert (estimate.cost_upper_usd is not None) == known
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_graph(db, plan)
    assert run.status == "completed"
    assert len(requests) == 1
    assert run.report.transcription_cost_upper_usd == estimate.cost_upper_usd
    if known:
        assert estimate.price == table.models[0]
        assert estimate.cost_upper_usd is not None
        assert run.report.transcription_cost_usd == Decimal("0.000080")
        assert run.report.transcription_cost_usd < estimate.cost_upper_usd
    else:
        assert estimate.price is None
        assert run.report.transcription_cost_usd is None
        assert run.report.cloud_cost_usd is None
        assert run.report.accounted_cost_usd > 0
