# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze set-scoped capacities and complete target/reference membership before approval."""

from datakeel.core.models import AssetRef, FileItem
from datakeel.core.vector_models import (
    ClusterParams,
    DuplicateParams,
    EmbedParams,
    FrozenVectorSelection,
    VectorError,
    VectorMember,
    VectorReferenceSet,
    VectorScope,
)
from datakeel.evidence.vector_parameters import CoverageParams
from datakeel.evidence.vector_payload import prepare_wire
from datakeel.pipeline.models import Node


def freeze_selection(
    node: Node,
    source: Node,
    selected: list[FileItem],
    actual: list[FileItem],
    references: tuple[VectorReferenceSet, ...],
    version_id: str,
) -> FrozenVectorSelection:
    """Count complete eligible pairs or exact T-minus-R by R comparisons, never top-k."""
    embed = EmbedParams.model_validate(source.params)
    params = (
        CoverageParams.model_validate(node.params)
        if node.operator == "evidence.coverage_gap"
        else ClusterParams.model_validate(node.params)
        if node.operator in {"evidence.semantic_cluster", "evidence.semantic_outlier"}
        else DuplicateParams.model_validate(node.params)
    )
    scope = None
    if isinstance(params, CoverageParams):
        reference = next(item for item in references if item.node_id == node.id)
        targets = tuple(
            VectorMember(
                subject=next(
                    (m.subject for m in reference.members if m.subject.asset_id == f.id),
                    AssetRef(asset_type="file", asset_id=f.id, version=version_id),
                ),
                revision=prepare_wire(f, embed).frozen.content_revision,
                content_revision=prepare_wire(f, embed).frozen.content_revision,
            )
            for f in sorted(actual, key=lambda f: f.id)
        )
        scope = VectorScope(targets=targets, references=reference.members)
        ids = {m.subject.asset_id for m in reference.members}
        for member in reference.members:
            if (
                member.subject.asset_id in {f.id for f in selected}
                and member.subject.version != version_id
            ):
                msg = "vector_reference_ambiguous_version"
                raise VectorError(msg)
        size = len({f.id for f in selected} | ids)
        comparisons = len({f.id for f in selected} - ids) * len(ids)
        limit = params.max_reference_comparisons
    else:
        size = len(selected)
        eligible = sum(prepare_wire(file, embed).frozen.failure is None for file in selected)
        comparisons, limit = eligible * (eligible - 1) // 2, params.max_candidate_pairs
    if size > params.max_samples or comparisons > limit:
        msg = "vector_capacity_exceeded"
        raise VectorError(msg)
    return FrozenVectorSelection(
        node_id=node.id,
        embedding_node=source.id,
        actual_asset_ids=tuple(sorted(f.id for f in actual)),
        scope=scope,
    )
