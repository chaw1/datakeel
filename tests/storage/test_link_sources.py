# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Retain each source mention as graph publications combine and replace documents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation
from datakeel.core.kg_models import ExtractionResult, RawExtraction
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.evidence_projection import rebuild_evidence
from datakeel.storage.link_queries import list_links, read_link_context
from tests.kg.integration_helpers import execute_graph, install_adapter, prepare_graph, text_dataset
from tests.storage.link_helpers import table_snapshot

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


def test_links_preserve_distinct_document_mentions_and_rebuild_without_duplicate_entities(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Merged entity links keep both original files and exact evidence projection after replay."""
    sentence = "Jordan owns sales table."
    dataset = text_dataset(db, tmp_path, (sentence + " Note A.", sentence + " Note B."))
    result = ExtractionResult(
        output=RawExtraction(
            entities=(
                ExtractedEntity(name="Jordan", type="person"),
                ExtractedEntity(name="sales table", type="dataset"),
            ),
            relations=(
                ExtractedRelation(
                    head="Jordan", relation="owns", tail="sales table", evidence=sentence
                ),
            ),
        )
    )
    publish_snapshot(db, table_snapshot())
    install_adapter(monkeypatch, (result, result))
    execute_graph(db, prepare_graph(db, dataset))
    links = list_links(db)
    assert len(links) == 1
    assert len(read_link_context(db).entities) == 2
    assert {anchor.asset_ref.asset_id for anchor in links[0].assertion.anchors} == {
        file.id for file in dataset.files
    }
    assert rebuild_evidence(db).matches
    assert list_links(db) == links
