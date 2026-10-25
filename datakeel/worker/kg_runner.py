# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Construct the selected graph adapter only after worker authorization succeeds."""

import logging
import threading
from contextlib import ExitStack

from datakeel.core.errors import ValidationError
from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_execution import KGLeaseFence, KGMeteringConfig, KGPrepared
from datakeel.core.kg_models import ExtractionResult, Recording, TextBlock
from datakeel.extraction_runtime.factory import create_extractor
from datakeel.kg.extractors import ExtractorAdapter
from datakeel.storage.database import Database
from datakeel.storage.kg_inputs import restore_inputs
from datakeel.storage.kg_store import get_job, start_run
from datakeel.worker.heartbeat import pulse
from datakeel.worker.kg_execution import KGExecution
from datakeel.worker.kg_metering import MeteredExtractor
from datakeel.worker.kg_transcription import ImageTranscription
from datakeel.worker.queue import DatabaseQueue, Lease

logger = logging.getLogger(__name__)


class _DeferredAdapter:
    """Construct credentials and provider resources only when raw output is missing."""

    def __init__(self, prepared: KGPrepared, recording: Recording | None, stack: ExitStack) -> None:
        self.prepared, self.recording, self.stack = prepared, recording, stack
        self.adapter: ExtractorAdapter | None = None

    def initialize(self) -> ExtractorAdapter:
        if self.adapter is None:
            self.adapter = self.stack.enter_context(
                create_extractor(self.prepared.profile, recording=self.recording)
            )
        return self.adapter

    def extract(self, block: TextBlock, schema: KGSchema) -> ExtractionResult:
        return self.initialize().extract(block, schema)


class _DeferredMetering(MeteredExtractor):
    """Keep provider construction failures outside attempted-call budget accounting."""

    def __init__(self, db: Database, config: KGMeteringConfig, adapter: _DeferredAdapter) -> None:
        super().__init__(db, config, adapter)
        self.deferred = adapter

    def extract(self, block: TextBlock, schema: KGSchema) -> ExtractionResult:
        self.deferred.initialize()
        return super().extract(block, schema)


def execute_kg(queue: DatabaseQueue, lease: Lease) -> bool:
    """Publish a complete or partial graph report under the existing queue fence."""
    job = get_job(queue.db, lease.kg_run_id or "")
    fence = KGLeaseFence(task_id=lease.task_id, shard_id=lease.shard_id, owner=lease.owner)
    if not start_run(queue.db, job.run.id, fence):
        return False
    stop = threading.Event()
    heartbeat = threading.Thread(target=pulse, args=(queue, lease, stop), daemon=True)
    heartbeat.start()
    prepared = job.prepared
    config = KGMeteringConfig(
        run_id=job.run.id,
        profile=prepared.profile,
        price=prepared.accounting_price,
        price_version=prepared.accounting_price_version,
        known_price=prepared.estimate.price is not None,
        budget_tokens=job.budget_tokens,
        max_cost_usd=job.max_cost_usd,
    )
    try:
        inputs = restore_inputs(queue.db, job, fence)
        job = job.model_copy(update={"documents": inputs.documents})
        with ExitStack() as stack:
            if prepared.transcription_profile is not None:
                job = ImageTranscription(queue, lease, job, stack).run(inputs)
            adapter = _DeferredMetering(
                queue.db, config, _DeferredAdapter(prepared, inputs.recording, stack)
            )
            completion = KGExecution(queue, lease, job, adapter).run()
        return queue.finish(lease, lease.inputs, [], evidence=completion)
    except Exception as error:
        logger.exception("Graph worker failed", extra={"extraction_id": job.run.id})
        reason = str(error) if isinstance(error, ValidationError) else type(error).__name__
        return queue.finish(lease, [], [], error=f"Graph extraction failed: {reason}")
    finally:
        stop.set()
        heartbeat.join(timeout=5)
