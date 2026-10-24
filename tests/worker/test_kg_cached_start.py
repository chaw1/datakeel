# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Cached extraction avoids provider construction and failed construction never spends budget."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import ValidationError
from datakeel.storage.harness_service import list_traces
from tests.kg.integration_helpers import (
    execute_graph,
    install_adapter,
    pair_result,
    prepare_graph,
    text_dataset,
)

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_cached_run_does_not_require_provider_credentials_or_construct_a_client(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing credentials after a successful run cannot prevent fully cached replay."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    adapter = install_adapter(monkeypatch, (pair_result(),))
    assert execute_graph(db, prepare_graph(db, dataset)).status == "completed"

    def unavailable(*_args: object, **_kwargs: object) -> None:
        pytest.fail("A fully cached run attempted provider construction or credential lookup")

    monkeypatch.setattr("datakeel.worker.kg_runner.create_extractor", unavailable)
    repeated = execute_graph(db, prepare_graph(db, dataset))
    assert repeated.status == "completed"
    assert repeated.report.cached == 1
    assert repeated.report.model_calls == 0
    assert adapter.calls == 1


def test_uncached_construction_failure_has_no_call_trace_or_budget_charge(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing provider configuration is a visible failed run before a call is reserved."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))

    def unavailable(*_args: object, **_kwargs: object) -> None:
        message = "No extraction API key configured"
        raise ValidationError(message)

    monkeypatch.setattr("datakeel.worker.kg_runner.create_extractor", unavailable)
    run = execute_graph(db, prepare_graph(db, dataset))
    assert run.status == "failed"
    assert run.report.error is not None
    assert run.report.unexecuted == 1
    assert list_traces(db, run.id) == []
