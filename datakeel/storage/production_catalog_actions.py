# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute production catalog mutations inside the shared signed action transaction."""

from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.actions.production_catalog_parameters import (
    AcceptPackageParams,
    CreateLabelSetParams,
    FinalizeProjectParams,
    ImportPredictionsParams,
    ProductionCatalogActionParams,
    PublishLabelSetParams,
    RegisterModelParams,
    RunPrelabelParams,
)
from datakeel.core.errors import ValidationError
from datakeel.core.models import AssetRef
from datakeel.storage.production_acceptance import accept_package
from datakeel.storage.production_ai_audit import audit_prelabel_run
from datakeel.storage.production_catalog_changes import (
    create_label_set,
    manage_template,
    publish_label_set,
    save_model,
)
from datakeel.storage.production_finalize import finalize_project
from datakeel.storage.production_predictions import import_predictions, run_prelabel
from datakeel.storage.production_prelabel_runs import prelabel_outputs


def _accept(session: Session, plan: ActionPlan, params: AcceptPackageParams) -> OperationResult:
    inspection = accept_package(session, plan, params)
    return OperationResult(
        outputs=[
            AssetRef(asset_type="package_inspection", asset_id=inspection.id),
            AssetRef(asset_type="task_package", asset_id=inspection.package_id),
        ],
        details=inspection.model_dump(mode="json"),
    )


def _prelabel(
    session: Session, plan: ActionPlan, params: ImportPredictionsParams | RunPrelabelParams
) -> OperationResult:
    run = (
        import_predictions(session, params, plan.actor)
        if isinstance(params, ImportPredictionsParams)
        else run_prelabel(session, params, plan.actor, plan_id=plan.id)
    )
    details = run.model_dump(mode="json")
    if run.status == "running":
        # Cloud calls continue after this transaction commits; see action_deferred.
        return OperationResult(outputs=prelabel_outputs(run), details=details, deferred=run.id)
    audit_prelabel_run(session, plan, run)
    return OperationResult(outputs=prelabel_outputs(run), details=details)


def execute_catalog_action(
    session: Session,
    plan: ActionPlan,
    params: ProductionCatalogActionParams,
) -> OperationResult:
    """Dispatch approved catalog writes without opening a nested top-level transaction."""
    if isinstance(params, FinalizeProjectParams):
        return finalize_project(session, params)
    if isinstance(params, AcceptPackageParams):
        return _accept(session, plan, params)
    if isinstance(params, ImportPredictionsParams | RunPrelabelParams):
        return _prelabel(session, plan, params)
    if isinstance(params, CreateLabelSetParams) and params.target == "template":
        template = manage_template(session, params)
        return OperationResult(
            outputs=[
                AssetRef(
                    asset_type="template", asset_id=template.id, version=str(template.revision)
                )
            ],
            details=template.model_dump(mode="json"),
        )
    if isinstance(params, CreateLabelSetParams | PublishLabelSetParams):
        labels = (
            create_label_set(session, params)
            if isinstance(params, CreateLabelSetParams)
            else publish_label_set(session, params)
        )
        return OperationResult(
            outputs=[
                AssetRef(asset_type="label_set", asset_id=labels.id, version=str(labels.version))
            ],
            details=labels.model_dump(mode="json"),
        )
    if isinstance(params, RegisterModelParams):
        model = save_model(session, params)
        return OperationResult(
            outputs=[AssetRef(asset_type="model", asset_id=model.id, version=str(model.revision))],
            details=model.model_dump(mode="json"),
        )
    message = "Unknown production catalog action parameters"
    raise ValidationError(message)
