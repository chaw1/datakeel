# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Application services for artifact imports and extended catalog navigation."""

from datakeel.catalog.importers.dbt import prepare_dbt
from datakeel.core.metadata_imports import DbtImportRequest, MetadataImportReport
from datakeel.storage.database import Database
from datakeel.storage.metadata_store import publish_metadata


def import_dbt(
    db: Database, request: DbtImportRequest, actor: str = "local-user"
) -> MetadataImportReport:
    """Validate artifacts before atomically publishing their independent source scope."""
    return publish_metadata(db, prepare_dbt(request), actor)
