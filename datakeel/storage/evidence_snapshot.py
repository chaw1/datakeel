# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Join current evidence projections by complete versioned identity inside one read session."""

import json
from collections import defaultdict

from pydantic import Field, JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.evidence_cache import EvidenceCacheEntry
from datakeel.core.evidence_models import Assertion
from datakeel.core.models import AssetRef, BoundaryModel, FileItem
from datakeel.storage.database import VersionRow
from datakeel.storage.evidence_rows import EvidenceCacheRow
from datakeel.storage.evidence_store import read_assertions


def identity(ref: AssetRef) -> str:
    """Use the original file identity for file/artifact views of one immutable version."""
    kind = "file" if ref.asset_type == "artifact" else ref.asset_type
    return json.dumps([ref.namespace, kind, ref.asset_id, ref.version], separators=(",", ":"))


class EvidenceObservations(BoundaryModel):
    """Collect stable extractor output fields and active assertion review overlays."""

    metadata: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])
    assertions: tuple[Assertion, ...] = ()


class EvidenceSnapshot(BoundaryModel):
    """Index a consistent transactional snapshot without keeping SQL row objects."""

    subjects: dict[str, EvidenceObservations]
    splits: dict[str, str] = Field(default_factory=dict[str, str])

    def observations(self, ref: AssetRef) -> EvidenceObservations:
        """Return exact-version observations, with canonical duplicate pairs expanded both ways."""
        return self.subjects.get(identity(ref), EvidenceObservations())


def _peer_splits(session: Session, keys: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for version in session.scalars(select(VersionRow)):
        for raw in version.manifest:
            ref = AssetRef(asset_type="file", asset_id=raw["id"], version=version.id)
            key = identity(ref)
            if key in keys:
                item = FileItem.model_validate(raw)
                split = item.metadata.get("split")
                if split in {"train", "val", "test"}:
                    result[key] = str(split)
    return result


def read_snapshot(session: Session, *, include_peer_splits: bool = False) -> EvidenceSnapshot:
    """Read active assertion statuses and cached facts once for a complete object query."""
    assertions: dict[str, list[Assertion]] = defaultdict(list)
    metadata: dict[str, dict[str, JsonValue]] = defaultdict(dict)
    for assertion in read_assertions(session):
        assertions[identity(assertion.subject)].append(assertion)
        if assertion.predicate == "near_duplicate_of" and isinstance(assertion.object, AssetRef):
            assertions[identity(assertion.object)].append(assertion)
    for row in session.scalars(select(EvidenceCacheRow).order_by(EvidenceCacheRow.slot)):
        entry = EvidenceCacheEntry.model_validate(row.payload)
        metadata[identity(entry.subject)].update(
            {name: value for name, value in entry.output.items() if name != "evidence_failed"}
        )
    keys = metadata.keys() | assertions.keys()
    return EvidenceSnapshot(
        subjects={
            key: EvidenceObservations(metadata=metadata[key], assertions=tuple(assertions[key]))
            for key in keys
        },
        splits=_peer_splits(session, keys) if include_peer_splits else {},
    )


def observed_file(file: FileItem, version: str, snapshot: EvidenceSnapshot) -> FileItem:
    """Map measured evidence back into the existing P1 file-quality vocabulary."""
    if "evidence_sample" not in file.metadata:
        return file
    facts = snapshot.observations(AssetRef(asset_type="file", asset_id=file.id, version=version))
    metadata = {**file.metadata, **facts.metadata}
    if "image_phash" in facts.metadata:
        metadata["corrupt"] = facts.metadata["image_phash"] is None
    dimensions = facts.metadata.get("image_dimensions")
    if isinstance(dimensions, dict):
        metadata.update({name: dimensions[name] for name in ("width", "height")})
    if "annotation_boxes" in facts.metadata:
        metadata["annotations"] = facts.metadata["annotation_boxes"]
    return file.model_copy(update={"metadata": metadata})
