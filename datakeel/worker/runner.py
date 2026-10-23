# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute isolated shard attempts and publish only while the lease is held."""

import logging
import threading
import time

from datakeel.actions.worker import reconcile_runs, start_task_run
from datakeel.core.errors import ExecutionError
from datakeel.core.evidence_execution import EvidenceExecutionContext
from datakeel.evidence.execution import EvidenceExecution
from datakeel.pipeline import Pipeline, default_pipeline, run_pipeline
from datakeel.storage.database import Database, data_dir
from datakeel.storage.datasets import materialize_files, persist_files
from datakeel.storage.evidence_import import source_manifest
from datakeel.worker.observations import Observations
from datakeel.worker.queue import DatabaseQueue, Lease

logger = logging.getLogger(__name__)


def _pulse(queue: DatabaseQueue, lease: Lease, stop: threading.Event) -> None:
    while not stop.wait(max(0.1, queue.lease_seconds / 3)):
        if not queue.heartbeat(lease):
            return


def execute(queue: DatabaseQueue, lease: Lease) -> bool:
    """Run one attempt and persist either a fenced result or a durable failure."""
    stop = threading.Event()
    definition = Pipeline.model_validate(
        lease.pipeline if lease.pipeline is not None else default_pipeline()
    )
    observations = Observations(lease, definition)
    evidence = EvidenceExecution(
        queue.db,
        EvidenceExecutionContext(
            task_id=lease.task_id,
            shard_id=lease.shard_id,
            version_id=lease.input_version_id or source_manifest(queue.db, lease.dataset_id)[0],
        ),
    )
    heartbeat = threading.Thread(target=_pulse, args=(queue, lease, stop), daemon=True)
    heartbeat.start()
    try:
        output_dir = data_dir() / "runs" / lease.task_id / lease.shard_id / lease.owner
        output_dir.mkdir(parents=True, exist_ok=True)
        outputs = run_pipeline(
            materialize_files(lease.inputs),
            output_dir,
            lease.pipeline,
            observations.observe,
            operator_executor=evidence.execute_node,
        )
        persisted = persist_files(outputs)
        return queue.finish(lease, persisted, observations.events, evidence=tuple(evidence.pending))
    except Exception as exc:
        logger.exception("Shard execution failed", extra={"shard_id": lease.shard_id})
        accepted = queue.finish(
            lease,
            [],
            observations.events,
            error=f"{type(exc).__name__}: {exc}",
            evidence=tuple(evidence.pending),
        )
        if not accepted:
            msg = "Cannot persist shard failure after its lease was lost"
            raise ExecutionError(msg) from exc
        return accepted
    finally:
        stop.set()
        heartbeat.join(timeout=5)


def run_worker(
    db: Database, *, once: bool = False, queue_name: str = "cpu", poll: float = 0.25
) -> None:
    """Drain or continuously poll one durable queue, relaying terminal events."""
    queue = DatabaseQueue(db)
    while True:
        queue.reap()
        queue.relay()
        reconcile_runs(db)
        lease = queue.claim(queue_name)
        if lease:
            decision = start_task_run(db, lease.task_id)
            accepted = (
                execute(queue, lease)
                if decision.allowed
                else queue.finish(
                    lease, [], [], error=decision.error or "Action target validation failed"
                )
            )
            logger.info(
                "Shard attempt completed",
                extra={"shard_id": lease.shard_id, "committed": accepted},
            )
            queue.relay()
            reconcile_runs(db)
        elif once:
            return
        else:
            time.sleep(poll)
