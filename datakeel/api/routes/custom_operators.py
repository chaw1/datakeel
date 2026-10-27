# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Review custom code and schedule approved content-addressed operator versions."""

from fastapi import APIRouter

from datakeel.actions import service
from datakeel.actions.custom_runs import schedule_custom_run
from datakeel.actions.models import ActionPlan, ActionRun
from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.custom_operators import (
    CustomOperatorRun,
    CustomOperatorSubmission,
    CustomOperatorVersion,
)
from datakeel.core.custom_requests import (
    CustomOperatorConfiguration,
    RunCustomOperatorRequest,
)
from datakeel.core.models import JsonDocument
from datakeel.core.settings import get_settings
from datakeel.storage import custom_store

router = APIRouter(prefix="/api/custom-operators", tags=["custom-operators"])


@router.post("", status_code=201)
def submit(body: CustomOperatorSubmission, db: DatabaseDependency) -> ActionPlan:
    """Prepare code review; submission alone never authorizes execution."""
    return service.prepare_action(
        db, "submit_custom_operator", JsonDocument(body.model_dump(mode="json"))
    )


@router.get("")
def versions(db: DatabaseDependency) -> list[CustomOperatorVersion]:
    """List immutable approved code versions that may enter an operator chain."""
    return custom_store.list_custom_operators(db)


@router.get("/submissions")
def submissions(db: DatabaseDependency) -> list[ActionPlan]:
    """Read submitted code, static findings and the durable review status."""
    return custom_store.list_custom_submissions(db)


@router.get("/runs")
def runs(db: DatabaseDependency, code_hash: str | None = None) -> list[CustomOperatorRun]:
    """Read successful and failed sandbox attempts without exposing host paths."""
    return custom_store.list_custom_runs(db, code_hash)


@router.get("/configuration")
def configuration() -> CustomOperatorConfiguration:
    """Expose the backend and an explicit warning flag for unsafe local development."""
    settings = get_settings()
    return CustomOperatorConfiguration(
        backend=settings.sandbox_backend,
        subprocess_enabled=settings.sandbox_allow_subprocess,
        container_image=settings.sandbox_image,
    )


@router.get("/{code_hash}")
def version(
    code_hash: str, db: DatabaseDependency, name: str | None = None
) -> CustomOperatorVersion:
    """Read full approved code and its reviewed declarations by content hash."""
    return custom_store.get_custom_operator(db, code_hash, name)


@router.post("/{code_hash}/runs", status_code=202)
def run(code_hash: str, body: RunCustomOperatorRequest, db: DatabaseDependency) -> ActionRun:
    """Enqueue an approved custom version against the selected dataset snapshot."""
    return schedule_custom_run(db, code_hash, body)
