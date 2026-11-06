# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Signed fake vector execution with two-level reuse and deferred atomic publication."""

import hashlib
import struct
import threading
from pathlib import Path

from pydantic import ValidationError

from datakeel.core.evidence_execution import EvidenceExecutionContext, PendingExtraction
from datakeel.core.models import AssetRef, FileItem
from datakeel.core.vector_models import (
    DuplicateParams,
    FrozenVectorNode,
    VectorError,
    VectorPermit,
    require_local_vector_objects,
    vector_hash,
)
from datakeel.core.vector_results import (
    VectorCacheProduct,
    VectorInputStatus,
    VectorNodeReport,
    VectorSample,
)
from datakeel.evidence.vector_duplicate import direct_pairs, global_key, vector_counts
from datakeel.evidence.vector_payload import PreparedWire, prepare_wire
from datakeel.evidence.vector_publication import vector_publication
from datakeel.evidence.vector_set_execution import compute_set
from datakeel.evidence.vector_transport import FakeVectorTransport
from datakeel.operators.base import OperatorResult
from datakeel.pipeline.models import Node
from datakeel.storage.database import Database
from datakeel.storage.vector_authorization import authorize_vector_node
from datakeel.storage.vector_budget import reserve_vector, settle_vector, unknown_vector
from datakeel.storage.vector_cache import vector_cached
from datakeel.storage.vector_references import reference_file


