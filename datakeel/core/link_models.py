# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable graph-to-catalog matches and latest-version query boundaries."""

from typing import Literal

from pydantic import Field

from datakeel.core.catalog_models import CatalogObject
from datakeel.core.evidence_models import Assertion
from datakeel.core.kg_execution import KGDocument
from datakeel.core.kg_product import KGEntity
from datakeel.core.models import BoundaryModel


class LinkMatch(BoundaryModel):
    """Keep exact matching evidence before a persisted assertion is assembled."""

    target: CatalogObject
    basis: tuple[str, ...]
    strength: Literal["exact", "synonym"] = "exact"


class LinkMetadata(BoundaryModel):
    """Freeze match cardinality and readable evidence with the immutable assertion."""

    match_kind: Literal["unique", "ambiguous"]
    basis: tuple[str, ...]


class EntityLink(LinkMetadata):
    """Expose the reviewable assertion and its graph and catalog endpoints."""

    assertion: Assertion
    entity: KGEntity
    target: CatalogObject


class LinkEntitySource(BoundaryModel):
    """Identify the source dataset of an otherwise opaque graph entity identity."""

    entity_id: str
    dataset_id: str
    dataset_name: str


class LinkContext(BoundaryModel):
    """Read raw current graphs without alias merging and their current associations."""

    entities: tuple[KGEntity, ...] = ()
    assertions: tuple[Assertion, ...] = ()
    links: tuple[EntityLink, ...] = ()
    entity_sources: tuple[LinkEntitySource, ...] = ()
    documents: tuple[KGDocument, ...] = ()


class LinkGraph(BoundaryModel):
    """Keep one latest published dataset version and its frozen source material."""

    dataset_id: str
    version_id: str
    entities: tuple[KGEntity, ...] = ()
    assertions: tuple[Assertion, ...] = ()
    documents: tuple[KGDocument, ...] = ()


class LinkRunResult(BoundaryModel):
    """Summarize an idempotent association refresh without exposing storage rows."""

    entities: int = Field(ge=0)
    links: int = Field(ge=0)
    created: int = Field(ge=0)
    invalidated: int = Field(ge=0)
