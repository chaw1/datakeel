# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image source lookups load only runs that actually contain the requested asset."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from datakeel.core.kg_execution import KGJob
from datakeel.storage.kg_image_sources import image_source
from datakeel.storage.kg_queries import get_source_text
from datakeel.storage.kg_store import get_job
from tests.kg.helpers import graph_product, seed_graph
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.image_helpers import (
    image_dataset,
    install_transcriber,
    prepare_image,
    transcript,
    use_profile,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


def test_text_source_skips_all_image_run_parsing(db: Database) -> None:
    """Text-only drawers project their frozen source without parsing any execution run."""
    product, source = graph_product()
    seed_graph(db, product, source)
    other, unrelated = graph_product("Other", "unrelated")
    seed_graph(db, other, unrelated)
    with patch.object(KGJob, "model_validate", wraps=KGJob.model_validate) as parsed:
        assert image_source(db, "document", "version") is None
        parsed.assert_not_called()
        assert get_source_text(db, "document", "version").text == source.text
        parsed.assert_not_called()


def test_image_sources_parse_only_exact_asset_and_revision_runs(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both original and transcript references select the containing run before deserialization."""
    dataset = image_dataset(db, tmp_path, count=2)
    use_profile(monkeypatch)
    install_transcriber(monkeypatch, (transcript(), transcript("Other uses Widget.")))
    install_adapter(monkeypatch, (pair_result(), pair_result("Other", "Widget")))
    first = execute_graph(db, prepare_image(db, dataset, file_ids=[dataset.files[0].id]))
    second = execute_graph(db, prepare_image(db, dataset, file_ids=[dataset.files[1].id]))
    document = get_job(db, first.id).documents[0]
    assert document.image is not None
    for reference in (document.asset_ref, document.image.asset_ref):
        assert reference.version is not None
        with patch.object(KGJob, "model_validate", wraps=KGJob.model_validate) as parsed:
            assert image_source(db, reference.asset_id, reference.version) is not None
            assert parsed.call_count == 1
            assert parsed.call_args is not None
            assert parsed.call_args.args[0]["run"]["id"] == first.id
            parsed.reset_mock()
            assert image_source(db, reference.asset_id, "wrong-version") is None
            assert image_source(db, reference.asset_id, reference.version, second.id) is None
            parsed.assert_not_called()