class VectorExecution:
    """Keep all vector products pending until the worker's complete DAG succeeds."""

    def __init__(
        self, db: Database, context: EvidenceExecutionContext, permit: VectorPermit
    ) -> None:
        """Bind the immutable version and consumed approval to this live worker."""
        require_local_vector_objects()
        if (
            context.version_id != permit.version_id
            or context.task_id != permit.task_id
            or context.shard_id != permit.shard_id
        ):
            msg = "vector_execution_identity_changed"
            raise VectorError(msg)
        self.db, self.context, self.permit = db, context, permit
        self.pending: list[PendingExtraction] = []
        self.samples: dict[str, tuple[VectorSample, ...]] = {}
        self.lock = threading.Lock()

    def execute_node(self, node: Node, files: list[FileItem], directory: Path) -> OperatorResult:
        """Dispatch only declared embedding/duplicate nodes under the same permit."""
        del directory
        with self.db.session() as session:
            prepared = authorize_vector_node(session, self.permit, node)
        if node.operator == "evidence.vector_embed":
            frozen = next((item for item in prepared.nodes if item.node_id == node.id), None)
            if frozen is None:
                msg = "vector_hidden_node_refused"
                raise VectorError(msg)
            with self.db.session() as session:
                extra = [
                    reference_file(session, item.subject)
                    for item in frozen.inputs
                    if item.subject and item.asset_id not in {f.id for f in files}
                ]
            result = self._embed(node, frozen, files + extra)
            return result.model_copy(
                update={"files": [f for f in result.files if f.id in {v.id for v in files}]}
            )
        selection = next((item for item in prepared.selections if item.node_id == node.id), None)
        if (
            selection is None
            or tuple(sorted(file.id for file in files)) != selection.actual_asset_ids
        ):
            msg = "vector_duplicate_inputs_changed"
            raise VectorError(msg)
        with self.lock:
            available = self.samples.get(selection.embedding_node, ())
        samples = tuple(
            sample
            for sample in available
            if sample.subject.asset_id in selection.actual_asset_ids
            or (
                selection.scope
                and sample.subject.asset_id
                in {m.subject.asset_id for m in selection.scope.references}
            )
        )
        if node.operator != "evidence.semantic_duplicate":
            computed = compute_set(self.db, samples, node, selection.scope)
            pending = vector_publication(
                self.context, node, computed.products, samples, computed.report, computed.output
            )
            with self.lock:
                self.pending.append(pending)
            return OperatorResult(files=files, quality=pending.event.quality)
        return self._duplicate(node, files, samples)

    def _duplicate(
        self, node: Node, files: list[FileItem], samples: tuple[VectorSample, ...]
    ) -> OperatorResult:
        if len(samples) != len(files):
            msg = "vector_duplicate_inputs_changed"
            raise VectorError(msg)
        params = DuplicateParams.model_validate(node.params)
        key = global_key(samples, params)
        cached = vector_cached(self.db, key, "global")
        pairs = cached.pairs if cached else direct_pairs(samples, params)
        products = (
            ()
            if any(sample.temporary for sample in samples)
            else (VectorCacheProduct(key=key, kind="global", samples=samples, pairs=pairs),)
        )
        counts = vector_counts(samples)
        if counts.input and not counts.eligible:
            msg = "vector_all_inputs_failed"
            raise VectorError(msg, counts)
        report = VectorNodeReport(
            status="partial_success" if counts.failed else "success",
            counts=counts,
            canonical_hash=vector_hash(
                {"key": key, "pairs": [pair.model_dump(mode="json") for pair in pairs]}
            ),
            cache_hits=len(samples) if cached else 0,
            eligible_cache_hits=counts.eligible if cached else 0,
        )
        pending = vector_publication(self.context, node, products, samples, report, pairs)
        with self.lock:
            self.pending.append(pending)
        return OperatorResult(files=files, quality=pending.event.quality)

    def _embed(self, node: Node, frozen: FrozenVectorNode, files: list[FileItem]) -> OperatorResult:
        if tuple(sorted(file.id for file in files)) != frozen.actual_asset_ids:
            msg = "vector_branch_inputs_changed"
            raise VectorError(msg)
        wires = [prepare_wire(file, frozen.params) for file in sorted(files, key=lambda f: f.id)]
        expected = {item.asset_id: item for item in frozen.inputs}
        wires = [
            wire.model_copy(
                update={
                    "frozen": wire.frozen.model_copy(
                        update={"subject": expected[wire.frozen.asset_id].subject}
                    )
                }
            )
            for wire in wires
        ]
        if any(wire.frozen not in frozen.inputs for wire in wires):
            msg = "vector_frozen_payload_changed"
            raise VectorError(msg)
        samples: list[VectorSample] = []
        products: list[VectorCacheProduct] = []
        hits = eligible_hits = requests = usage = 0
        for wire in wires:
            sample, cached, tokens = self._sample(frozen, wire)
            hits += int(cached)
            eligible_hits += int(cached and sample.failure is None)
            requests += int(not cached and wire.frozen.failure is None)
            usage += tokens
            samples.append(sample)
            if not sample.temporary:
                products.append(
                    VectorCacheProduct(
                        key=wire.frozen.cache_key, kind="embedding", samples=(sample,)
                    )
                )
        selected = tuple(samples)
        counts = vector_counts(selected)
        if counts.input and not counts.eligible:
            msg = "vector_all_inputs_failed"
            raise VectorError(msg, counts)
        report = VectorNodeReport(
            status="partial_success" if counts.failed else "success",
            counts=counts,
            canonical_hash=vector_hash(sorted(sample.canonical() for sample in selected)),
            cache_hits=hits,
            eligible_cache_hits=eligible_hits,
            fake_requests=requests,
            fake_usage=usage,
            fake_cost_nanos=usage * frozen.params.policy.nanos_per_token,
        )
        pending = vector_publication(self.context, node, tuple(products), selected, report)
        with self.lock:
            self.samples[node.id] = selected
            self.pending.append(pending)
        return OperatorResult(files=_annotated(files, selected), quality=pending.event.quality)

    def _sample(self, node: FrozenVectorNode, wire: PreparedWire) -> tuple[VectorSample, bool, int]:
        frozen = wire.frozen
        subject = frozen.subject or AssetRef(
            asset_type="file", asset_id=frozen.asset_id, version=self.context.version_id
        )
        cached = vector_cached(self.db, frozen.cache_key, "embedding")
        if cached:
            return cached.samples[0].model_copy(update={"subject": subject}), True, 0
        sample = VectorSample(
            subject=subject,
            content_revision=frozen.content_revision,
            embedding_key=frozen.cache_key,
            failure=frozen.failure or "pending",
        )
        if frozen.failure:
            return sample, False, 0
        attempt = reserve_vector(self.db, self.permit, node.node_id, frozen)
        try:
            response = FakeVectorTransport().send(self.db, self.permit, node, wire, attempt.id)
            raw = response.data[0].embedding
            vector = struct.unpack(f"<{len(raw)}f", struct.pack(f"<{len(raw)}f", *raw))
            valid = VectorSample(
                subject=subject,
                content_revision=frozen.content_revision,
                embedding_key=frozen.cache_key,
                vector=vector,
                f32le_sha256=hashlib.sha256(struct.pack(f"<{len(vector)}f", *vector)).hexdigest(),
            )
            settle_vector(
                self.db, self.permit, attempt.id, response.usage.total_tokens, response.id
            )
        except (VectorError, ValidationError, OverflowError, struct.error) as error:
            reason = error.reason if isinstance(error, VectorError) else "vector_invalid_response"
            unknown_vector(self.db, attempt.id, reason)
            if reason == "vector_temporary_input_failure":
                return sample.model_copy(update={"failure": reason, "temporary": True}), False, 0
            raise VectorError(reason) from None
        return valid, False, response.usage.total_tokens


def _annotated(files: list[FileItem], samples: tuple[VectorSample, ...]) -> list[FileItem]:
    by_id = {sample.subject.asset_id: sample for sample in samples}
    return [
        file.model_copy(
            update={
                "metadata": {
                    **file.metadata,
                    "vector_input": VectorInputStatus(
                        status="input_failed" if by_id[file.id].failure else "eligible",
                        reason=by_id[file.id].failure,
                    ).model_dump(mode="json"),
                }
            }
        )
        for file in files
    ]
