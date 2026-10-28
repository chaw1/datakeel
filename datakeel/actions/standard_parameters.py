# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed changes to field standards, reference codes and confirmed associations."""

from pydantic import Field

from datakeel.actions.catalog_parameters import CatalogActionParams
from datakeel.core.standard_models import (
    CodeList,
    ColumnMapping,
    FieldStandard,
    StandardsContract,
)


class StandardActionParams(CatalogActionParams):
    """Mark standards changes whose complete state is frozen independently of files."""


class ImportStandardsParams(StandardActionParams):
    """Merge validated definitions while retaining unspecified existing definitions."""

    contract: StandardsContract


class UpdateStandardParams(StandardActionParams):
    """Create or replace a field standard at its expected current version."""

    definition: FieldStandard


class UpdateCodeListParams(StandardActionParams):
    """Create or replace a code list at its expected current version."""

    definition: CodeList


class ConfirmStandardMappingParams(StandardActionParams):
    """Confirm one existing column's association with an active field standard."""

    mapping: ColumnMapping


class RollbackStandardsParams(StandardActionParams):
    """Restore prior semantics as a new revision; zero restores the initial empty state."""

    revision: int = Field(ge=0)
