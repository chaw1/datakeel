# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run approved model documentation tasks under the existing shard lease."""

import logging
import threading

from datakeel.core.agent_models import Provider
from datakeel.core.datasheet_execution import DatasheetCompletion, DatasheetFence
from datakeel.core.datasheet_models import DatasheetDocument
from datakeel.datasheets.validation import parse_model_output
from datakeel.runtime.datasheet_model import draft_with_model
from datakeel.storage.datasheet_jobs import job_input
from datakeel.worker.heartbeat import pulse
from datakeel.worker.queue import DatabaseQueue, Lease

logger = logging.getLogger(__name__)


def execute_datasheet(
    queue: DatabaseQueue,
    lease: Lease,
    supplied: Provider | None = None,
) -> bool:
    """Validate each proposed sentence before atomically publishing the fenced document."""
    stop = threading.Event()
    heartbeat = threading.Thread(target=pulse, args=(queue, lease, stop), daemon=True)
    heartbeat.start()
    try:
        fence = DatasheetFence(task_id=lease.task_id, shard_id=lease.shard_id, owner=lease.owner)
        job, prepared = job_input(queue.db, lease.datasheet_job_id or "", fence)
        output = draft_with_model(queue.db, job, prepared, fence, supplied)
        checked = parse_model_output(output, prepared.facts, job.language)
        document = DatasheetDocument(
            id=job.id,
            dataset_id=job.dataset_id,
            version_id=job.version_id,
            language=job.language,
            facts=prepared.facts,
            sections=checked.sections,
            dropped_sentences=checked.dropped_sentences,
            mode="model",
        )
        return queue.finish(
            lease, [], [], evidence=DatasheetCompletion(job_id=job.id, document=document)
        )
    except Exception as error:
        logger.exception("Datasheet generation failed", extra={"job_id": lease.datasheet_job_id})
        return queue.finish(
            lease, [], [], error=f"Datasheet generation failed: {type(error).__name__}"
        )
    finally:
        stop.set()
        heartbeat.join(timeout=5)
