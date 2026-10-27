# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Signed inspection actions freeze complete sampled units and retain every reviewed error."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, list_runs, prepare_action
from datakeel.core.annotation_sampling import SamplingRequest
from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.storage.annotation_rework import export_rework
from datakeel.storage.annotation_rows import AnnotationBatchRow, AnnotationSamplingRow
from datakeel.storage.annotation_sampling import create_sampling_plan
from datakeel.storage.annotation_store import get_annotation_quality
from tests.storage.test_annotation_store import AnnotationFixture, annotations

if TYPE_CHECKING:
    from datakeel.actions.models import ActionPlan
    from datakeel.storage.database import Database

__all__ = ["annotations"]


def inspection_params(db: Database, fixture: AnnotationFixture) -> JsonDocument:
    """Review the actual frozen sample, including one explicitly described defective unit."""
    sample = create_sampling_plan(
        db,
        fixture.dataset_id,
        SamplingRequest(batch_id=fixture.report.id, method="ratio", ratio=0.1, acceptance_number=0),
    )
    return JsonDocument(
        {
            "dataset_id": fixture.dataset_id,
            "version_id": fixture.version_id,
            "batch_id": fixture.report.id,
            "sampling_id": sample.id,
            "checks": [
                {"sample_id": identifier, "defective": index == 0, "reason": "Wrong class"}
                for index, identifier in enumerate(sample.sample_ids)
            ],
        }
    )


def approved_plan(db: Database, fixture: AnnotationFixture) -> ActionPlan:
    """Prepare and approve a real annotation inspection through the established boundary."""
    plan = prepare_action(db, "annotation_acceptance", inspection_params(db, fixture))
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    return plan


def test_inspection_requires_human_approval_and_archives_error_details(
    db: Database, annotations: AnnotationFixture
) -> None:
    """Denied execution produces no acceptance fact; approved execution persists rejection."""
    plan = prepare_action(db, "annotation_acceptance", inspection_params(db, annotations))
    assert plan.requires_approval
    with pytest.raises(AuthorizationError, match="human approval"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert list_runs(db)[0].status == "DENIED"
    assert get_annotation_quality(db, annotations.dataset_id).inspections == ()
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    request = ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id)
    run = execute_plan(db, plan.id, request)
    assert execute_plan(db, plan.id, request) == run
    inspection = get_annotation_quality(db, annotations.dataset_id).inspections[0]
    assert (inspection.accepted, inspection.defective_count, inspection.actor) == (
        False,
        1,
        "local",
    )
    assert inspection.checks[0].sample_id
    assert "Wrong class" in export_rework(
        db, annotations.dataset_id, annotations.report.id, csv_format=True
    )
    assert "inspection_error" in export_rework(
        db, annotations.dataset_id, annotations.report.id, csv_format=False
    )


def test_inspection_prepare_rejects_partial_sample_and_missing_scope(
    db: Database, annotations: AnnotationFixture
) -> None:
    """Review membership and action scope are enforced before any signable plan exists."""
    params = inspection_params(db, annotations)
    checks = params.root["checks"]
    assert isinstance(checks, list)
    with pytest.raises(ValidationError, match="every frozen sampled unit"):
        prepare_action(
            db, "annotation_acceptance", JsonDocument({**params.root, "checks": checks[:1]})
        )
    with pytest.raises(AuthorizationError, match="annotations:accept"):
        prepare_action(
            db, "annotation_acceptance", params, ActionContext(scopes=["datasets:write"])
        )


@pytest.mark.parametrize("changed", ["batch", "report", "sample"])
def test_inspection_rechecks_frozen_annotations_metrics_and_sample_before_execution(
    db: Database, annotations: AnnotationFixture, changed: str
) -> None:
    """An approved plan cannot accept substituted annotation inputs, reports or selections."""
    plan = approved_plan(db, annotations)
    with db.session() as session:
        batch = session.get(AnnotationBatchRow, annotations.report.id)
        assert batch is not None
        if changed == "batch":
            batch.batch = {**batch.batch, "iou_threshold": 0.6}
        elif changed == "report":
            batch.report = {**batch.report, "name": "Changed after approval"}
        else:
            sample_id = str(plan.canonical_params["sampling_id"])
            sample = session.get(AnnotationSamplingRow, sample_id)
            assert sample is not None
            sample.payload = {**sample.payload, "seed": 99}
        session.commit()
    with pytest.raises(ConflictError, match=r"digest|state|selection"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert get_annotation_quality(db, annotations.dataset_id).inspections == ()


def test_rejected_inspection_approval_and_different_actor_cannot_publish(
    db: Database, annotations: AnnotationFixture
) -> None:
    """Neither rejected approval nor an arbitrary execute actor grants acceptance authority."""
    plan = prepare_action(db, "annotation_acceptance", inspection_params(db, annotations))
    approve_plan(db, plan.id, ApprovalDecision(approve=False, plan_digest=plan.plan_digest))
    with pytest.raises(ConflictError, match="rejected"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    approved = approved_plan(db, annotations)
    with pytest.raises(AuthorizationError, match="actor"):
        execute_plan(
            db, approved.id, ExecuteRequest(plan_digest=approved.plan_digest, actor="other")
        )
    assert get_annotation_quality(db, annotations.dataset_id).inspections == ()
