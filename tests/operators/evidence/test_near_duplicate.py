# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Production dHash and matching recover direct pairs while rejecting transitive endpoints."""

from pathlib import Path

from datakeel.operators import REGISTRY
from datakeel.operators.evidence.near_duplicate import duplicate_pairs
from datakeel.sample_evidence import generate_samples
from tests.operators.evidence.helpers import drafts, paired_file


def test_near_duplicate_when_full_gold_supplied_meets_precision_and_recall(tmp_path: Path) -> None:
    """Verify generated images against production hashing, blocking, and pair matching."""
    gold = generate_samples(tmp_path)
    files = [paired_file(tmp_path, sample.image) for sample in gold.samples]
    measured = REGISTRY["evidence.image_phash"].run(files, tmp_path / "output").files
    pairs = {(left.id, right.id) for left, right, _ in duplicate_pairs(measured)}
    expected = {(pair.left, pair.right) for pair in gold.near_duplicate_pairs}
    cross = {pair for pair in expected if pair[0].split("/")[0] != pair[1].split("/")[0]}
    assert len(pairs & expected) / len(pairs) >= 0.9
    assert len(pairs & expected) / len(expected) >= 0.8
    assert len(pairs & cross) / len(cross) >= 0.8


def test_near_duplicate_when_chain_images_supplied_does_not_infer_endpoint_pair(
    tmp_path: Path,
) -> None:
    """Kill a four-bit threshold increase using actual generated PNG chain inputs."""
    gold = generate_samples(tmp_path, 100)
    chain = gold.non_transitive_chains[0]
    files = [paired_file(tmp_path, path) for path in (chain.c, chain.a, chain.b)]
    measured = REGISTRY["evidence.image_phash"].run(files, tmp_path / "output").files
    result = REGISTRY["evidence.near_duplicate"].run(measured, tmp_path / "output")
    observations = [draft for file in result.files for draft in drafts(file)]
    assert {(draft.subject.asset_id, draft.object.asset_id) for draft in observations} == {
        (chain.a, chain.b),
        (chain.b, chain.c),
    }
    assert [draft.distance for draft in observations] == [6, 6]
    assert all(draft.subject.asset_id < draft.object.asset_id for draft in observations)
    assert all(len(draft.anchors) == 2 for draft in observations)
