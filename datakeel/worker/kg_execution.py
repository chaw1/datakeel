# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute frozen graph blocks incrementally without publishing unfenced facts."""

from time import perf_counter

from datakeel.core.errors import BudgetError, ConflictError
from datakeel.core.kg_errors import KGExtractionError
from datakeel.core.kg_execution import KGBlockFailure, KGCompletion, KGDocument, KGJob, KGLeaseFence
from datakeel.core.kg_models import ExtractionResult, TextBlock
from datakeel.core.kg_product import KGSource, ProductExtraction
from datakeel.core.models import utcnow
from datakeel.kg.assembly import assemble_extraction
from datakeel.kg.cache import build_cache_key, extraction_identity
from datakeel.kg.extractors import checked_extract
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_store import cache_block, cached_block
from datakeel.worker.kg_metering import MeteredExtractor
from datakeel.worker.kg_report import base_report, merge_products
from datakeel.worker.queue import DatabaseQueue, Lease


class KGExecution:
    """Keep successful products and visible failures for one leased worker attempt."""

    def __init__(
        self, queue: DatabaseQueue, lease: Lease, job: KGJob, adapter: MeteredExtractor
    ) -> None:
        """Bind extraction to the immutable job and current queue fence."""
        self.queue, self.lease, self.job, self.adapter = queue, lease, job, adapter
        self.fence = KGLeaseFence(task_id=lease.task_id, shard_id=lease.shard_id, owner=lease.owner)
        self.products: list[ProductExtraction] = []
        self.failures: list[KGBlockFailure] = []
        self.cached = self.extracted = 0
        self.stopped = False
        prepared = job.prepared
        self.extractor = extraction_identity(
            prepared.schema_definition, prepared.profile, prepared.recording_hash
        )

    def _failure(
        self, document: KGDocument, block: TextBlock, reason: str, *, attempted: bool = True
    ) -> bool:
        self.failures.append(
            KGBlockFailure(
                file_id=document.asset_ref.asset_id,
                filename=document.filename,
                start=block.start,
                end=block.end,
                reason=reason,
                attempted=attempted,
            )
        )
        return False

    def _assemble(self, document: KGDocument, block: TextBlock, result: ExtractionResult) -> None:
        source = KGSource(
            dataset_id=self.job.run.dataset_id,
            dataset_version_id=self.job.run.version_id,
            file=document.asset_ref,
            text=document.text,
            content_revision=document.content_revision,
            extractor=self.extractor,
            block_start=block.start,
            block_end=block.end,
        )
        self.products.append(
            assemble_extraction(result.output, self.job.prepared.schema_definition, source)
        )

    def _block(self, document: KGDocument, block: TextBlock) -> bool:
        prepared = self.job.prepared
        key = build_cache_key(
            block,
            prepared.schema_definition,
            prepared.profile,
            self.extractor,
            prepared.recording_hash,
        )
        result = cached_block(self.queue.db, key)
        if result is not None:
            self.cached += 1
        else:
            if self.stopped:
                return self._failure(document, block, "budget_exceeded", attempted=False)
            if not self.queue.heartbeat(self.lease):
                msg = "Graph worker lease was lost before a model request"
                raise ConflictError(msg)
            try:
                result = checked_extract(self.adapter, block, prepared.schema_definition)
            except BudgetError:
                self.stopped = True
                return self._failure(document, block, "budget_exceeded", attempted=False)
            except KGExtractionError as error:
                return self._failure(document, block, error.reason)
            if not cache_block(self.queue.db, self.fence, key, result):
                msg = "Graph worker lease was lost before cache publication"
                raise ConflictError(msg)
            self.extracted += 1
        self._assemble(document, block, result)
        return True

    def run(self) -> KGCompletion:
        """Continue failed blocks independently and stop only new calls when budget runs out."""
        started = perf_counter()
        complete: list[str] = []
        for document in self.job.documents:
            outcomes = [self._block(document, block) for block in document.blocks]
            if all(outcomes):
                complete.append(document.asset_ref.asset_id)
        products = merge_products(self.job, self.products)
        report = base_report(
            self.job, products, self.failures, list_traces(self.queue.db, self.job.run.id)
        ).model_copy(
            update={
                "cached": self.cached,
                "extracted": self.extracted,
                "elapsed_seconds": perf_counter() - started,
            }
        )
        status = (
            "budget_exceeded"
            if self.stopped or self.adapter.exceeded
            else "partial"
            if self.failures
            else "completed"
        )
        return KGCompletion(
            run=self.job.run.model_copy(
                update={
                    "status": status,
                    "completed_at": utcnow(),
                    "report": report,
                }
            ),
            products=products,
            replace_file_ids=tuple(complete),
        )
