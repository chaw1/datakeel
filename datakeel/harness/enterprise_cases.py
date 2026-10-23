# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Seed generated enterprise facts for Agent scenarios without reaching through CLI layers."""

from pathlib import Path

from datakeel.catalog.service import import_catalog
from datakeel.core.catalog_models import CatalogImportRequest
from datakeel.core.harness_eval import CaseFixture
from datakeel.harness.resources import contract_path
from datakeel.metrics.loader import load_layer
from datakeel.sample_enterprise import generate_enterprise
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_files
from datakeel.storage.metric_store import install_layer


def seed_enterprise_case(db: Database, directory: Path) -> CaseFixture:
    """Import four local generated SQLite sources and the versioned semantic contract."""
    sample = generate_enterprise(directory / "enterprise")
    for source in sample.sources:
        import_catalog(
            db,
            CatalogImportRequest(
                source_id=source.id, name=source.name, connection_url=f"sqlite:///{source.path}"
            ),
        )
    install_layer(db, load_layer(contract_path("semantic-layer")))
    document = directory / "enterprise.txt"
    document.write_text("Fictional enterprise benchmark; no external data.")
    dataset = import_paths(db, "Generated enterprise golden", [document])
    return CaseFixture(dataset_id=dataset.id, file_id=list_files(db, dataset.id)[0].id)
