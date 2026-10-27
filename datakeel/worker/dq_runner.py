# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute frozen quality jobs and fence all result publication with shard leases."""

import logging
import threading

from datakeel.core.catalog_identity import catalog_id
from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqResult, DqRule
from datakeel.core.dq_monitor import DqCompletion
from datakeel.core.errors import ExecutionError
from datakeel.quality.dq_engine import execute_rule
from datakeel.storage.catalog_queries import get_object
from datakeel.storage.dq_reads import read_execution_inputs
from datakeel.worker.heartbeat import pulse
from datakeel.worker.queue import DatabaseQueue, Lease

logger = logging.getLogger(__name__)


def execute_dq(queue: DatabaseQueue, lease: Lease) -> bool:
    """Use the ordinary heartbeat and completion path for one quality-rule attempt."""
    stop = threading.Event()
    heartbeat = threading.Thread(target=pulse, args=(queue, lease, stop), daemon=True)
    heartbeat.start()
    rule: DqRule | None = None
    try:
        rule, history = read_execution_inputs(queue.db, lease.dq_run_id or "")
        source = SourceProperties.model_validate(
            get_object(queue.db, catalog_id(rule.target.source_id)).properties.root,
        )
        result = execute_rule(rule, source, history)
        return queue.finish(
            lease,
            [],
            [],
            evidence=DqCompletion(run_id=lease.dq_run_id or "", result=result),
        )
    except Exception as error:
        logger.exception("Quality attempt failed", extra={"run_id": lease.dq_run_id})
        if rule is not None:
            completion = DqCompletion(
                run_id=lease.dq_run_id or "",
                result=DqResult(
                    rule_id=rule.id,
                    rule_revision=rule.revision,
                    status="error",
                    threshold=rule.threshold,
                    message="Quality source unavailable",
                ),
            )
            accepted = queue.finish(lease, [], [], evidence=completion)
        else:
            accepted = queue.finish(lease, [], [], error="Quality job definition unavailable")
        if not accepted:
            msg = "Cannot persist quality failure after its lease was lost"
            raise ExecutionError(msg) from error
        return accepted
    finally:
        stop.set()
        heartbeat.join(timeout=5)
