# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Content-addressed cache and event-bundle schemas without storage dependencies."""

import hashlib
import json
from typing import Literal, Self

from pydantic import Field, JsonValue, model_validator

from datakeel.core.evidence_models import (
    Assertion,
    AssertionDecision,
    ContentRevision,
    ExtractorRef,
    Selector,
    Whole,
    require_version,
)
from datakeel.core.models import AssetRef, BoundaryModel


class EvidenceInput(BoundaryModel):
    """Describe one actual extractor input by role, content, and selected region."""

    role: str = Field(min_length=1)
    content_revision: ContentRevision
    selector: Selector = Field(default_factory=Whole)


class EvidenceCacheKey(BoundaryModel):
    """Exclude locations and identities while including all actual input content."""

    inputs: tuple[EvidenceInput, ...] = Field(min_length=1)
    extractor: ExtractorRef
    lexicon_hash: ContentRevision
    near_duplicate_hash: ContentRevision
    schema_version: Literal["1.0"] = "1.0"

    def digest(self) -> str:
        """Hash a canonical ordering so input enumeration cannot invalidate reuse."""
        content = self.model_dump(mode="json")
        content["inputs"] = sorted(
            content["inputs"], key=lambda item: json.dumps(item, sort_keys=True)
        )
        return hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class EvidenceCacheEntry(BoundaryModel):
    """Associate cached content with the assertion identities it produced."""

    subject: AssetRef
    key: EvidenceCacheKey
    assertion_ids: tuple[str, ...]
    output: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])

    @model_validator(mode="after")
    def validate_subject(self) -> Self:
        """Bind reusable observations to a versioned subject identity."""
        require_version(self.subject)
        return self

    @property
    def slot(self) -> str:
        """Separate versioned provenance while keeping mutable paths out of identity."""
        return json.dumps(
            [
                self.subject.namespace,
                self.subject.asset_type,
                self.subject.asset_id,
                self.subject.version,
                self.key.extractor.id,
            ],
            separators=(",", ":"),
        )


class KnowledgeBundle(BoundaryModel):
    """Carry replayable immutable extraction products inside a COMPLETE event."""

    schema_version: Literal["1.0"] = "1.0"
    run_id: str = Field(min_length=1)
    assertions: tuple[Assertion, ...]
    cache_entries: tuple[EvidenceCacheEntry, ...] = ()
    invalidations: tuple[AssertionDecision, ...] = ()
    prior_cache_event_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_members(self) -> Self:
        """Reject duplicate identities and cache references outside this extraction."""
        assertions = {item.id: item for item in self.assertions}
        if len(assertions) != len(self.assertions):
            msg = "Knowledge bundle assertion identities must be unique"
            raise ValueError(msg)
        if any(item.run_id != self.run_id for item in self.assertions):
            msg = "Knowledge bundle assertions must belong to its run"
            raise ValueError(msg)
        for entry in self.cache_entries:
            if any(
                identifier not in assertions
                or assertions[identifier].extractor != entry.key.extractor
                or assertions[identifier].subject != entry.subject
                for identifier in entry.assertion_ids
            ):
                msg = "Cache entries must reference matching assertions from this run"
                raise ValueError(msg)
        return self


class KnowledgeBundleArtifact(BoundaryModel):
    """Reference an immutable bundle object without embedding semantics in lineage."""

    schema_version: Literal["1.0"] = "1.0"
    object_key: str
    content_revision: ContentRevision


class EvidenceRebuildResult(BoundaryModel):
    """Compare the normalized projection before and after authoritative replay."""

    before_hash: str
    after_hash: str
    matches: bool
    assertions: int
    events: int
