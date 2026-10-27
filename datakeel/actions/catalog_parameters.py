# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed metadata actions with separately frozen catalog state."""

from pydantic import Field

from datakeel.core.catalog_models import CatalogImportRequest, CatalogSnapshot, SqlFailure
from datakeel.core.metric_models import MetricDefinition, TermDefinition
from datakeel.core.models import BoundaryModel


class CatalogActionParams(BoundaryModel):
    """Mark metadata actions that must never select legacy file objects."""


class ImportCatalogParams(CatalogActionParams):
    """Freeze a server-reflected snapshot and individual SQL parsing failures."""

    request: CatalogImportRequest
    snapshot: CatalogSnapshot | None = None
    parse_failures: tuple[SqlFailure, ...] = ()


class RestoreCatalogParams(CatalogActionParams):
    """Restore an earlier source snapshot as a new append-only version."""

    scope: str = Field(pattern=r"^source:.+")
    version: int = Field(ge=0)


class UpdateMetricParams(CatalogActionParams):
    """Bind a replacement metric to its expected current definition version."""

    definition: MetricDefinition


class ConfirmMetricDraftParams(CatalogActionParams):
    """Approve an imported draft with an explicit or server-proposed complete definition."""

    draft_id: str = Field(min_length=1)
    definition: MetricDefinition | None = None


class RollbackMetricParams(CatalogActionParams):
    """Restore historical semantics while retaining the intervening revisions."""

    metric_id: str = Field(min_length=1)
    version: int = Field(ge=1)


class UpdateTermParams(CatalogActionParams):
    """Replace one glossary entry using its authoritative catalog revision."""

    definition: TermDefinition
    expected_revision: int = Field(ge=1)


class RollbackTermParams(CatalogActionParams):
    """Restore a prior glossary definition by its catalog revision."""

    term: str = Field(min_length=1)
    revision: int = Field(ge=1)
