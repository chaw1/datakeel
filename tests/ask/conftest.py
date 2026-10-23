# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Semantic fixtures and isolated generated enterprise catalogs for question tests."""

from pathlib import Path

import pytest

from datakeel.catalog.service import import_catalog
from datakeel.core.catalog_models import CatalogImportRequest
from datakeel.core.metric_models import SemanticLayer
from datakeel.metrics.loader import load_layer
from datakeel.sample_enterprise import EnterpriseSample, generate_enterprise
from datakeel.storage.database import Database
from datakeel.storage.metric_store import install_layer


@pytest.fixture
def layer() -> SemanticLayer:
    """Load the actual shipped contract so matching tests cannot drift from the demo."""
    return load_layer(Path("contracts/semantic-layer"))


@pytest.fixture
def enterprise_sample(db: Database, tmp_path: Path, layer: SemanticLayer) -> EnterpriseSample:
    """Import generated local sources into the isolated test fact store."""
    sample = generate_enterprise(tmp_path / "enterprise")
    for source in sample.sources:
        import_catalog(
            db,
            CatalogImportRequest(
                source_id=source.id, name=source.name, connection_url=f"sqlite:///{source.path}"
            ),
        )
    install_layer(db, layer)
    return sample
