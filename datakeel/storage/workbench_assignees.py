# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""List the registered people a manager can assign a project's work to by name."""

from sqlalchemy import select

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError
from datakeel.core.identity_models import User
from datakeel.core.models import AssetRef
from datakeel.core.production_models import AssignmentStage
from datakeel.core.workbench_models import AssignablePerson, WorkbenchAssignees
from datakeel.storage.data_asset_access import require_access
from datakeel.storage.database import Database
from datakeel.storage.identity_authorization import effective_scopes
from datakeel.storage.identity_rows import UserRow
from datakeel.storage.production_dispatch_rules import active_loads
from datakeel.storage.production_tasks import require_project

_STAGE_SCOPES: dict[str, str] = {
    "annotation": "production:annotate",
    "review": "production:review",
}


def assignees(
    db: Database, project_id: str, caller: AccessContext, stage: AssignmentStage
) -> WorkbenchAssignees:
    """Return active registered people holding the stage scope here, with their open load.

    Only someone who may assign here sees the list. Before anyone registers there is nobody
    to list: zero-user work is done as `local`.
    """
    require_access(db, (AssetRef(asset_type="project", asset_id=project_id),), caller)
    required = _STAGE_SCOPES[stage]
    with db.session() as session:
        require_project(session, project_id)
        caller_scopes = effective_scopes(session, caller.actor, project_id).scopes
        if not {"production:assign", "*"} & set(caller_scopes):
            message = "Listing assignable people requires the production:assign scope"
            raise AuthorizationError(message)
        users = [
            User.model_validate(row.payload)
            for row in session.scalars(select(UserRow).order_by(UserRow.id))
        ]
        eligible = [
            user
            for user in users
            if user.status == "active"
            and {required, "*"} & set(effective_scopes(session, user.id, project_id).scopes)
        ]
        loads = active_loads(session, project_id, stage, [user.id for user in eligible])
    return WorkbenchAssignees(
        project_id=project_id,
        stage=stage,
        people=tuple(
            AssignablePerson(
                actor=user.id, display_name=user.display_name, current=loads.get(user.id, 0)
            )
            for user in eligible
        ),
    )
