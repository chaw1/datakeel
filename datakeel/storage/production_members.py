# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Record production participants independently of project and assignment mutations."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datakeel.core.production_models import Project
from datakeel.storage.production_rows import ProductionMemberRow, ProductionProjectRow
from datakeel.storage.production_tasks import require_mutable_project

REVIEW_SUGGESTION_MEMBERS = 2


def record_project_member(session: Session, project_id: str, actor: str) -> bool:
    """Return the review suggestion exactly once when a second participant first appears.

    Membership rows are insert-only, so a known member returns before locking the project
    row; only a person's first appearance serializes on the project, keeping saves and
    claims by existing members free of a project-wide lock.
    """
    if session.get(ProductionMemberRow, (project_id, actor)) is not None:
        return False
    row = session.get(
        ProductionProjectRow, project_id, with_for_update=True, populate_existing=True
    )
    if row is None:
        require_mutable_project(session, project_id)
        return False
    if session.get(ProductionMemberRow, (project_id, actor), populate_existing=True) is not None:
        return False
    session.add(ProductionMemberRow(project_id=project_id, actor=actor))
    session.flush()
    count = (
        session.scalar(
            select(func.count())
            .select_from(ProductionMemberRow)
            .where(ProductionMemberRow.project_id == project_id)
        )
        or 0
    )
    project = Project.model_validate(row.payload)
    suggest = count >= REVIEW_SUGGESTION_MEMBERS and not project.review_prompt_shown
    if suggest:
        row.payload = project.model_copy(update={"review_prompt_shown": True}).model_dump(
            mode="json"
        )
    return suggest
