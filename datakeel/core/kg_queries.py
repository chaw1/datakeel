# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only entity, relation, evidence explanation and bounded graph contracts."""

from pydantic import Field

from datakeel.core.evidence_models import Assertion, AssertionStatus, Verification
from datakeel.core.kg_product import KGEntity
from datakeel.core.models import AssetRef, BoundaryModel


class KGQuery(BoundaryModel):
    """Select one dataset-version graph with explicit bounded result filters."""

    dataset_id: str | None = None
    version_id: str | None = None
    name: str | None = None
    entity_type: str | None = None
    status: AssertionStatus | None = None
    verification: Verification | None = None
    limit: int = Field(default=100, ge=1, le=500)


class KGEntityView(KGEntity):
    """Expose all source mentions for one deterministic entity identity."""

    mentions: tuple[Assertion, ...] = ()
    mention_count: int = 0


class KGRelationView(BoundaryModel):
    """Present an assertion with readable endpoints and extraction attribution."""

    assertion: Assertion
    head: KGEntity
    tail: KGEntity
    extractor: str
    model: str
    extraction_id: str


class KGQueryResult(BoundaryModel):
    """Return entities and relations from exactly one dataset version."""

    dataset_id: str | None = None
    version_id: str | None = None
    entities: tuple[KGEntityView, ...] = ()
    relations: tuple[KGRelationView, ...] = ()
    truncated: bool = False


class KGSourceText(BoundaryModel):
    """Return the precise decoded text used by verification offsets."""

    asset_ref: AssetRef
    filename: str
    text: str


class KGRelationExplanation(BoundaryModel):
    """Keep all checks and original documents together for a human review drawer."""

    relation: KGRelationView
    sources: tuple[KGSourceText, ...]


class KGGraphNode(BoundaryModel):
    """Represent one displayed entity or an accepted pair alias group."""

    id: str
    label: str
    entity_type: str
    members: tuple[str, ...]


class KGGraphEdge(BoundaryModel):
    """Keep graph styling tied to the independent review and verification states."""

    id: str
    source: str
    target: str
    predicate: str
    status: AssertionStatus
    verification: Verification | None = None


class KGGraph(BoundaryModel):
    """Bound the displayed projection without changing underlying assertions."""

    dataset_id: str | None = None
    version_id: str | None = None
    nodes: tuple[KGGraphNode, ...] = ()
    edges: tuple[KGGraphEdge, ...] = ()
    truncated: bool = False
