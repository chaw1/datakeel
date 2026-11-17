# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent authority data: omission denies, presentation never grants access."""

from pydantic import TypeAdapter

from datakeel.actions.declarations import AuthorizationPolicy, resource
from datakeel.actions.file_declarations import active_declarations
from datakeel.actions.models import ActionPlan, ExecuteRequest
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError

AUTHORIZATION = resource("authorization.json", TypeAdapter(dict[str, AuthorizationPolicy]))


def authorization_for(name: str) -> AuthorizationPolicy:
    """Resolve one independent policy, requiring even generated owners to retain authority."""
    policy = AUTHORIZATION.get(name)
    declaration = active_declarations().get(name)
    if declaration is not None:
        return declaration.authorization
    if policy is None:
        msg = "Action has no explicit authorization policy"
        raise AuthorizationError(msg)
    return policy


def allows_automatic(name: str, *, reversible: bool) -> bool:
    """Allow only explicit reversible, nonproduction execution eligibility."""
    policy = authorization_for(name)
    return reversible and policy.automatic and not policy.human_only


def require_production_human(plan: ActionPlan, access: AccessContext | None) -> None:
    """Allow model transports to prepare plans and reject their approval or execution."""
    policy = authorization_for(plan.action_type)
    if policy.human_only and access is not None and access.entry in {"agent", "mcp"}:
        message = "Production plans must be approved and executed by a person in the Web UI or CLI"
        raise AuthorizationError(message)
    if access is not None and access.entry == "mcp":
        message = "MCP cannot approve or execute action plans"
        raise AuthorizationError(message)


def production_request(
    plan: ActionPlan, request: ExecuteRequest, access: AccessContext | None
) -> ExecuteRequest:
    """Apply entry restrictions and the existing stable production request identity."""
    require_production_human(plan, access)
    if "request_id" in plan.canonical_params and request.operation_id is None:
        return request.model_copy(update={"operation_id": plan.operation_id})
    return request
