# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Extension boundary for future file import adapters; P4 implements only SQLite."""

from typing import Protocol

from datakeel.catalog.importers.models import ImportBatch
from datakeel.core.catalog_models import CatalogImportRequest


class CatalogImporter(Protocol):
    """Expose typed reflection without prescribing a file or database implementation."""

    def reflect(self, request: CatalogImportRequest) -> ImportBatch:
        """Read metadata from an explicitly authorized source without mutating it."""
        ...
