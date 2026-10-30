# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Write what a dispatch plan will do into the plan before anyone signs it."""

from sqlalchemy.orm import Session

from datakeel.actions.production_parameters import AssignTasksParams
from datakeel.core.models import BoundaryModel
from datakeel.storage.production_dispatch_rules import require_dispatch_limit
from datakeel.storage.production_rows import ProductionTaskRow
from datakeel.storage.production_tasks import require_project


def prepare_dispatch_params(session: Session, params: BoundaryModel) -> BoundaryModel:
    """Refuse a dispatch limit above the project's before anyone signs the plan.

    Unknown tasks are left for execution to reject with its usual error.
    """
    if not isinstance(params, AssignTasksParams):
        return params
    tasks = [
        row
        for identifier in sorted(set(params.task_ids))
        if (row := session.get(ProductionTaskRow, identifier)) is not None
    ]
    if tasks:
        require_dispatch_limit(
            require_project(session, tasks[0].project_id), params.max_active_tasks
        )
    return params
