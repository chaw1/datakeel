# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose authoritative production queries to both read-only tool transports."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument, utcnow
from datakeel.core.production_models import ReworkRateWorkload
from datakeel.core.production_reads import (
    AssigneesParams,
    LabelSetDiffParams,
    LeaseStatusParams,
    NextTaskParams,
    PackageAcceptanceParams,
    PackageReadParams,
    ProductionObjectQuery,
    ProjectReadParams,
    ReworkRateParams,
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
from datakeel.storage.production_team_reads import (
    lease_status,
    package_acceptance_status,
    skill_workload,
)
from datakeel.storage.workbench_assignees import assignees

if TYPE_CHECKING:
    from collections.abc import Callable

TEAM_READS = frozenset({"lease_status", "skill_workload", "package_acceptance"})
PRODUCTION_READ_MODELS: dict[str, type[BoundaryModel]] = {
    "project_progress": ProjectReadParams,
    "package_status": PackageReadParams,
    "annotator_workload": ProjectReadParams,
    "rework_rate": ReworkRateParams,
    "annotation_consistency": ProjectReadParams,
    "prelabel_confidence": ProjectReadParams,
    "production_prelabel_accuracy": ProjectReadParams,
    "label_set_diff": LabelSetDiffParams,
    "next_task": NextTaskParams,
    "production_objects": ProductionObjectQuery,
    "lease_status": LeaseStatusParams,
    "skill_workload": ProjectReadParams,
    "package_acceptance": PackageAcceptanceParams,
    "assignees": AssigneesParams,
}


def _review_bounds(
    query: ReworkRateParams, reference: datetime
) -> tuple[str | None, int | None, datetime | None, datetime | None, bool]:
    if query.since is not None or query.until is not None:
        start = query.since.astimezone(UTC) if query.since is not None else None
        end = query.until.astimezone(UTC) if query.until is not None else None
        return query.window or "custom", query.days, start, end, False
    if query.days is not None:
        return query.window, query.days, reference - timedelta(days=query.days), reference, False
    if query.window is None or query.window == "all_time":
        return query.window, None, None, None, False
    day_start = reference.replace(hour=0, minute=0, second=0, microsecond=0)
    monday = day_start - timedelta(days=day_start.weekday())
    presets: dict[str, tuple[datetime, datetime, bool]] = {
        "today": (day_start, reference, False),
        "this_week": (monday, reference, False),
        "last_week": (monday - timedelta(days=7), monday, True),
        "this_month": (day_start.replace(day=1), reference, False),
        "last_7_days": (reference - timedelta(days=7), reference, False),
        "last_30_days": (reference - timedelta(days=30), reference, False),
    }
    start, end, exclusive = presets[query.window]
    return query.window, None, start, end, exclusive


def rework_rate_workload(
    db: Database, query: ReworkRateParams, *, now: datetime | None = None
) -> ReworkRateWorkload:
    """Compute rework rates across all project reviews or within a bounded UTC review window."""
    reference = (now or utcnow()).astimezone(UTC)
    window, days, start, end, exclusive_end = _review_bounds(query, reference)
    base = annotator_workload(db, query.project_id, (start, end, exclusive_end))
    return ReworkRateWorkload(
        project_id=base.project_id,
        annotators=base.annotators,
        window=window,
        days=days,
        since=start,
        until=end,
    )


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
    value = (
        _team_read(db, name, arguments)
        if name in TEAM_READS
        else _project_read(db, name, arguments, caller)
    )
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
    if name == "assignees":
        query = AssigneesParams.model_validate(arguments.root)
        return assignees(db, query.project_id, caller, query.stage)
    if name == "next_task":
        query = NextTaskParams.model_validate(arguments.root)
        return next_task(db, query.project_id, caller.actor, query.package_id)
    if name == "package_status":
        query = PackageReadParams.model_validate(arguments.root)
        return project_progress(db, query.project_id, query.package_id)
    if name == "rework_rate":
        return rework_rate_workload(db, ReworkRateParams.model_validate(arguments.root))
    project = ProjectReadParams.model_validate(arguments.root)
    readers: dict[str, Callable[[Database, str], BoundaryModel]] = {
        "project_progress": project_progress,
        "prelabel_confidence": confidence_distribution,
        "production_prelabel_accuracy": production_prelabel_accuracy,
        "annotation_consistency": production_agreement,
    }
    return readers.get(name, annotator_workload)(db, project.project_id)


def _team_read(db: Database, name: str, arguments: JsonDocument) -> BoundaryModel:
    if name == "lease_status":
        return lease_status(db, LeaseStatusParams.model_validate(arguments.root))
    if name == "package_acceptance":
        return package_acceptance_status(db, PackageAcceptanceParams.model_validate(arguments.root))
    return skill_workload(db, ProjectReadParams.model_validate(arguments.root).project_id)
