# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Assemble workbench views from existing production facts and native source grants."""

import mimetypes
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import select

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.models import AssetRef
from datakeel.core.production_models import ProductionTask, Project
from datakeel.core.workbench_models import (
    WorkbenchIndex,
    WorkbenchProject,
    WorkbenchProjectQuery,
    WorkbenchSample,
    WorkbenchTask,
    WorkbenchTaskRisk,
)
from datakeel.storage.data_asset_access import require_access, skip_protected
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import resolve_download
from datakeel.storage.identity_authorization import effective_scopes
from datakeel.storage.image_geometry import read_geometry
from datakeel.storage.production_catalog import require_label_set
from datakeel.storage.production_queries import (
    get_project,
    get_task,
    list_assignments,
    list_packages,
    list_projects,
    list_reviews,
    list_revisions,
    project_progress,
)
from datakeel.storage.production_rows import ProductionTaskRow
from datakeel.storage.production_separation import exclude_own_work
from datakeel.storage.production_statistics import (
    annotator_workload,
    confidence_distribution,
    production_agreement,
    production_prelabel_accuracy,
)
from datakeel.storage.production_tasks import task_view
from datakeel.storage.production_template_versions import (
    latest_label_set_version,
    latest_template,
    locked_template,
)
from datakeel.storage.workbench_risk import review_order, task_risks
from datakeel.storage.workbench_samples import (
    matches_search,
    name_tasks,
    named_tasks,
    sample_names,
)


def workbench_index(db: Database, caller: AccessContext) -> WorkbenchIndex:
    """Filter project discovery with the same source-grant policy used by production tools."""
    projects = list_projects(db)
    hidden = skip_protected(
        db,
        [
            (project.id, (AssetRef(asset_type="project", asset_id=project.id),))
            for project in projects
        ],
        caller,
    )
    blocked: set[str] = set(hidden.ids) if hidden else set()
    with db.session() as session:
        scopes = effective_scopes(session, caller.actor)
    return WorkbenchIndex(
        actor=caller.actor,
        zero_users=scopes.zero_users,
        effective_scopes=scopes,
        projects=tuple(project for project in projects if project.id not in blocked),
    )


def _tasks(
    db: Database,
    project: Project,
    caller: AccessContext,
    query: WorkbenchProjectQuery,
) -> tuple[tuple[ProductionTask, ...], tuple[WorkbenchTaskRisk, ...], dict[str, tuple[str, str]]]:
    with db.session() as session:
        statement = select(ProductionTaskRow).where(ProductionTaskRow.project_id == project.id)
        if query.package_id is not None:
            statement = statement.where(ProductionTaskRow.package_id == query.package_id)
        if query.view == "review":
            statement = statement.where(ProductionTaskRow.state.in_(("submitted", "in_review")))
            if project.workflow_tier == "team":
                statement = exclude_own_work(statement, caller.actor)
        elif query.view == "mine":
            statement = statement.where(ProductionTaskRow.annotator_id == caller.actor)
        names = sample_names(session, project)
        tasks = tuple(
            task
            for task in (
                task_view(row) for row in session.scalars(statement.order_by(ProductionTaskRow.id))
            )
            if matches_search(task, names, query.search)
        )
    risks = task_risks(db, tasks)
    return (review_order(tasks, risks) if query.view == "review" else tasks), risks, names


def _page(
    tasks: tuple[ProductionTask, ...], limit: int, cursor: str | None
) -> tuple[tuple[ProductionTask, ...], str | None]:
    start = 0
    if cursor:
        start = next((i + 1 for i, task in enumerate(tasks) if task.id == cursor), len(tasks))
    page = tasks[start : start + limit]
    return page, page[-1].id if page and start + limit < len(tasks) else None


