# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only team projections for leases, skill workload and package acceptance."""

from sqlalchemy import func, select

from datakeel.core.errors import NotFoundError
from datakeel.core.identity_models import Skill, User
from datakeel.core.models import utcnow
from datakeel.core.production_models import Assignment
from datakeel.core.production_reads import LeaseStatusParams, PackageAcceptanceParams
from datakeel.core.production_team_models import (
    LeaseRelease,
    LeaseStatus,
    LeaseView,
    PackageAcceptance,
    ProductionSkillWorkload,
    SkillWorkload,
)
from datakeel.storage.database import Database
from datakeel.storage.identity_rows import SkillRow, UserRow
from datakeel.storage.production_acceptance import package_acceptance
from datakeel.storage.production_dispatch_rules import active_loads
from datakeel.storage.production_leases import running_lease
from datakeel.storage.production_rows import (
    ProductionAssignmentRow,
    ProductionPackageRow,
    ProductionTaskRow,
)
from datakeel.storage.production_tasks import require_project
from datakeel.storage.production_team_rows import ProductionLeaseReleaseRow

_COMPLETED = ("submitted", "in_review", "approved", "finalized")


def lease_status(db: Database, params: LeaseStatusParams) -> LeaseStatus:
    """List running leases by deadline as live, expiring or overdue, plus recent reclaims."""
    now = utcnow()
    with db.session() as session:
        require_project(session, params.project_id)
        rows = session.execute(
            select(ProductionAssignmentRow.payload, ProductionAssignmentRow.lease_expires_at)
            .join(ProductionTaskRow, ProductionTaskRow.id == ProductionAssignmentRow.task_id)
            .where(ProductionTaskRow.project_id == params.project_id, running_lease())
            .order_by(ProductionAssignmentRow.lease_expires_at, ProductionAssignmentRow.id)
            .limit(params.limit)
        ).all()
        releases = session.scalars(
            select(ProductionLeaseReleaseRow.payload)
            .where(ProductionLeaseReleaseRow.project_id == params.project_id)
            .order_by(
                ProductionLeaseReleaseRow.released_at.desc(),
                ProductionLeaseReleaseRow.assignment_id,
            )
            .limit(params.limit)
        )
        reclaimed = tuple(LeaseRelease.model_validate(payload) for payload in releases)
    views = [
        LeaseView(
            assignment=Assignment.model_validate(payload),
            seconds_remaining=(deadline or 0) - now.timestamp(),
        )
        for payload, deadline in rows
    ]
    live = tuple(view for view in views if view.seconds_remaining > 0)
    return LeaseStatus(
        project_id=params.project_id,
        observed_at=now,
        expiring_within_seconds=params.expiring_within_seconds,
        active=live,
        expiring=tuple(
            view for view in live if view.seconds_remaining <= params.expiring_within_seconds
        ),
        overdue=tuple(view for view in views if view.seconds_remaining <= 0),
        reclaimed=reclaimed,
    )


def skill_workload(db: Database, project_id: str) -> ProductionSkillWorkload:
    """Sum each active skill holder's effective and completed annotation work in the project."""
    with db.session() as session:
        require_project(session, project_id)
        users = [User.model_validate(row.payload) for row in session.scalars(select(UserRow))]
        loads = active_loads(session, project_id, "annotation")
        completed = {
            actor: int(count)
            for actor, count in session.execute(
                select(ProductionTaskRow.annotator_id, func.count())
                .where(
                    ProductionTaskRow.project_id == project_id,
                    ProductionTaskRow.state.in_(_COMPLETED),
                    ProductionTaskRow.annotator_id.is_not(None),
                )
                .group_by(ProductionTaskRow.annotator_id)
            ).all()
            if actor is not None
        }
        skills = [
            Skill.model_validate(row.payload)
            for row in session.scalars(select(SkillRow).order_by(SkillRow.id))
        ]
    result: list[SkillWorkload] = []
    for skill in skills:
        if skill.status != "active":
            continue
        holders = tuple(
            sorted(
                user.id for user in users if user.status == "active" and skill.id in user.skill_ids
            )
        )
        result.append(
            SkillWorkload(
                skill_id=skill.id,
                name=skill.name,
                annotation_type=skill.annotation_type,
                domain=skill.domain,
                level=skill.level,
                users=holders,
                active_assignments=sum(loads.get(user, 0) for user in holders),
                completed_tasks=sum(completed.get(user, 0) for user in holders),
            )
        )
    return ProductionSkillWorkload(project_id=project_id, skills=tuple(result))


def package_acceptance_status(db: Database, params: PackageAcceptanceParams) -> PackageAcceptance:
    """Read one package of the selected project with its acceptance state and sample preview."""
    with db.session() as session:
        require_project(session, params.project_id)
        package = session.get(ProductionPackageRow, params.package_id)
        if package is None or package.project_id != params.project_id:
            message = "Package was not found within the selected project"
            raise NotFoundError(message)
        return package_acceptance(session, params.package_id, params)
