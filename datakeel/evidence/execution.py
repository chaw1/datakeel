# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Incremental operator execution with publication deferred to the fenced worker."""

import threading
from pathlib import Path
from time import perf_counter

from datakeel.core.evidence_execution import EvidenceExecutionContext, PendingExtraction
from datakeel.core.evidence_models import ExtractorRef
from datakeel.core.models import FileItem, JsonDocument
from datakeel.evidence.runtime_compute import compute_node
from datakeel.evidence.runtime_inputs import prepare_node_inputs
from datakeel.evidence.runtime_publication import publication
from datakeel.operators import REGISTRY, OperatorResult
from datakeel.pipeline.models import Node
from datakeel.storage.database import Database
from datakeel.storage.evidence_cache import cached_entries


class EvidenceExecution:
    """Run deterministic extractors while retaining all writes as typed pending products."""

    def __init__(self, db: Database, context: EvidenceExecutionContext) -> None:
        """Bind durable cache reads to one leased attempt's immutable source version."""
        self.db = db
        self.context = context
        self.pending: list[PendingExtraction] = []
        self.lock = threading.Lock()

    def execute_node(self, node: Node, files: list[FileItem], directory: Path) -> OperatorResult:
        """Reuse exact input revisions or run only the invalidated operator samples."""
        operator = REGISTRY[str(node.operator)]
        if not str(node.operator).startswith("evidence."):
            return operator.run(files, directory, node.params)
        started = perf_counter()
        params = JsonDocument.model_validate(
            operator.params_type.model_validate(node.params).model_dump()
        )
        extractor = ExtractorRef(
            id=str(node.operator), version=str(params.root["extractor_version"])
        )
        prepared = prepare_node_inputs(files, self.context.version_id, extractor, params)
        requests = prepared.requests
        result = compute_node(
            node, prepared.files, directory, requests, cached_entries(self.db, requests)
        )
        pending = publication(self.context, node, result, perf_counter() - started)
        with self.lock:
            self.pending.append(pending)
        return OperatorResult(files=result.files, quality=pending.event.quality)
