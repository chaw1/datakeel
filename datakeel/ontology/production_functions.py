# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose authoritative production queries to both read-only tool transports."""

from typing import TYPE_CHECKING

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument
from datakeel.core.production_reads import (
    LabelSetDiffParams,
    NextTaskParams,
    PackageReadParams,
    ProductionObjectQuery,
    ProjectReadParams,
)
from datakeel.ontology.models import FunctionResult
from datakeel.storage.database import Database
from datakeel.storage.production_objects import label_set_difference, production_objects
from datakeel.storage.production_queries import get_project, next_task, project_progress
from datakeel.storage.production_statistics import (
    annotator_workload,
    confidence_distribution,
    production_agreement,
    production_prelabel_accuracy,
)

if TYPE_CHECKING:
    from collections.abc import Callable

PRODUCTION_READ_MODELS: dict[str, type[BoundaryModel]] = {
    "project_progress": ProjectReadParams,
    "package_status": PackageReadParams,
    "annotator_workload": ProjectReadParams,
    "rework_rate": ProjectReadParams,
    "annotation_consistency": ProjectReadParams,
    "prelabel_confidence": ProjectReadParams,
    "production_prelabel_accuracy": ProjectReadParams,
    "label_set_diff": LabelSetDiffParams,
    "next_task": NextTaskParams,
    "production_objects": ProductionObjectQuery,
}


def invoke_production(
    db: Database, name: str, arguments: JsonDocument, caller: AccessContext
) -> FunctionResult:
    """Read exact counters, current provenance, vocabularies or next eligible task."""
    if name == "production_objects":
        objects = production_objects(db, ProductionObjectQuery.model_validate(arguments.root))
        return FunctionResult(
            function=name,
            asset_refs=[value.asset_ref for value in objects],
            data=[value.model_dump(mode="json") for value in objects],
        )
    if name == "label_set_diff":
        query = LabelSetDiffParams.model_validate(arguments.root)
        result = label_set_difference(db, query)
        return FunctionResult(
            function=name,
            asset_refs=[AssetRef(asset_type="label_set", asset_id=query.label_set_id)],
            data=result.model_dump(mode="json"),
        )
    project_id = ProjectReadParams.model_validate(
        {"project_id": arguments.root.get("project_id")}
    ).project_id
    project = get_project(db, project_id)
    value = _project_read(db, name, arguments, caller)
    return FunctionResult(
        function=name,
        asset_refs=[
            AssetRef(asset_type="project", asset_id=project.id),
            AssetRef(asset_id=project.dataset_id, version=project.version_id),
        ],
        data=value.model_dump(mode="json") if value is not None else None,
    )


def _project_read(
    db: Database, name: str, arguments: JsonDocument, caller: AccessContext
) -> BoundaryModel | None:
    if name == "next_task":
        query = NextTaskParams.model_validate(arguments.root)
        return next_task(db, query.project_id, caller.actor, query.package_id)
    if name == "package_status":
        query = PackageReadParams.model_validate(arguments.root)
        return project_progress(db, query.project_id, query.package_id)
    project = ProjectReadParams.model_validate(arguments.root)
    readers: dict[str, Callable[[Database, str], BoundaryModel]] = {
        "project_progress": project_progress,
        "prelabel_confidence": confidence_distribution,
        "production_prelabel_accuracy": production_prelabel_accuracy,
        "annotation_consistency": production_agreement,
    }
    return readers.get(name, annotator_workload)(db, project.project_id)
