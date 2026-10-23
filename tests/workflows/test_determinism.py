# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compare real step outputs, transition sequences, and complete tool invocation projections."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pytest

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan, get_plan
from datakeel.core.agent_models import ResumeInput
from datakeel.core.models import JsonDocument
from datakeel.core.workflow_models import WorkflowStart
from datakeel.harness.enterprise_cases import seed_enterprise_case
from datakeel.runtime.workflow_service import resume_workflow, start_workflow
from datakeel.storage.tool_invocations import list_invocations
from datakeel.workflows.resolver import lookup
from tests.workflows.conftest import create_dataset, worker_hooks
from tests.workflows.determinism import (
    comparable,
    deterministic_clock_and_ids,
    document,
    fresh_database,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import JsonValue

    from datakeel.storage.database import Database

Kind = Literal["dataset-health", "metric-change", "low-quality-cleanup"]


def _snapshot(db: Database, directory: Path, kind: Kind, *, changed: bool = False) -> JsonDocument:
    if kind == "metric-change":
        seed_enterprise_case(db, directory)
        inputs = JsonDocument(
            {"override": {"measure": {"column": "ecommerce/main/orders/paid_amount"}}}
            if changed
            else {}
        )
    else:
        dataset = create_dataset(db, directory / "dataset")
        inputs = JsonDocument(
            {
                "dataset_id": dataset.id,
                **({"quality_max": 0} if kind == "low-quality-cleanup" else {}),
            }
        )
    events = list(
        start_workflow(
            db,
            kind,
            WorkflowStart(inputs=inputs, idempotency_key="deterministic-start"),
            hooks=worker_hooks(db),
        )
    )
    run = events[-1].run
    if run.status == "PAUSED":
        assert run.pending_plan_id is not None
        plan = get_plan(db, run.pending_plan_id)
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
        events.extend(
            resume_workflow(
                db, run.id, ResumeInput(plan_id=plan.id, idempotency_key="deterministic-resume")
            )
        )
        run = events[-1].run
    assert run.status == "SUCCEEDED", run
    return document(
        {
            "steps": [step.model_dump(mode="json") for step in run.steps],
            "sequence": [
                {
                    "event": item.event,
                    "step_id": item.step_id,
                    "run_status": item.run.status,
                    "states": [[step.id, step.status] for step in item.run.steps],
                }
                for item in events
            ],
            "tools": [item.model_dump(mode="json") for item in list_invocations(db, run.id)],
        }
    )


def _output(snapshot: JsonDocument, identity: str) -> JsonValue:
    steps = snapshot.root["steps"]
    assert isinstance(steps, list)
    step = next(step for step in steps if isinstance(step, dict) and step["id"] == identity)
    assert isinstance(step, dict)
    return step["output"]


@pytest.mark.parametrize("kind", ["dataset-health", "metric-change", "low-quality-cleanup"])
def test_same_initial_data_and_inputs_produce_identical_outputs_and_trace(
    db: Database, tmp_path: Path, kind: Kind
) -> None:
    """Retain all business fields and digests; normalize only generated IDs and times."""
    snapshots: list[JsonDocument] = []
    for _ in range(2):
        with fresh_database(db, tmp_path) as isolated, deterministic_clock_and_ids():
            snapshots.append(_snapshot(isolated, tmp_path, kind))
    assert comparable(snapshots[0].root) == comparable(snapshots[1].root)
    if kind == "metric-change":
        assert lookup(_output(snapshots[0], "before"), "data.result.rows") == [[4979475]]
        assert lookup(_output(snapshots[0], "after"), "data.result.rows") == [[5255975]]
    else:
        total = lookup(_output(snapshots[0], "quality"), "data.total")
        assert isinstance(total, int | float)
        assert 0 <= total <= 100


def test_changed_input_changes_rows_on_the_same_initial_data(db: Database, tmp_path: Path) -> None:
    """A no-op metric override cannot produce the changed monetary answer from another input."""
    snapshots: list[JsonDocument] = []
    for changed in (False, True):
        with fresh_database(db, tmp_path) as isolated, deterministic_clock_and_ids():
            snapshots.append(_snapshot(isolated, tmp_path, "metric-change", changed=changed))
    original = lookup(_output(snapshots[0], "after"), "data.result.rows")
    different = lookup(_output(snapshots[1], "after"), "data.result.rows")
    assert original == [[5255975]]
    assert different == [[4979475]]
    assert comparable(snapshots[0].root) != comparable(snapshots[1].root)