def workbench_project(
    db: Database,
    project_id: str,
    caller: AccessContext,
    query: WorkbenchProjectQuery | None = None,
) -> WorkbenchProject:
    """Project existing P29 counters and measurements without maintaining a second state."""
    require_access(db, (AssetRef(asset_type="project", asset_id=project_id),), caller)
    query = query or WorkbenchProjectQuery()
    project = get_project(db, project_id)
    packages = list_packages(db, project_id)
    if query.package_id is not None and not any(p.id == query.package_id for p in packages):
        message = "Package was not found within the selected project"
        raise NotFoundError(message)
    with db.session() as session:
        labels = require_label_set(session, project.label_set_id, project.label_set_version)
        template = locked_template(session, project)
        latest = latest_template(session, project.template_id) if project.template_id else None
        latest_labels = latest_label_set_version(session, project.label_set_id)
        scopes = effective_scopes(session, caller.actor, project_id)
    tasks, risks, names = _tasks(db, project, caller, query)
    page, next_cursor = _page(tasks, query.limit, query.cursor)
    identities = {task.id for task in page}
    progress = project_progress(db, project_id)
    with db.session() as session:
        rework = named_tasks(session, project, progress.rework_task_ids)
    return WorkbenchProject(
        project=project,
        packages=packages,
        label_set=labels,
        template=template,
        latest_template=latest,
        latest_label_set_version=latest_labels,
        effective_scopes=scopes,
        progress=progress,
        workload=annotator_workload(db, project_id),
        confidence=confidence_distribution(db, project_id),
        agreement=production_agreement(db, project_id),
        prelabel_accuracy=production_prelabel_accuracy(db, project_id),
        tasks=page,
        task_risks=tuple(risk for risk in risks if risk.task_id in identities),
        next_cursor=next_cursor,
        task_samples=name_tasks(page, names)
        + tuple(item for item in rework if item.task_id not in identities),
    )


def task_source(db: Database, task_id: str, caller: AccessContext) -> tuple[Path, str]:
    """Authorize task and exact version-pinned source content before materializing bytes."""
    require_access(db, (AssetRef(asset_type="production_task", asset_id=task_id),), caller)
    task = get_task(db, task_id)
    project = get_project(db, task.project_id)
    source = resolve_download(
        db, project.dataset_id, task.sample_id, project.version_id, access=caller
    )
    return source.path, source.filename


def _sample(
    path: Path, name: str, task: ProductionTask, *, relative: str, text_sample: bool = False
) -> WorkbenchSample:
    media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if text_sample and not media_type.startswith("image/"):
        media_type = "text/plain"
    url = f"/api/production/tasks/{quote(task.id, safe='')}/content"
    width, height, text = None, None, None
    thumbnail = None
    if media_type.startswith("image/"):
        geometry = read_geometry(path)
        if geometry is not None:
            width, height = geometry.width, geometry.height
        thumbnail = url + "?thumbnail=true"
    elif media_type.startswith("text/"):
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeError as error:
            message = "Workbench text samples must use UTF-8"
            raise ValidationError(message) from error
    return WorkbenchSample(
        id=task.sample_id,
        name=name,
        path=relative,
        media_type=media_type,
        text=text,
        image_width=width,
        image_height=height,
        content_url=url,
        thumbnail_url=thumbnail,
    )


def workbench_task(db: Database, task_id: str, caller: AccessContext) -> WorkbenchTask:
    """Load a sample and immutable history after native project and file authorization."""
    path, name = task_source(db, task_id, caller)
    task = get_task(db, task_id)
    project = get_project(db, task.project_id)
    with db.session() as session:
        template = locked_template(session, project)
        _, relative = sample_names(session, project).get(task.sample_id, (name, name))
    configured = template.component_config.get("components") if template else None
    text_sample = template is not None and (
        template.annotation_type == "text_span"
        or (isinstance(configured, list) and "text_span" in configured)
    )
    return WorkbenchTask(
        task=task,
        sample=_sample(
            path,
            name,
            task,
            relative=relative,
            text_sample=text_sample,
        ),
        revisions=tuple(
            sorted(list_revisions(db, task_id), key=lambda item: (item.created_at, item.id))
        ),
        reviews=tuple(
            sorted(list_reviews(db, task_id), key=lambda item: (item.created_at, item.id))
        ),
        assignments=list_assignments(db, task_id),
    )
