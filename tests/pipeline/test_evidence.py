# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The evidence preset resolves versions independently and stays inside the typed DAG."""

import re
from pathlib import Path

import pytest

from datakeel.operators import REGISTRY
from datakeel.operators.evidence import annotation_labels, caption_mentions, image_phash
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


def test_web_extraction_preset_pins_the_same_extractor_versions() -> None:
    """The Web's frozen preset must invalidate the same cache entries as the server's."""
    source = (Path(__file__).parents[2] / "web/src/features/evidence/extraction.ts").read_text(
        encoding="utf-8"
    )
    block = re.search(r"EXTRACTOR_VERSIONS = \{(.*?)\} as const", source, re.DOTALL)
    assert block is not None
    web = dict(re.findall(r'(\w+): "([^"]+)"', block.group(1)))
    server = {
        str(node.operator).removeprefix("evidence."): node.params["extractor_version"]
        for node in evidence_pipeline().nodes
        if node.operator
    }
    assert web == server


def test_orientation_affected_extractors_are_past_the_stored_frame_version() -> None:
    """v0.18.0 cached stored-pixel sizes and boxes at 1.0; those entries must not be reused."""
    assert image_phash.VERSION != "1.0"
    assert annotation_labels.VERSION != "1.0"
