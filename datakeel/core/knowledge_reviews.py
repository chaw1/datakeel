# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed decisions for reproducible graph and catalog-link fixture reviews."""

from datakeel.core.evidence_models import AssertionStatus
from datakeel.core.models import BoundaryModel


class RelationReview(BoundaryModel):
    """Select one documented relationship and its explicit human decision."""

    head: str
    predicate: str
    tail: str
    status: AssertionStatus
    reason: str


class LinkReview(BoundaryModel):
    """Select one graph entity association and its explicit human decision."""

    entity: str
    target: str
    status: AssertionStatus
    reason: str


class KnowledgeReviews(BoundaryModel):
    """Load fixture decisions as data without embedding identities in runner code."""

    relations: tuple[RelationReview, ...] = ()
    links: tuple[LinkReview, ...] = ()
