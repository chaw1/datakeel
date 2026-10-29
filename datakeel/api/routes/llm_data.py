# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline training dry runs, user-registered evaluations and approved clean publication."""

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from datakeel.actions.models import ActionPlan
from datakeel.actions.service import prepare_action
from datakeel.api.dependencies import DatabaseDependency
from datakeel.api.identity_access import http_action_context
from datakeel.core.data_asset_models import AccessContext, AccessScope
from datakeel.core.llm_data_governance import (
    TrainingAnalysisRequest,
    TrainingEvaluation,
    TrainingEvaluationRequest,
    TrainingGovernanceRun,
)
from datakeel.core.models import JsonDocument
from datakeel.storage.llm_data_evaluations import list_evaluations, register_evaluation
from datakeel.storage.llm_data_store import (
    analyze_training,
    get_training_run,
    list_training_runs,
    resolve_training_ledger,
)

router = APIRouter(prefix="/api", tags=["training-governance"])


@router.get("/datasets/{dataset_id}/text-governance")
def reports(
    dataset_id: str, db: DatabaseDependency, request: Request, version_id: str | None = None
) -> tuple[TrainingGovernanceRun, ...]:
    """Read bounded reports for one pinned version or the latest immutable version."""
    return list_training_runs(db, dataset_id, version_id, access=_access(request))


@router.post("/datasets/{dataset_id}/text-governance/analyze")
def analyze(
    dataset_id: str, body: TrainingAnalysisRequest, db: DatabaseDependency, request: Request
) -> TrainingGovernanceRun:
    """Stream uploaded JSONL into a reproducible dry run without publishing clean files."""
    return analyze_training(db, dataset_id, body, access=_access(request))


@router.get("/datasets/{dataset_id}/text-governance/evaluations")
def evaluations(
    dataset_id: str, db: DatabaseDependency, request: Request
) -> tuple[TrainingEvaluation, ...]:
    """List the user's own registered evaluation file references."""
    return list_evaluations(db, dataset_id, access=_access(request))


@router.post("/datasets/{dataset_id}/text-governance/evaluations")
def register(
    dataset_id: str, body: TrainingEvaluationRequest, db: DatabaseDependency, request: Request
) -> TrainingEvaluation:
    """Register an exact uploaded JSONL or text manifest selection for contamination checks."""
    return register_evaluation(db, dataset_id, body, access=_access(request))


@router.get("/training-governance/{run_id}")
def report(run_id: str, db: DatabaseDependency, request: Request) -> TrainingGovernanceRun:
    """Return bounded redacted findings and any approved clean-version reference."""
    return get_training_run(db, run_id, access=_access(request))


@router.post("/training-governance/{run_id}/clean")
def clean(run_id: str, db: DatabaseDependency, request: Request) -> ActionPlan:
    """Prepare mandatory human approval bound to this exact dry run and frozen sources."""
    result = get_training_run(db, run_id, access=_access(request))
    return prepare_action(
        db,
        "clean_training_data",
        JsonDocument({"dataset_id": result.dataset_id, "run_id": run_id}),
        http_action_context(request),
    )


@router.get("/training-governance/{run_id}/ledger", response_class=FileResponse)
def ledger(run_id: str, db: DatabaseDependency, request: Request) -> FileResponse:
    """Download every keep, drop and redact decision with redacted evidence and reasons."""
    value = resolve_training_ledger(db, run_id, access=_access(request, "download"))
    return FileResponse(value.path, filename=value.filename, media_type="application/x-ndjson")


def _access(request: Request, scope: AccessScope = "query") -> AccessContext:
    return AccessContext(
        actor=request.headers.get("X-Datakeel-Actor", "local"),
        entry="download" if scope == "download" else "ask",
        scope=scope,
    )
