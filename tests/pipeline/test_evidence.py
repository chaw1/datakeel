# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The evidence preset resolves versions independently and stays inside the typed DAG."""

import pytest

from datakeel.operators import REGISTRY
from datakeel.operators.evidence import caption_mentions
from datakeel.pipeline.evidence import evidence_pipeline
from datakeel.pipeline.validation import validate_pipeline


def test_evidence_pipeline_when_built_contains_only_five_deterministic_extractors() -> None:
    """Verify typed slot validation and explicit versions without a fake-model node."""
    pipeline, _ = validate_pipeline(evidence_pipeline())
    operators = [node.operator for node in pipeline.nodes if node.kind == "operator"]
    assert operators == [
        "evidence.image_phash",
        "evidence.caption_mentions",
        "evidence.annotation_labels",
        "evidence.label_gap",
        "evidence.near_duplicate",
    ]
    assert all(
        REGISTRY[str(identifier)].manifest.category == "evidence" for identifier in operators
    )


def test_evidence_pipeline_when_one_version_changes_changes_only_that_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify independent extractor parameters permit isolated cache invalidation."""
    before = evidence_pipeline()
    monkeypatch.setattr(caption_mentions, "VERSION", "1.1")
    after = evidence_pipeline()
    assert [old.id for old, new in zip(before.nodes, after.nodes, strict=True) if old != new] == [
        "caption_mentions"
    ]
