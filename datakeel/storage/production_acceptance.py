# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Team package acceptance by P26 sampling; rejection returns the whole package for rework."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan
from datakeel.actions.production_catalog_parameters import AcceptPackageParams
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.models import new_id, utcnow
from datakeel.core.production_models import Project
from datakeel.core.production_team_models import (
    PackageAcceptance,
    PackageAcceptanceState,
    PackageInspection,
    PackageSampling,
    PackageSamplingParams,
)
from datakeel.storage.annotation_sampling import sampling_selection
from datakeel.storage.object_projection import content_digest
from datakeel.storage.production_reviews import return_for_rework
from datakeel.storage.production_rows import ProductionPackageRow, ProductionTaskRow
from datakeel.storage.production_tasks import require_mutable_project, require_project
from datakeel.storage.production_team_rows import ProductionPackageInspectionRow


def package_tasks(
    session: Session, package_id: str, *, lock: bool = False
) -> tuple[Project, list[ProductionTaskRow]]:
    """Read a package's project and its tasks in identity order, optionally locked."""
    package = session.get(ProductionPackageRow, package_id)
    if package is None:
        message = "Task package was not found"
        raise NotFoundError(message)
    statement = (
        select(ProductionTaskRow)
        .where(ProductionTaskRow.package_id == package_id)
        .order_by(ProductionTaskRow.id)
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return require_project(session, package.project_id), list(session.scalars(statement))


def approved_digest(tasks: Sequence[ProductionTaskRow]) -> str:
    """Bind a decision to the exact approved revision of every task in the package."""
    return content_digest([[task.id, task.approved_revision_id] for task in tasks])


def package_sampling(
    tasks: Sequence[ProductionTaskRow], params: PackageSamplingParams
) -> PackageSampling:
    """Apply the P26 selection to the package's sample identities."""
    request = params.sampling_request("package")
    selection = sampling_selection(tuple(task.sample_id for task in tasks), request)
    sampling = PackageSampling.model_validate(
        {
            **selection,
            "task_ids": [],
            "method": params.method,
            "aql": params.aql if params.method == "aql" else None,
            "ratio": params.ratio,
            "seed": params.seed,
        }
    )
    chosen = set(sampling.sample_ids)
    return sampling.model_copy(
        update={"task_ids": tuple(task.id for task in tasks if task.sample_id in chosen)}
    )


def require_inspectable(
    session: Session, params: AcceptPackageParams, *, lock: bool = False
) -> tuple[Project, list[ProductionTaskRow], PackageSampling]:
    """Require a fully approved team package and checks covering exactly the sampled units."""
    project, tasks = package_tasks(session, params.package_id, lock=lock)
    if project.workflow_tier != "team":
        message = "Package acceptance applies only to team-tier projects"
        raise ValidationError(message)
    if project.finalized_version_id is not None:
        message = "Finalized projects cannot be changed; create a new project"
        raise ConflictError(message)
    if not tasks or any(task.state != "approved" for task in tasks):
        message = "Every package task must be approved before acceptance"
        raise ConflictError(message)
    sampling = package_sampling(tasks, params)
    if {check.sample_id for check in params.checks} != set(sampling.sample_ids):
        message = "Inspection must review every sampled unit exactly once"
        raise ValidationError(message)
    return project, tasks, sampling


def accept_package(
    session: Session, plan: ActionPlan, params: AcceptPackageParams
) -> PackageInspection:
    """Archive the decision; a rejection returns every package task for one more round."""
    project, tasks, sampling = require_inspectable(session, params, lock=True)
    require_mutable_project(session, project.id)
    defective = sum(check.defective for check in params.checks)
    accepted = defective <= sampling.acceptance_number
    digest = approved_digest(tasks)
    returned: list[str] = []
    if not accepted:
        for task in tasks:
            return_for_rework(session, project, task)
            returned.append(task.id)
    inspection = PackageInspection(
        id=new_id(),
        action_plan_id=plan.id,
        project_id=project.id,
        package_id=params.package_id,
        sampling=sampling,
        checks=tuple(sorted(params.checks, key=lambda item: item.sample_id)),
        defective_count=defective,
        accepted=accepted,
        revision_digest=digest,
        returned_task_ids=tuple(returned),
        actor=plan.actor,
        created_at=utcnow(),
    )
    session.add(
        ProductionPackageInspectionRow(
            id=inspection.id,
            package_id=inspection.package_id,
            project_id=project.id,
            created_at=inspection.created_at.timestamp(),
            payload=inspection.model_dump(mode="json"),
        )
    )
    session.flush()
    return inspection


def latest_inspection(session: Session, package_id: str) -> tuple[PackageInspection | None, int]:
    """Return the newest decision for a package and how many decisions exist."""
    rows = list(
        session.scalars(
            select(ProductionPackageInspectionRow)
            .where(ProductionPackageInspectionRow.package_id == package_id)
            .order_by(ProductionPackageInspectionRow.created_at, ProductionPackageInspectionRow.id)
        )
    )
    return (PackageInspection.model_validate(rows[-1].payload) if rows else None), len(rows)


def acceptance_state(
    tasks: Sequence[ProductionTaskRow], latest: PackageInspection | None
) -> PackageAcceptanceState:
    """Accepted only while the accepted decision still covers the current approved revisions."""
    complete = bool(tasks) and all(task.state == "approved" for task in tasks)
    if latest is not None and latest.accepted and latest.revision_digest == approved_digest(tasks):
        return "accepted"
    if complete:
        return "ready"
    if latest is not None and not latest.accepted:
        return "rejected"
    return "in_progress"


def package_acceptance(
    session: Session, package_id: str, params: PackageSamplingParams
) -> PackageAcceptance:
    """Report state, the last decision and, when ready, the reproducible sample to inspect."""
    project, tasks = package_tasks(session, package_id)
    latest, count = latest_inspection(session, package_id)
    state = acceptance_state(tasks, latest)
    return PackageAcceptance(
        project_id=project.id,
        package_id=package_id,
        status=state,
        total=len(tasks),
        approved=sum(task.state in {"approved", "finalized"} for task in tasks),
        sampling=package_sampling(tasks, params) if state == "ready" else None,
        latest=latest,
        inspections=count,
    )


def require_packages_accepted(session: Session, project: Project) -> None:
    """Block team finalization until every package's acceptance covers its approved revisions."""
    if project.workflow_tier != "team":
        return
    pending: list[str] = []
    for package_id in session.scalars(
        select(ProductionPackageRow.id)
        .where(ProductionPackageRow.project_id == project.id)
        .order_by(ProductionPackageRow.id)
    ):
        _, tasks = package_tasks(session, package_id)
        latest, _ = latest_inspection(session, package_id)
        if acceptance_state(tasks, latest) != "accepted":
            pending.append(package_id)
    if pending:
        message = "Team projects finalize only after every package is accepted: " + ", ".join(
            pending
        )
        raise ConflictError(message)
