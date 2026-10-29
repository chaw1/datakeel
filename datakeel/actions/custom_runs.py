# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Schedule immutable custom operators through the existing controlled task action."""

from datakeel.actions import service
from datakeel.actions.models import ActionContext, ActionRun, ExecuteRequest
from datakeel.core.custom_requests import RunCustomOperatorRequest
from datakeel.core.models import JsonDocument
from datakeel.pipeline.models import Node, Pipeline
from datakeel.storage.custom_store import get_custom_operator
from datakeel.storage.database import Database


def schedule_custom_run(
    db: Database, code_hash: str, request: RunCustomOperatorRequest, *, actor: str = "local"
) -> ActionRun:
    """Resolve an approved version and freeze a single-node durable operator chain."""
    version = get_custom_operator(db, code_hash, request.name)
    pipeline = Pipeline(
        nodes=[
            Node(
                id="custom",
                operator=version.id,
                inputs={"files": "$input.files"},
                params=request.params,
            )
        ],
        outputs=["custom.files"],
    )
    plan = service.prepare_action(
        db,
        "run_pipeline",
        JsonDocument(
            {
                "dataset_id": request.dataset_id,
                "version_id": request.version_id,
                "pipeline": pipeline.model_dump(mode="json"),
                "shards": 1,
                "queue": "cpu",
            }
        ),
        ActionContext(actor=actor),
    )
    return service.execute_plan(
        db,
        plan.id,
        ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id, actor=actor),
    )
