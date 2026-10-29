# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evidence reads and reversible, audited assertion decisions."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from datakeel.actions import service as actions
from datakeel.actions.models import ActionRun, ExecuteRequest
from datakeel.actions.parameters import DecideAssertionsParams
from datakeel.api.dependencies import DatabaseDependency
from datakeel.api.identity_access import http_action_context
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import JsonDocument
from datakeel.evidence.query_models import EvidenceQuery, EvidenceQueryResult, EvidenceSample
from datakeel.storage import evidence_queries

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


@router.post("/query")
def query(body: EvidenceQuery, db: DatabaseDependency, request: Request) -> EvidenceQueryResult:
    """Select versioned samples with bounded, asset-ordered evidence pagination."""
    return evidence_queries.query_evidence(db, body, access=_access(request))


@router.get("/assets/{asset_id}")
def asset(
    asset_id: str,
    db: DatabaseDependency,
    request: Request,
    version_id: Annotated[str | None, Query(min_length=1)] = None,
) -> EvidenceSample:
    """Read one sample's active evidence, optionally bound to its displayed source version."""
    return evidence_queries.get_evidence(db, asset_id, version_id, access=_access(request))


@router.post("/assertions/decide")
def decide(body: DecideAssertionsParams, db: DatabaseDependency, request: Request) -> ActionRun:
    """Apply an explicit local decision through the same frozen-plan action boundary."""
    plan = actions.prepare_action(
        db,
        "decide_assertions",
        JsonDocument.model_validate(body.model_dump(mode="json")),
        http_action_context(request),
    )
    return actions.execute_plan(
        db,
        plan.id,
        ExecuteRequest(
            plan_digest=plan.plan_digest, operation_id=plan.operation_id, actor=plan.actor
        ),
    )


def _access(request: Request) -> AccessContext:
    return AccessContext(
        actor=request.headers.get("X-Datakeel-Actor", "local-user"), entry="ask", scope="query"
    )
