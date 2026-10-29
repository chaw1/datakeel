# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep new production decisions and execution exclusively in human entry points."""

from datakeel.actions.models import ActionPlan
from datakeel.actions.production_language import PRODUCTION_LANGUAGE
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError


def require_production_human(plan: ActionPlan, access: AccessContext | None) -> None:
    """Allow model transports to prepare plans and reject their approval or execution."""
    if (
        plan.action_type in PRODUCTION_LANGUAGE
        and access is not None
        and access.entry in {"agent", "mcp"}
    ):
        message = "Production plans must be approved and executed by a person in the Web UI or CLI"
        raise AuthorizationError(message)
