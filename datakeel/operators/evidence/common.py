# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared typed extraction boundaries and current-node metadata publication."""

import hashlib
from pathlib import Path

from pydantic import Field, JsonValue

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import EvidenceAnchor, Selector, Whole, require_version
from datakeel.core.models import AssetRef, FileItem
from datakeel.operators.base import Params, annotate


class EvidenceParams(Params):
    """Expose the selected implementation version as a reproducible DAG parameter."""

    extractor_version: str = Field(default="1.0", min_length=1)


def subject(file: FileItem) -> AssetRef:
    """Read the versioned source identity injected by the extraction runtime."""
    result = AssetRef.model_validate(file.metadata.get("evidence_subject"))
    require_version(result)
    return result


def content_hash(file: FileItem) -> str:
    """Hash actual materialized bytes rather than trusting a stale metadata digest."""
    return hashlib.sha256(Path(file.path).read_bytes()).hexdigest()


def anchor(file: FileItem, owner: AssetRef, selector: Selector | None = None) -> EvidenceAnchor:
    """Bind the file's current bytes and selector to its immutable source version."""
    ref = (
        owner
        if file.id == owner.asset_id
        else AssetRef(
            asset_type="file", asset_id=file.id, namespace=owner.namespace, version=owner.version
        )
    )
    return EvidenceAnchor(
        asset_ref=ref, content_revision=content_hash(file), selector=selector or Whole()
    )


def publish(
    file: FileItem, drafts: list[ObservationDraft], *, failed: bool = False, **metadata: JsonValue
) -> FileItem:
    """Replace current-node drafts while retaining upstream facts and source context."""
    return annotate(
        file,
        evidence_drafts=[draft.model_dump(mode="json") for draft in drafts],
        evidence_failed=failed,
        **metadata,
    )
