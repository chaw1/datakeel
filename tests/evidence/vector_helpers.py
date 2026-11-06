# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated local sources and the real controlled-action fake vector path."""

from pathlib import Path

from datakeel.actions.models import ActionPlan, ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.models import JsonDocument
from datakeel.core.vector_models import FrozenVectorNode, VectorPermit
from datakeel.dataset_store.dataset_service import import_paths
from datakeel.dataset_store.datasets import materialize_files
from datakeel.evidence.vector_payload import PreparedWire, prepare_wire
from datakeel.pipeline.models import Node, Pipeline
from datakeel.storage.database import Database
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.task_models import TaskView
from datakeel.storage.task_queries import query_task
from datakeel.storage.task_queue import DatabaseQueue, Lease
from datakeel.storage.vector_authorization import authorize_vector, vector_permit
from datakeel.worker.runner import run_worker


def vector_pipeline() -> Pipeline:
    """Use the ordinary run_pipeline DAG with explicit fake and direct duplicate nodes."""
    return Pipeline(
        nodes=[
            Node(id="embed", operator="evidence.vector_embed", inputs={"files": "$input.files"}),
            Node(
                id="pairs",
                operator="evidence.semantic_duplicate",
                inputs={"files": "embed.files"},
                params={"threshold": 0.0},
            ),
        ],
        outputs=["pairs.files"],
        max_workers=1,
    )


def vector_dataset(
    db: Database, directory: Path, contents: tuple[bytes, ...] = (b"one", b"two", b"three")
) -> str:
    """Import only generated local text without external fixtures or network sources."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, content in enumerate(contents):
        path = directory / f"source-{index}.txt"
        path.write_bytes(content)
        paths.append(path)
    return import_paths(db, "generated vectors", paths).id


def vector_prepare(
    db: Database, dataset_id: str, pipeline: Pipeline | None = None, version_id: str | None = None
) -> ActionPlan:
    """Prepare and freeze through the production action service."""
    return prepare_action(
        db,
        "run_pipeline",
        JsonDocument.model_validate(
            {
                "dataset_id": dataset_id,
                "version_id": version_id or source_manifest(db, dataset_id)[0],
                "pipeline": (pipeline or vector_pipeline()).model_dump(mode="json"),
            }
        ),
    )


def vector_schedule(db: Database, plan: ActionPlan) -> str:
    """Consume an actual approval and return its durable worker task identity."""
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    action = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert action.task_id is not None
    return action.task_id


def vector_run(db: Database, dataset_id: str, pipeline: Pipeline | None = None) -> TaskView:
    """Drain the real worker with the fake-only transport and query its durable status."""
    task_id = vector_schedule(db, vector_prepare(db, dataset_id, pipeline))
    run_worker(db, once=True)
    return query_task(db, task_id)


def leased_vector(
    db: Database, directory: Path
) -> tuple[Lease, VectorPermit, FrozenVectorNode, PreparedWire]:
    """Return the actual signed, persisted, leased request for boundary and crash tests."""
    dataset = vector_dataset(db, directory)
    vector_schedule(db, vector_prepare(db, dataset))
    lease = DatabaseQueue(db).claim()
    assert lease is not None
    permit = vector_permit(db, lease.task_id, lease.shard_id, lease.owner)
    with db.session() as session:
        frozen = authorize_vector(session, permit).nodes[0]
    files = sorted(materialize_files(lease.inputs), key=lambda file: file.id)
    return lease, permit, frozen, prepare_wire(files[0], frozen.params)
