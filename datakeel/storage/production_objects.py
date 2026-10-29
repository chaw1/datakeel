# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Project production objects from authoritative facts using portable asset identities."""

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.identity_models import Role, Skill, Team, User
from datakeel.core.models import AssetRef, BoundaryModel
from datakeel.core.production_catalog_models import (
    LabelSet,
    PrelabelRun,
    ProductionModel,
    ProductionTemplate,
)
from datakeel.core.production_models import (
    AnnotationRevision,
    Assignment,
    Project,
    Review,
    TaskPackage,
)
from datakeel.core.production_reads import (
    LabelSetDifference,
    LabelSetDiffParams,
    ProductionObjectQuery,
)
from datakeel.ontology.models import FrozenObject
from datakeel.storage.database import Database
from datakeel.storage.identity_rows import RoleRow, SkillRow, TeamRow, UserRow
from datakeel.storage.identity_store import role_templates
from datakeel.storage.object_projection import content_digest
from datakeel.storage.production_catalog import require_label_set
from datakeel.storage.production_catalog_impact import migration_impact
from datakeel.storage.production_catalog_rows import (
    ProductionLabelSetRow,
    ProductionModelRow,
    ProductionPrelabelRunRow,
    ProductionTemplateRow,
)
from datakeel.storage.production_rows import (
    ProductionAssignmentRow,
    ProductionPackageRow,
    ProductionProjectRow,
    ProductionReviewRow,
    ProductionRevisionRow,
    ProductionTaskRow,
)
from datakeel.storage.production_tasks import task_view

_READERS: dict[str, Callable[[Session], list[BoundaryModel]]] = {
    "user": lambda s: [User.model_validate(r.payload) for r in s.scalars(select(UserRow))],
    "team": lambda s: [Team.model_validate(r.payload) for r in s.scalars(select(TeamRow))],
    "skill": lambda s: [Skill.model_validate(r.payload) for r in s.scalars(select(SkillRow))],
    "role": lambda s: [Role.model_validate(r.payload) for r in s.scalars(select(RoleRow))],
    "project": lambda s: [
        Project.model_validate(r.payload) for r in s.scalars(select(ProductionProjectRow))
    ],
    "task_package": lambda s: [
        TaskPackage.model_validate(r.payload) for r in s.scalars(select(ProductionPackageRow))
    ],
    "production_task": lambda s: [task_view(r) for r in s.scalars(select(ProductionTaskRow))],
    "assignment": lambda s: [
        Assignment.model_validate(r.payload) for r in s.scalars(select(ProductionAssignmentRow))
    ],
    "annotation_revision": lambda s: [
        AnnotationRevision.model_validate(r.payload)
        for r in s.scalars(select(ProductionRevisionRow))
    ],
    "review": lambda s: [
        Review.model_validate(r.payload) for r in s.scalars(select(ProductionReviewRow))
    ],
    "label_set": lambda s: [
        LabelSet.model_validate(r.payload) for r in s.scalars(select(ProductionLabelSetRow))
    ],
    "template": lambda s: [
        ProductionTemplate.model_validate(r.payload)
        for r in s.scalars(select(ProductionTemplateRow))
    ],
    "model": lambda s: [
        ProductionModel.model_validate(r.payload) for r in s.scalars(select(ProductionModelRow))
    ],
    "prelabel_run": lambda s: [
        PrelabelRun.model_validate(r.payload) for r in s.scalars(select(ProductionPrelabelRunRow))
    ],
}


def _matches(session: Session, value: BoundaryModel, query: ProductionObjectQuery) -> bool:
    payload = value.model_dump(mode="json")
    if query.object_id is not None and payload.get("id") != query.object_id:
        return False
    if query.version is not None and payload.get("version") != query.version:
        return False
    if query.task_id is not None and payload.get("task_id", payload.get("id")) != query.task_id:
        return False
    if query.project_id is None:
        return True
    project_id = payload.get("id") if query.kind == "project" else payload.get("project_id")
    task_id = payload.get("task_id")
    if isinstance(task_id, str):
        task = session.get(ProductionTaskRow, task_id)
        project_id = task.project_id if task else None
    return project_id == query.project_id


def production_objects(db: Database, query: ProductionObjectQuery) -> tuple[FrozenObject, ...]:
    """Return validated object projections; role templates appear before their first override."""
    with db.session() as session:
        values = _READERS[query.kind](session)
        if query.kind == "role":
            overrides = {getattr(value, "id", "") for value in values}
            values.extend(role for role in role_templates() if role.id not in overrides)
        selected = sorted(
            (value for value in values if _matches(session, value, query)),
            key=lambda value: (str(getattr(value, "id", "")), str(getattr(value, "version", ""))),
        )[: query.limit]
        return tuple(_freeze(query.kind, value) for value in selected)


def _freeze(kind: str, value: BoundaryModel) -> FrozenObject:
    properties = value.model_dump(mode="json")
    identifier = str(properties["id"])
    version = str(properties["version"]) if kind == "label_set" else None
    return FrozenObject(
        asset_ref=AssetRef(asset_type=kind, asset_id=identifier, version=version),
        revision=content_digest(properties),
        properties=properties,
    )


def label_set_difference(db: Database, query: LabelSetDiffParams) -> LabelSetDifference:
    """Compute current annotation impact rather than estimating from aggregate label counts."""
    with db.session() as session:
        before = require_label_set(session, query.label_set_id, query.before_version)
        after = require_label_set(session, query.label_set_id, query.after_version)
        old = {label.id: label.name for label in before.labels}
        new = {label.id: label.name for label in after.labels}
        annotations, revisions = migration_impact(session, before, after)
        return LabelSetDifference(
            label_set_id=query.label_set_id,
            before_version=query.before_version,
            after_version=query.after_version,
            added=tuple(sorted(new.keys() - old.keys())),
            removed=tuple(sorted(old.keys() - new.keys())),
            renamed=tuple(sorted(key for key in old.keys() & new.keys() if old[key] != new[key])),
            affected_annotations=annotations,
            affected_revisions=revisions,
            migration=after.migration,
        )
