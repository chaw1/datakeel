# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Graph extraction binds external approval to recomputed frozen inputs and source scope."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.kg.loader import get_profile
from datakeel.storage.action_rows import ActionPlanRow
from datakeel.storage.kg_store import get_job, list_runs
from tests.kg.integration_helpers import install_adapter, prepare_graph, text_dataset

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_external_graph_requires_approval_before_creating_any_worker_task(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No outbound adapter can be reached until the visible external plan is approved."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    profile = get_profile("cloud").model_copy(update={"base_url": "https://example.test/v1"})
    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id: profile)
    adapter = install_adapter(monkeypatch, ())
    plan = prepare_graph(db, dataset, "cloud")
    assert plan.requires_approval
    assert plan.impact.external
    assert plan.impact.kg_estimate is not None
    assert plan.impact.kg_estimate.target_host == "example.test"
    assert plan.impact.kg_estimate.documents == 1
    assert plan.impact.kg_estimate.input_tokens > 0
    with pytest.raises(AuthorizationError, match="human approval"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert list_runs(db) == ()
    assert adapter.calls == 0
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert run.status == "QUEUED"
    assert adapter.calls == 0
    job = get_job(db, list_runs(db)[0].id)
    assert job.prepared.profile == profile
    assert job.prepared.documents[0].text == "Acme uses Widget."


def test_supplied_local_snapshot_cannot_hide_an_external_profile(
    db: Database, tmp_path: Path
) -> None:
    """Preparation recalculates transport, source text and estimates instead of trusting callers."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    local = prepare_graph(db, dataset)
    forged = deepcopy(local.canonical_params)
    forged["profile_id"] = "cloud"
    prepared = forged["prepared"]
    assert isinstance(prepared, dict)
    prepared["external"] = False
    prepared["documents"] = []
    plan = prepare_action(db, "run_kg_extraction", JsonDocument(root=forged))
    assert plan.external
    assert plan.requires_approval
    assert plan.impact.kg_estimate is not None
    assert plan.impact.kg_estimate.documents == 1
    assert plan.canonical_params["prepared"] != prepared


@pytest.mark.parametrize("field", ["profile", "schema_definition", "documents"])
def test_frozen_graph_input_tampering_invalidates_the_approved_digest(
    db: Database, tmp_path: Path, field: str
) -> None:
    """A persisted model, schema or source change cannot reuse the original prepared consent."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    plan = prepare_graph(db, dataset)
    with db.session() as session:
        row = session.get(ActionPlanRow, plan.id)
        assert row is not None
        payload = deepcopy(row.payload)
        prepared = payload["canonical_params"]["prepared"]
        if field == "profile":
            prepared[field]["model"] = "changed-model"
        elif field == "schema_definition":
            prepared[field]["version"] = "changed-version"
        else:
            prepared[field][0]["text"] = "unapproved replacement text"
        row.payload = payload
        session.commit()
    with pytest.raises(ConflictError, match="plan_digest"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert list_runs(db) == ()


def test_unknown_model_price_is_visible_as_unknown_in_external_approval(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An accounting envelope cannot masquerade as a quoted provider tariff or free call."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    profile = get_profile("cloud").model_copy(update={"model": "unpriced-fixture-model"})
    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id: profile)
    plan = prepare_graph(db, dataset, "cloud")
    assert plan.requires_approval
    assert plan.impact.kg_estimate is not None
    assert plan.impact.kg_estimate.cost_upper_usd is None
    assert plan.impact.kg_estimate.price is None
    assert plan.impact.kg_estimate.price_version is None


def test_graph_prepare_rejects_unavailable_version_and_incomplete_file_scope(
    db: Database, tmp_path: Path
) -> None:
    """A frozen plan must contain precisely the selected dataset-version source files."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    with pytest.raises(NotFoundError, match="version"):
        prepare_graph(db, dataset.model_copy(update={"version_id": "missing"}))
    with pytest.raises(ValidationError, match="selection"):
        prepare_graph(db, dataset, file_ids=("missing-file",))
    assert list_runs(db) == ()
