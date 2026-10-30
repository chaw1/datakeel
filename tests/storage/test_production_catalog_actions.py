# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Production catalog actions share human approval, receipts and retry identities."""

import pytest

from datakeel.actions.models import ActionRun, ApprovalDecision, ExecuteRequest
from datakeel.actions.production_catalog_parameters import (
    CreateLabelSetParams,
    FinalizeProjectParams,
    ImportPredictionsParams,
    ProductionCatalogActionParams,
    PublishLabelSetParams,
    RegisterModelParams,
    RunPrelabelParams,
    UpdateModelParams,
)
from datakeel.actions.production_parameters import SaveRevisionParams, SubmitTaskParams
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import JsonDocument
from datakeel.core.production_catalog_models import (
    PredictionFile,
    ProductionLabel,
    ProductionModel,
    ProductionTemplate,
)
from datakeel.storage.database import Database
from datakeel.storage.production_catalog import require_label_set, require_model, require_template
from datakeel.storage.production_reviews import submit_task
from datakeel.storage.production_revisions import append_revision, current_revision
from datakeel.storage.production_tasks import require_task
from tests.storage.production_catalog_fixtures import catalog_project


def _execute(db: Database, name: str, params: ProductionCatalogActionParams) -> ActionRun:
    plan = prepare_action(db, name, JsonDocument(params.model_dump(mode="json")))
    if plan.requires_approval:
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    request = ExecuteRequest(plan_digest=plan.plan_digest)
    run = execute_plan(db, plan.id, request)
    assert run.status == "SUCCEEDED"
    assert execute_plan(db, plan.id, request) == run
    assert prepare_action(db, name, JsonDocument(params.model_dump(mode="json"))).id == plan.id
    return run


def test_catalog_actions_publish_and_update_only_through_signed_boundaries(db: Database) -> None:
    """Label publication, models and templates all retain the common action receipt contract."""
    labels = CreateLabelSetParams(
        request_id="labels", label_set_id="labels", labels=(ProductionLabel(id="a", name="a"),)
    )
    _execute(db, "create_label_set", labels)
    params = PublishLabelSetParams(request_id="publish", label_set_id="labels", version=1)
    plan = prepare_action(db, "publish_label_set", JsonDocument(params.model_dump(mode="json")))
    assert plan.requires_approval
    with pytest.raises(AuthorizationError, match="human approval"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    _execute(db, "publish_label_set", params)
    model = ProductionModel(id="model", name="Offline", version="one", provider="import")
    _execute(db, "register_model", RegisterModelParams(request_id="register", model=model))
    _execute(
        db,
        "update_model",
        UpdateModelParams(
            request_id="update",
            expected_revision=1,
            model=model.model_copy(update={"version": "two"}),
        ),
    )
    template = ProductionTemplate(id="template", name="Boxes")
    _execute(
        db,
        "create_label_set",
        CreateLabelSetParams(request_id="template", target="template", template=template),
    )
    with db.session() as session:
        assert require_label_set(session, "labels", 1).published
        assert require_model(session, "model").version == "two"
        assert require_template(session, "template").annotation_type == "box"


def test_prelabel_import_and_finalization_have_versioned_receipts(db: Database) -> None:
    """Budget overruns gate a local fake model, and finalization names the originating project."""
    fixture = catalog_project(db)
    params = RunPrelabelParams(
        request_id="fake", project_id=fixture.project.id, model_id="fake", budget=0
    )
    plan = prepare_action(db, "run_prelabel", JsonDocument(params.model_dump(mode="json")))
    assert plan.requires_approval
    assert not plan.external
    _execute(db, "run_prelabel", params)
    imported = _execute(
        db,
        "import_predictions",
        ImportPredictionsParams(
            request_id="import",
            project_id=fixture.project.id,
            model_id="fake",
            format="yolo",
            files=(PredictionFile(filename="sample-0.txt", content="0 0.5 0.5 0.5 0.5"),),
        ),
    )
    assert imported.receipt is not None
    with db.session() as session:
        for task in fixture.tasks:
            row = require_task(session, task.id)
            head = current_revision(session, row)
            assert head is not None
            append_revision(
                session,
                row,
                SaveRevisionParams(
                    request_id=f"confirm-{task.id}",
                    task_id=task.id,
                    previous_revision_id=head.id,
                    annotation=head.annotation.model_copy(update={"annotator_id": "local"}),
                ),
                "local",
            )
            submit_task(session, SubmitTaskParams(request_id=task.id, task_id=task.id), "local")
        session.commit()
    run = _execute(
        db,
        "finalize_project",
        FinalizeProjectParams(request_id="finalize", project_id=fixture.project.id),
    )
    assert run.receipt is not None
    assert any(
        item.asset_type == "project" and item.asset_id == fixture.project.id
        for item in run.receipt.inputs
    )
    assert any(item.asset_type == "version" for item in run.receipt.outputs)
