# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Direct cosine semantics, canonical F32 output and bounded complete comparisons."""

import math

import pytest

from datakeel.core.models import AssetRef
from datakeel.core.vector_models import DuplicateParams, VectorError, vector_hash
from datakeel.core.vector_results import VectorSample
from datakeel.evidence.vector_duplicate import direct_pairs, global_key


def _sample(identifier: str, angle: float) -> VectorSample:
    return VectorSample(
        subject=AssetRef(asset_type="file", asset_id=identifier, version="v1"),
        content_revision=vector_hash(identifier),
        embedding_key=vector_hash([identifier]),
        vector=(math.cos(angle), math.sin(angle)),
    )


def test_direct_pairs_are_nontransitive_and_input_order_invariant() -> None:
    """A~B and B~C never imply A~C, regardless of enumeration order."""
    samples = (_sample("a", 0), _sample("b", 0.4), _sample("c", 0.8))
    params = DuplicateParams(threshold=0.9)
    pairs = direct_pairs(samples, params)
    assert [(pair.left, pair.right) for pair in pairs] == [("a", "b"), ("b", "c")]
    assert direct_pairs(tuple(reversed(samples)), params) == pairs
    assert global_key(samples, params) == global_key(tuple(reversed(samples)), params)


@pytest.mark.parametrize(("count", "limit"), [(3, 2), (4, 5)])
def test_capacity_rejects_complete_set_before_partial_result(count: int, limit: int) -> None:
    """The bound applies to every candidate pair, without top-k or half publication."""
    samples = tuple(_sample(str(index), 0.1) for index in range(count))
    with pytest.raises(VectorError, match="capacity"):
        direct_pairs(samples, DuplicateParams(max_candidate_pairs=limit))


def test_equal_vectors_different_original_bytes_change_global_identity() -> None:
    """Preprocessing equivalence must not preserve stale original anchors."""
    samples = (_sample("a", 0), _sample("b", 0))
    changed = samples[1].model_copy(update={"content_revision": vector_hash("other original")})
    params = DuplicateParams()
    assert direct_pairs(samples, params) == direct_pairs((samples[0], changed), params)
    assert global_key(samples, params) != global_key((samples[0], changed), params)
