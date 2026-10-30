# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Load what AI pre-review needs about a whole project in a few bounded queries.

Each task contributes its submitted head (when it is waiting for or past review) and its
latest model draft. Tasks without a submitted head stand in with their draft, so project-wide
statistics such as box sizes are complete from the first submission of a prelabelled project.
Image hashes come from the process-wide memo in ``sample_hash``; nothing is decoded twice.
"""

from functools import cache
from typing import TYPE_CHECKING, NamedTuple

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from datakeel.annotation_qa import Draft
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.production_catalog_models import ProductionTemplate
from datakeel.core.production_models import AnnotationRevision, Project
from datakeel.operators.evidence.contracts import read_near_duplicate
from datakeel.storage.database import VersionRow
from datakeel.storage.production_catalog import require_label_set, require_template
from datakeel.storage.production_prelabel_refs import object_confidences
from datakeel.storage.production_rows import ProductionRevisionRow, ProductionTaskRow

if TYPE_CHECKING:
    from pydantic import JsonValue

CONTEXT_LIMIT = 500
CONTEXT_STATES = ("submitted", "in_review", "approved", "finalized")


class TaskFacts(NamedTuple):
    """One task's sample, state, submitted head and latest model draft."""

    task_id: str
    sample_id: str
    state: str
    head: AnnotationRevision | None
    draft: Draft | None


class ProjectFacts(NamedTuple):
    """Tasks keyed by id plus label names, file names, object keys and the project template."""

    tasks: dict[str, TaskFacts]
    names: dict[str, str]
    files: dict[str, str]
    keys: dict[str, str]
    template: ProductionTemplate | None


@cache
def hamming_threshold() -> int:
    """Read the near-duplicate contract once per process."""
    return read_near_duplicate().hamming_threshold


def _draft(revision: AnnotationRevision) -> Draft:
    confidences = object_confidences(revision)
    overall = revision.confidence
    if overall is None:
        overall = min(confidences, default=0.0)
    return Draft(revision.annotation, confidences, overall)


def _manifest(session: Session, project: Project) -> tuple[dict[str, str], dict[str, str]]:
    version = session.get(VersionRow, project.version_id)
    files: dict[str, str] = {}
    keys: dict[str, str] = {}
    if version is None or version.dataset_id != project.dataset_id:
        return files, keys
    for item in version.manifest:
        entry: dict[str, JsonValue] = item
        identifier, name, metadata = entry.get("id"), entry.get("filename"), entry.get("metadata")
        if not isinstance(identifier, str):
            continue
        files[identifier] = name if isinstance(name, str) else "another image"
        key = metadata.get("object_key") if isinstance(metadata, dict) else None
        if isinstance(key, str):
            keys[identifier] = key
    return files, keys


def _revisions(
    session: Session, rows: list[ProductionTaskRow]
) -> tuple[dict[str, AnnotationRevision], dict[str, AnnotationRevision]]:
    heads = {
        row.id: identifier
        for row in rows
        if row.state in CONTEXT_STATES
        and (identifier := row.approved_revision_id or row.latest_revision_id)
    }
    found: dict[str, AnnotationRevision] = {}
    drafts: dict[str, AnnotationRevision] = {}
    for row in session.scalars(
        select(ProductionRevisionRow).where(
            ProductionRevisionRow.task_id.in_([row.id for row in rows]),
            or_(
                ProductionRevisionRow.source == "model",
                ProductionRevisionRow.id.in_(list(heads.values())),
            ),
        )
    ):
        revision = AnnotationRevision.model_validate(row.payload)
        if heads.get(row.task_id) == row.id:
            found[row.task_id] = revision
        current = drafts.get(row.task_id)
        if revision.source == "model" and (
            current is None or (revision.created_at, revision.id) > (current.created_at, current.id)
        ):
            drafts[row.task_id] = revision
    return found, drafts


def load_facts(session: Session, project: Project, task: ProductionTaskRow) -> ProjectFacts:
    """Collect up to ``CONTEXT_LIMIT`` recent tasks of the project, always including ``task``."""
    rows = list(
        session.scalars(
            select(ProductionTaskRow)
            .where(ProductionTaskRow.project_id == project.id, ProductionTaskRow.id != task.id)
            .order_by(ProductionTaskRow.id.desc())
            .limit(CONTEXT_LIMIT)
        )
    )
    rows.append(task)
    heads, drafts = _revisions(session, rows)
    tasks = {
        row.id: TaskFacts(
            row.id,
            row.sample_id,
            row.state,
            heads.get(row.id),
            _draft(drafts[row.id]) if row.id in drafts else None,
        )
        for row in rows
    }
    labels = require_label_set(session, project.label_set_id, project.label_set_version)
    files, keys = _manifest(session, project)
    return ProjectFacts(
        tasks,
        {label.id: label.name for label in labels.labels},
        files,
        keys,
        _template(session, project),
    )


def _template(session: Session, project: Project) -> ProductionTemplate | None:
    if project.template_id is None:
        return None
    try:
        return require_template(session, project.template_id)
    except (NotFoundError, ValidationError):
        return None
