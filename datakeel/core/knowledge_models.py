# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Separated catalog facts and source-backed one-hop knowledge answers."""

from typing import Literal, Self

from pydantic import Field, model_validator

from datakeel.core.kg_product import KGEntity
from datakeel.core.models import AssetRef, BoundaryModel

KnowledgeIntent = Literal["owner", "upstream", "downstream", "owned", "related"]
LinkStatus = Literal["candidate", "accepted"]


class KnowledgeSubject(BoundaryModel):
    """Identify a resolved subject or a safe clarification or suggestion candidate."""

    asset_ref: AssetRef
    name: str
    kind: Literal["metric", "table", "view", "owner", "kg_entity"]
    entity_type: str | None = None


class KnowledgeSystemRecord(BoundaryModel):
    """Expose a registered asset without conflating it with a document assertion."""

    asset_ref: AssetRef
    name: str
    relation: Literal["owner", "upstream", "downstream", "owned"]


class KnowledgeSubjectLink(BoundaryModel):
    """Explain the exact entity-to-asset assertion used to join a document claim."""

    entity: KGEntity
    asset_ref: AssetRef
    assertion_id: str
    link_status: LinkStatus


class KnowledgeOtherEnd(BoundaryModel):
    """Distinguish a linked data asset from missing and inapplicable catalog identities."""

    status: Literal["not_applicable", "linked", "not_in_catalog"]
    entity: KGEntity
    asset_ref: AssetRef | None = None
    assertion_id: str | None = None
    link_status: LinkStatus | None = None

    @model_validator(mode="after")
    def linked_evidence(self) -> Self:
        """Require a complete link receipt exactly when an endpoint is linked."""
        supplied = (self.asset_ref, self.assertion_id, self.link_status)
        if self.status == "linked" and any(value is None for value in supplied):
            msg = "Linked endpoints require an asset, assertion, and review status"
            raise ValueError(msg)
        if self.status != "linked" and any(value is not None for value in supplied):
            msg = "Unlinked endpoints cannot assert an asset or link receipt"
            raise ValueError(msg)
        return self


class KnowledgeEvidence(BoundaryModel):
    """Retain the verified evidence fragment and its immutable source document."""

    source: AssetRef
    document: str
    text: str
    start: int | None = None
    end: int | None = None


class KnowledgeClaim(BoundaryModel):
    """Carry one visible document assertion with independent review and source checks."""

    assertion_id: str
    head: KGEntity
    predicate: str
    tail: KGEntity
    relation_status: LinkStatus
    verification: Literal["verified", "needs_review"]
    evidence: tuple[KnowledgeEvidence, ...]
    subject_link: KnowledgeSubjectLink | None = None
    other_end: KnowledgeOtherEnd
    consistency: Literal["consistent", "not_in_system", "not_in_catalog"] | None = None


class KnowledgeAnswer(BoundaryModel):
    """Keep system records and document claims in separate, auditable collections."""

    intent: KnowledgeIntent
    subject: KnowledgeSubject | None = None
    system_records: tuple[KnowledgeSystemRecord, ...] = ()
    system_message: str = ""
    claims: tuple[KnowledgeClaim, ...] = ()
    pending_ambiguous_links: int = Field(default=0, ge=0)
    reason_code: Literal["unknown_subject", "ambiguous_subject", "no_knowledge"] | None = None
