# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep access-application decisions with an independent person on the Web UI or CLI."""

from collections.abc import Mapping

from pydantic import JsonValue
from sqlalchemy.orm import Session

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError
from datakeel.storage.data_asset_grants import application_in_session

DECISION_ACTION = "decide_asset_application"
_TOOL_ENTRIES = frozenset({"agent", "mcp"})


def refuse_tool_decision(action_type: str, access: AccessContext | None) -> None:
    """Reject preparing, approving or executing an application decision from a tool caller."""
    if action_type == DECISION_ACTION and access is not None and access.entry in _TOOL_ENTRIES:
        msg = (
            "Access applications can only be approved or rejected by a person in the Web UI "
            "or CLI; MCP and Agent tools cannot decide them"
        )
        raise AuthorizationError(msg)


def same_identity(left: str, right: str) -> bool:
    """Compare self-reported operator names the way a reviewer would read them."""
    return left.strip().casefold() == right.strip().casefold()


def require_independent_reviewer(
    session: Session, action_type: str, params: Mapping[str, JsonValue], reviewer: str
) -> None:
    """Reject an application decision reviewed under the applicant's own identity."""
    if action_type != DECISION_ACTION:
        return
    application_id = params.get("application_id")
    if not isinstance(application_id, str):
        return
    application = application_in_session(session, application_id)
    if same_identity(application.applicant, reviewer):
        msg = (
            f"Applicant {application.applicant} cannot review their own access application; "
            "another person must approve or reject it"
        )
        raise AuthorizationError(msg)
