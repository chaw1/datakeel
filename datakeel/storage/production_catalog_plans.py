# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze catalog and project facts before production action signing and execution."""

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_catalog_parameters import (
    AcceptPackageParams,
    CreateLabelSetParams,
    FinalizeProjectParams,
    ImportPredictionsParams,
    ProductionCatalogActionParams,
    PublishLabelSetParams,
    RegisterModelParams,
    RunPrelabelParams,
    UpgradeProjectTemplateParams,
)
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.core.production_catalog_models import LabelSet
from datakeel.ontology.models import FrozenManifest, FrozenObject, ObjectSet
from datakeel.storage.object_projection import content_digest
from datakeel.storage.production_acceptance import require_inspectable
from datakeel.storage.production_catalog import require_label_set, require_model
from datakeel.storage.production_catalog_impact import migration_impact
from datakeel.storage.production_catalog_rows import (
    ProductionLabelSetRow,
    ProductionModelRow,
    ProductionTemplateRow,
)
from datakeel.storage.production_rows import ProductionTaskRow
from datakeel.storage.production_tasks import require_project, task_view
from datakeel.storage.production_template_upgrade import upgrade_plan


def _freeze(kind: str, identifier: str, value: dict[str, JsonValue]) -> FrozenObject:
    return FrozenObject(
        asset_ref=AssetRef(asset_type=kind, asset_id=identifier),
        properties=value,
        revision=content_digest(value),
    )


def catalog_objects(session: Session, params: ProductionCatalogActionParams) -> list[FrozenObject]:
    """Return exact affected catalog records or project task heads for action impact displays."""
    if isinstance(params, RegisterModelParams):
        row = session.get(ProductionModelRow, params.model.id)
        return [_freeze("model", row.id, row.payload)] if row else []
    if isinstance(params, CreateLabelSetParams) and params.target == "template":
        template = params.template
        row = session.get(ProductionTemplateRow, template.id) if template else None
        return [_freeze("template", row.id, row.payload)] if row else []
    if isinstance(params, CreateLabelSetParams | PublishLabelSetParams):
        return _label_objects(session, params)
    if isinstance(params, AcceptPackageParams | UpgradeProjectTemplateParams):
        return _decision_objects(session, params)
    if isinstance(params, ImportPredictionsParams | RunPrelabelParams | FinalizeProjectParams):
        project = require_project(session, params.project_id)
        objects = [_freeze("project", project.id, project.model_dump(mode="json"))]
        statement = select(ProductionTaskRow).where(ProductionTaskRow.project_id == project.id)
        if isinstance(params, ImportPredictionsParams | RunPrelabelParams):
            model = require_model(session, params.model_id)
            objects.append(_freeze("model", model.id, model.model_dump(mode="json")))
            if params.package_id is not None:
                statement = statement.where(ProductionTaskRow.package_id == params.package_id)
        objects.extend(
            _freeze("production_task", task.id, task_view(task).model_dump(mode="json"))
            for task in session.scalars(statement.order_by(ProductionTaskRow.id))
        )
        return objects
    return []


def _decision_objects(
    session: Session, params: AcceptPackageParams | UpgradeProjectTemplateParams
) -> list[FrozenObject]:
    """Freeze the project and every task head an acceptance or template upgrade depends on.

    A template upgrade also shows its computed plan on the project object.
    """
    if isinstance(params, AcceptPackageParams):
        project, tasks, _ = require_inspectable(session, params)
        value: dict[str, JsonValue] = project.model_dump(mode="json")
    else:
        project = require_project(session, params.project_id)
        plan = upgrade_plan(session, params)
        tasks = list(
            session.scalars(
                select(ProductionTaskRow)
                .where(ProductionTaskRow.project_id == project.id)
                .order_by(ProductionTaskRow.id)
            )
        )
        value = JsonDocument.model_validate(
            {
                "project": project.model_dump(mode="json"),
                "template_upgrade": plan.model_dump(mode="json"),
            }
        ).root
    return [
        _freeze("project", project.id, value),
        *(
            _freeze("production_task", task.id, task_view(task).model_dump(mode="json"))
            for task in tasks
        ),
    ]


def _label_objects(
    session: Session,
    params: CreateLabelSetParams | PublishLabelSetParams,
) -> list[FrozenObject]:
    statement = select(ProductionLabelSetRow).where(
        ProductionLabelSetRow.label_set_id == params.label_set_id,
    )
    if params.version is not None:
        statement = statement.where(ProductionLabelSetRow.version == params.version)
    result: list[FrozenObject] = []
    for row in session.scalars(statement.order_by(ProductionLabelSetRow.version)):
        value = LabelSet.model_validate(row.payload)
        payload = value.model_dump(mode="json")
        if value.previous_version is not None:
            before = require_label_set(session, value.id, value.previous_version)
            annotations, revisions = migration_impact(session, before, value)
            payload.update({"affected_annotations": annotations, "affected_revisions": revisions})
        result.append(
            _freeze("label_set", row.id, payload).model_copy(
                update={
                    "asset_ref": AssetRef(
                        asset_type="label_set", asset_id=row.label_set_id, version=str(row.version)
                    ),
                }
            )
        )
    return result


def catalog_state(session: Session, params: ProductionCatalogActionParams) -> str:
    """Bind signing and execution to current catalog versions and affected revision heads."""
    return content_digest(
        [value.model_dump(mode="json") for value in catalog_objects(session, params)]
    )


def catalog_manifest(session: Session, params: ProductionCatalogActionParams) -> FrozenManifest:
    """Expose catalog targets through the existing immutable plan manifest model."""
    objects = catalog_objects(session, params)
    total_bytes = (
        sum(len(file.content.encode("utf-8")) for file in params.files)
        if isinstance(params, ImportPredictionsParams)
        else 0
    )
    return FrozenManifest(
        query=ObjectSet(object_type="dataset", limit=10000),
        objects=objects,
        state_digest=catalog_state(session, params),
        total_bytes=total_bytes,
    )


def catalog_requires_approval(session: Session, params: ProductionCatalogActionParams) -> bool:
    """Require a human decision when the fake provider's declared estimate exceeds budget."""
    if not isinstance(params, RunPrelabelParams):
        return False
    model = require_model(session, params.model_id)
    statement = select(ProductionTaskRow.id).where(
        ProductionTaskRow.project_id == params.project_id
    )
    if params.package_id is not None:
        statement = statement.where(ProductionTaskRow.package_id == params.package_id)
    count = len(list(session.scalars(statement)))
    return model.estimate_cost(count) > params.budget
