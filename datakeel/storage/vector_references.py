# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve complete relative reference sets without transport, credentials or display limits."""

from sqlalchemy.orm import Session

from datakeel.core.models import AssetRef, FileItem
from datakeel.core.vector_models import EmbedParams, VectorError, VectorMember, VectorReferenceSet
from datakeel.dataset_store.datasets import materialize_files
from datakeel.dataset_store.object_queries import matching_objects_in_session
from datakeel.dataset_store.rows import VersionRow
from datakeel.evidence.vector_parameters import CoverageParams
from datakeel.evidence.vector_payload import prepare_wire
from datakeel.pipeline.models import Pipeline
from datakeel.storage.evidence_snapshot import read_snapshot


def reference_file(session: Session, ref: AssetRef) -> FileItem:
    """Read the exact local immutable file version; never materialize an external object."""
    version = session.get(VersionRow, ref.version)
    raw = (
        next((item for item in version.manifest if item["id"] == ref.asset_id), None)
        if version
        else None
    )
    if raw is None:
        msg = "vector_reference_unavailable"
        raise VectorError(msg)
    return materialize_files([raw])[0]


def resolve_references(session: Session, pipeline: Pipeline) -> tuple[VectorReferenceSet, ...]:
    """Freeze every matching R identity/revision/content hash, ignoring ObjectSet.limit."""
    result: list[VectorReferenceSet] = []
    for node in pipeline.nodes:
        if node.operator != "evidence.coverage_gap":
            continue
        params = CoverageParams.model_validate(node.params)
        if params.reference.object_type != "file" or params.reference.include_deleted:
            msg = "vector_reference_requires_live_files"
            raise VectorError(msg)
        objects = matching_objects_in_session(
            session, params.reference, read_snapshot(session, validate_vectors=False)
        )
        if len(objects) > params.max_samples:
            msg = "vector_capacity_exceeded"
            raise VectorError(msg)
        files = tuple(reference_file(session, item.asset_ref) for item in objects)
        if len({f.id for f in files}) != len(files):
            msg = "vector_reference_ambiguous_version"
            raise VectorError(msg)
        members = tuple(
            VectorMember(
                subject=item.asset_ref,
                revision=item.revision,
                state_revision=item.state_revision,
                content_revision=prepare_wire(file, EmbedParams()).frozen.content_revision,
            )
            for item, file in zip(objects, files, strict=True)
        )
        result.append(VectorReferenceSet(node_id=node.id, files=files, members=members))
    return tuple(result)
