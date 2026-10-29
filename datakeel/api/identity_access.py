# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Authorize legacy HTTP business mutations with registered server action scopes."""

from typing import TYPE_CHECKING, cast

from fastapi import Request

from datakeel.actions.models import ActionContext
from datakeel.actions.registry import action_definition
from datakeel.core.errors import AuthorizationError
from datakeel.storage.identity_authorization import effective_scopes

if TYPE_CHECKING:
    from fastapi.routing import APIRoute

    from datakeel.storage.database import Database

# Legacy endpoints reuse the closest existing controlled action scope. No HTTP-only scope exists.
MUTATION_ACTIONS: dict[tuple[str, str], str] = {
    ("POST", "/api/datasets"): "save_metadata",
    ("PUT", "/api/datasets/{identifier}/quality/config"): "create_quality_rule",
    ("PUT", "/api/datasets/{identifier}/template"): "save_metadata",
    ("PUT", "/api/datasets/{identifier}/metadata"): "save_metadata",
    ("POST", "/api/tasks"): "run_pipeline",
    ("POST", "/api/uploads"): "save_metadata",
    ("PUT", "/api/uploads/{identifier}/chunks/{ordinal}"): "save_metadata",
    ("POST", "/api/uploads/{identifier}/complete"): "save_metadata",
    ("POST", "/api/lineage/events"): "import_catalog",
    ("POST", "/api/openlineage/events"): "import_catalog",
    ("POST", "/api/catalog/import/dbt"): "import_catalog",
    ("POST", "/api/catalog/import/airflow"): "import_catalog",
    ("POST", "/api/custom-operators"): "submit_custom_operator",
    ("POST", "/api/custom-operators/{code_hash}/runs"): "run_pipeline",
    ("POST", "/api/datasets/{dataset_id}/annotation-quality/batches"): "save_metadata",
    ("POST", "/api/datasets/{dataset_id}/annotation-quality/samples"): "annotation_acceptance",
    (
        "POST",
        "/api/datasets/{dataset_id}/annotation-quality/acceptance/prepare",
    ): "annotation_acceptance",
    ("POST", "/api/evidence/assertions/decide"): "decide_assertions",
    ("POST", "/api/kg/links/rerun"): "decide_assertions",
    ("POST", "/api/datasets/{dataset_id}/datasheets"): "generate_datasheet",
    ("POST", "/api/datasheets/{document_id}/publish"): "publish_datasheet",
    ("POST", "/api/agent/memories"): "manage_users",
    ("DELETE", "/api/agent/memories/{memory_id}"): "manage_users",
    # Training splits exist only to define controlled export packages.
    (
        "POST",
        "/api/datasets/{identifier}/versions/{version_id}/training/splits",
    ): "export_dataset",
    (
        "POST",
        "/api/datasets/{identifier}/versions/{version_id}/training/import-annotations",
    ): "save_metadata",
    # Text dry runs and evaluation registrations are durable inputs of the clean action.
    ("POST", "/api/datasets/{dataset_id}/text-governance/analyze"): "clean_training_data",
    ("POST", "/api/datasets/{dataset_id}/text-governance/evaluations"): "clean_training_data",
    ("POST", "/api/training-governance/{run_id}/clean"): "clean_training_data",
}

# Read computations may retain audit/session state. Business writes inside tools remain scoped.
READ_OR_CONTROLLED_ROUTES = frozenset(
    {
        ("POST", "/api/production/functions/{name}"),
        ("POST", "/api/evidence/query"),
        ("POST", "/api/datasets/{identifier}/versions/{version_id}/training/preview"),
        ("POST", "/api/datasets/{identifier}/versions/{version_id}/training/leakage"),
        ("POST", "/api/ontology/object-sets/evaluate"),
        ("POST", "/api/kg/query"),
        ("POST", "/api/kg/graph"),
        ("POST", "/api/ask"),
        ("POST", "/api/ask/conversations"),
        ("DELETE", "/api/ask/conversations/{conversation_id}"),
        ("POST", "/api/data-assets/{asset_id}/applications"),
        ("POST", "/api/releases/{release_id}/export"),
        ("POST", "/api/releases/{release_id}/reconcile"),
        ("POST", "/api/agent/conversations"),
        ("POST", "/api/agent/conversations/{conversation_id}/messages"),
        ("POST", "/api/agent/conversations/{conversation_id}/resume"),
        ("POST", "/api/workflows/{workflow_id}/runs"),
        ("POST", "/api/workflows/runs/{run_id}/resume"),
        ("POST", "/api/actions/{action_type}/prepare"),
        ("POST", "/api/actions/{plan_id}/execute"),
        ("POST", "/api/approvals/{plan_id}"),
    }
)


def http_actor(request: Request) -> str:
    """Use the request identity after registration, retaining the legacy local HTTP actor."""
    db = cast("Database", request.app.state.db)
    actor = request.headers.get("X-Datakeel-Actor", "local")
    with db.session() as session:
        return "local" if effective_scopes(session, actor).zero_users else actor


def http_action_context(request: Request) -> ActionContext:
    """Attribute legacy preparation wrappers to the same server-selected HTTP actor."""
    return ActionContext(actor=http_actor(request))


def authorize_http_mutation(request: Request) -> None:
    """Block legacy write bypasses while leaving read computations and project actions intact."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    route = cast("APIRoute", request.scope["route"])
    key = (request.method, route.path)
    if key in READ_OR_CONTROLLED_ROUTES:
        return
    db = cast("Database", request.app.state.db)
    with db.session() as session:
        current = effective_scopes(session, request.headers.get("X-Datakeel-Actor", "local"))
        if current.zero_users:
            return
        action = MUTATION_ACTIONS.get(key)
        scope = action_definition(action).auth_scope if action else None
        if scope is None or scope not in current.scopes:
            msg = "HTTP business mutation requires a server-authorized action scope: " + (
                scope or "unregistered route"
            )
            raise AuthorizationError(msg)
