# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real generated enterprise setup shared by HTTP, function, and protocol regressions."""

from pathlib import Path

from datakeel.catalog.service import import_catalog
from datakeel.core.catalog_models import CatalogImportRequest
from datakeel.harness.resources import contract_path
from datakeel.metrics.loader import load_layer
from datakeel.sample_enterprise import EnterpriseSample, generate_enterprise
from datakeel.storage.database import Database
from datakeel.storage.metric_store import install_layer


def enterprise_fixture(db: Database, directory: Path) -> EnterpriseSample:
    """Install real sources and semantic contracts without any network or model calls."""
    sample = generate_enterprise(directory)
    for source in sample.sources:
        import_catalog(
            db,
            CatalogImportRequest(
                source_id=source.id, name=source.name, connection_url=f"sqlite:///{source.path}"
            ),
        )
    install_layer(db, load_layer(contract_path("semantic-layer")))
    return sample
