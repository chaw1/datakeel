# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Scripted adapters exercise the future extractor boundary without provider calls."""

from datakeel.core.evidence_models import EvidenceValue
from datakeel.core.models import FileItem
from datakeel.operators.evidence.llm_extractor import ExtractorAdapter, FakeExtractor, ScriptedFact


def test_fake_adapter_when_scripted_returns_typed_repeatable_observations(sample: FileItem) -> None:
    """Verify an offline fake carries source anchors but no event or run identity."""
    adapter: ExtractorAdapter = FakeExtractor(
        (ScriptedFact(object=EvidenceValue(concept="person", value="unknown")),)
    )
    observations = adapter.extract(sample)
    assert observations == adapter.extract(sample)
    assert observations[0].object == EvidenceValue(concept="person", value="unknown")
    assert observations[0].anchors[0].content_revision == sample.sha256
    assert observations[0].extractor.id == "evidence.llm_extractor"
    assert "producer_event_id" not in observations[0].model_dump()
