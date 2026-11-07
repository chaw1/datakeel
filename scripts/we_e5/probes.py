# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Count real worker invocations without replacing production computations or responses."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict

from datakeel.evidence import vector_duplicate, vector_sets
from datakeel.evidence.vector_transport import FakeVectorTransport

if TYPE_CHECKING:
    from collections.abc import Generator

    from datakeel.core.vector_models import (
        ClusterParams,
        DuplicateParams,
        FrozenVectorNode,
        VectorPermit,
        VectorScope,
    )
    from datakeel.core.vector_results import VectorFinding, VectorPair, VectorSample
    from datakeel.evidence.vector_parameters import CoverageParams
    from datakeel.evidence.vector_payload import PreparedWire
    from datakeel.evidence.vector_transport import FakeResponse
    from datakeel.storage.database import Database


class Counters(BaseModel):
    """Mutable in-process instrumentation only; never a cross-module product boundary."""

    model_config = ConfigDict(extra="forbid")
    dispatch: int = 0
    pairs: int = 0
    cluster: int = 0
    outlier: int = 0
    reference: int = 0


@contextmanager
def observed() -> Generator[Counters]:
    """Wrap actual kernels and the existing fake responder, preserving all return values."""
    count = Counters()
    original = FakeVectorTransport.send

    def send(
        self: FakeVectorTransport,
        db: Database,
        permit: VectorPermit,
        node: FrozenVectorNode,
        wire: PreparedWire,
        attempt_id: str,
    ) -> FakeResponse:
        count.dispatch += 1
        return original(self, db, permit, node, wire, attempt_id)

    def pairs(samples: tuple[VectorSample, ...], params: DuplicateParams) -> tuple[VectorPair, ...]:
        valid = sum(s.failure is None for s in samples)
        count.pairs += valid * (valid - 1) // 2
        return vector_duplicate.direct_pairs(samples, params)

    def cluster(
        samples: tuple[VectorSample, ...], params: ClusterParams, *, outlier: bool = False
    ) -> tuple[VectorFinding, ...]:
        valid = sum(s.failure is None for s in samples)
        comparisons = valid * (valid - 1) // 2
        if outlier:
            count.outlier += comparisons
        else:
            count.cluster += comparisons
        return vector_sets.cluster_findings(samples, params, outlier=outlier)

    def coverage(
        samples: tuple[VectorSample, ...], scope: VectorScope, params: CoverageParams
    ) -> tuple[VectorFinding, ...]:
        count.reference += len(
            {m.subject.asset_id for m in scope.targets}
            - {m.subject.asset_id for m in scope.references}
        ) * len(scope.references)
        return vector_sets.coverage_findings(samples, scope, params)

    with ExitStack() as stack:
        stack.enter_context(patch.object(FakeVectorTransport, "send", send))
        stack.enter_context(patch("datakeel.evidence.vector_execution.direct_pairs", pairs))
        stack.enter_context(
            patch("datakeel.evidence.vector_set_execution.cluster_findings", cluster)
        )
        stack.enter_context(
            patch("datakeel.evidence.vector_set_execution.coverage_findings", coverage)
        )
        yield count
