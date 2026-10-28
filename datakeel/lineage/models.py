# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed immutable domain evaluation results."""

from typing import Literal, Self

from pydantic import Field, model_validator

from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.evidence_models import Assertion
from datakeel.core.models import BoundaryModel, LineageEvent, Record

MIN_COLLAPSED_NODES = 4


class GraphQuery(BoundaryModel):
    """Bound an optional semantic projection while preserving legacy lineage queries."""

    asset: str | None = None
    asset_id: str | None = None
    direction: Literal["both", "upstream", "downstream"] = "both"
    depth: int = Field(default=20, ge=0, le=100)
    include_semantic: bool = False
    include_catalog: bool = False
    hops: int | None = Field(default=None, ge=1, le=3)
    max_nodes: int = Field(default=200, ge=1, le=1000)
    collapse: bool = False

    @model_validator(mode="after")
    def validate_focus(self) -> Self:
        """Reject two conflicting spellings of the same focused asset parameter."""
        if self.asset is not None and self.asset_id is not None and self.asset != self.asset_id:
            msg = "asset and asset_id must identify the same asset"
            raise ValueError(msg)
        if self.collapse and self.max_nodes < MIN_COLLAPSED_NODES:
            msg = "Collapsed graphs require room for the focus and three edge-kind aggregates"
            raise ValueError(msg)
        return self


class GraphOverlay(BoundaryModel):
    """Supply independently stored assertion and catalog projections to one graph BFS."""

    assertions: tuple[Assertion, ...] = ()
    catalog: CatalogSnapshot | None = None


class GraphNode(Record):
    """Asset identity and display data in a lineage projection."""

    id: str
    asset_id: str
    asset_type: str
    namespace: str
    label: str
    version: str | None = None
    display_name: str | None = None
    english_name: str | None = None
    quarantined: bool | None = None
    deleted: bool | None = None


class GraphEdge(Record):
    """Keep event-derived lineage distinct from a reviewed semantic assertion."""

    source: str
    target: str
    kind: Literal["lineage", "semantic", "catalog"] = "lineage"
    event_id: str | None = None
    operator: str
    event: LineageEvent | None = None
    link_type: str | None = None
    assertion: Assertion | None = None

    @model_validator(mode="after")
    def validate_backing(self) -> Self:
        """Require one authoritative backing and prevent semantic provenance claims."""
        if self.kind == "catalog":
            if (
                self.event_id is None
                or self.assertion is not None
                or self.link_type
                not in {
                    "contains",
                    "derived",
                    "measures",
                    "sliced_by",
                    "means",
                    "owned_by",
                    "references",
                }
                or (self.event is not None and self.event.event_id != self.event_id)
            ):
                msg = "Catalog edges require an explicit relationship and producing event"
                raise ValueError(msg)
            return self
        valid = (
            self.event_id is not None
            and (self.event is None or self.event_id == self.event.event_id)
            and self.assertion is None
            and self.link_type is None
            if self.kind == "lineage"
            else self.event is None
            and self.event_id is None
            and self.link_type == "similar_to"
            and self.assertion is not None
            and self.assertion.predicate == "near_duplicate_of"
        )
        if not valid:
            msg = "Graph edges must distinguish lineage events from semantic assertions"
            raise ValueError(msg)
        return self


class GraphView(Record):
    """A bounded lineage projection and the events backing its edges."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    events: list[LineageEvent]
    truncated: bool = False
