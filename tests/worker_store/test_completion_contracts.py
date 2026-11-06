# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Mechanical completion boundaries, ownership and fixed slice budgets."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.worker_store.completion import (
    CompletionRequest,
    CompletionResult,
    ExpirationResult,
    TaskCompletionPort,
)
from scripts import check_boundaries, check_schema
from scripts.check_coverage import belongs_to_package

if TYPE_CHECKING:
    from pathlib import Path


def test_completion_port_schema_contains_only_frozen_models() -> None:
    """Request/result contracts offer no database, Row or untyped parameter escape hatch."""
    for model in (CompletionRequest, CompletionResult, ExpirationResult):
        schema = model.model_json_schema()
        assert schema["additionalProperties"] is False
        assert model.model_config["frozen"]
        assert not {"session", "row", "db", "kind"} & model.model_fields.keys()
    assert tuple(TaskCompletionPort.__annotations__) == ()
    assert set(TaskCompletionPort.complete.__annotations__) == {"request", "return"}


def test_worker_coverage_keeps_moved_implementations_and_wiring() -> None:
    """Both critical owners retain queue logic; composition adapters gain the same 90% gate."""
    for name in (
        "completion",
        "task_queue",
        "task_terminal",
        "task_models",
        "task_queries",
        "task_views",
    ):
        path = f"datakeel/worker_store/{name}.py"
        assert belongs_to_package(path, "worker")
        assert belongs_to_package(path, "worker_store")
    for name in ("task_completion", "task_queue", "task_vector", "task_queries"):
        path = f"datakeel/persistence/{name}.py"
        assert belongs_to_package(path, "worker")
        assert belongs_to_package(path, "worker_store")
        assert belongs_to_package(path, "persistence")


def test_worker_budget_rejects_growth_without_borrowing_schema_or_dataset_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The S3 implementation and wiring are measured together beneath their own fixed cap."""
    monkeypatch.setattr(check_schema, "WORKER_SLICE_BUDGET", 0)
    assert "Worker slice source exceeds its frozen 1096-line budget" in check_schema.violations()


@pytest.mark.parametrize("module", ["domain/port", "worker/completion", "datasets/projection"])
def test_worker_rows_cannot_cross_public_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module: str,
) -> None:
    """Moving tasks does not authorize public ports or application adapters to import Rows."""
    monkeypatch.chdir(tmp_path)
    path = tmp_path / f"datakeel/{module}.py"
    path.parent.mkdir(parents=True)
    path.write_text("from datakeel.worker_store.rows import TaskRow\n")
    assert check_boundaries.violations()
    assert check_schema._row_import_violations({})  # noqa: SLF001  # Exercise the public boundary.
