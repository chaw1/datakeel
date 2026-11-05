# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve every possible external branch against frozen original source bytes."""

from datakeel.core.models import FileItem
from datakeel.core.vector_models import (
    VECTOR_OPERATORS,
    DuplicateParams,
    EmbedParams,
    FrozenVectorNode,
    FrozenVectorSelection,
    VectorError,
    VectorPrepared,
    vector_hash,
)
from datakeel.evidence.vector_payload import prepare_wire
from datakeel.pipeline.models import ConditionParams, Node, Pipeline
from datakeel.pipeline.validation import reference, validate_pipeline


def has_vectors(pipeline: Pipeline | None) -> bool:
    """Classify the whole DAG, including hidden or inactive external nodes."""
    return pipeline is not None and any(n.operator in VECTOR_OPERATORS for n in pipeline.nodes)


def _selected(
    value: str, nodes: dict[str, Node], files: list[FileItem], *, possible: bool
) -> list[FileItem] | None:
    source, slot = reference(value)
    if source == "$input":
        return files
    node = nodes[source]
    selected = _selected(node.inputs["files"], nodes, files, possible=possible)
    if selected is None:
        return None
    if node.kind == "route":
        return [file for file in selected if file.modality == slot]
    if node.kind == "condition":
        if possible:
            return selected
        params = ConditionParams.model_validate(node.params)
        condition = len(selected) >= params.min_count and (
            params.max_count is None or len(selected) <= params.max_count
        )
        return selected if condition == (slot == "true") else []
    return selected if node.operator in VECTOR_OPERATORS else None


def _source(value: str, nodes: dict[str, Node]) -> str:
    source, _ = reference(value)
    if source == "$input":
        msg = "duplicate_requires_vector_input"
        raise VectorError(msg)
    node = nodes[source]
    if node.operator == "evidence.vector_embed":
        return source
    if node.kind != "operator" or node.operator == "evidence.semantic_duplicate":
        return _source(node.inputs["files"], nodes)
    msg = "duplicate_requires_vector_input"
    raise VectorError(msg)


def freeze_vectors(pipeline: Pipeline, files: list[FileItem]) -> VectorPrepared:
    """Freeze conditional alternatives and exact execution membership; reject transformed input."""
    validate_pipeline(pipeline)
    nodes = {node.id: node for node in pipeline.nodes}
    frozen: list[FrozenVectorNode] = []
    selections: list[FrozenVectorSelection] = []
    for node in pipeline.nodes:
        if node.operator not in VECTOR_OPERATORS:
            continue
        selected = _selected(node.inputs["files"], nodes, files, possible=True)
        actual = _selected(node.inputs["files"], nodes, files, possible=False)
        if selected is None or actual is None:
            msg = "unfreezable_upstream_payload"
            raise VectorError(msg)
        identities = tuple(sorted(file.id for file in actual))
        if node.operator == "evidence.vector_embed":
            params = EmbedParams.model_validate(node.params)
            inputs = tuple(
                prepare_wire(file, params).frozen for file in sorted(selected, key=lambda f: f.id)
            )
            frozen.append(
                FrozenVectorNode(
                    node_id=node.id, params=params, inputs=inputs, actual_asset_ids=identities
                )
            )
        else:
            limits = DuplicateParams.model_validate(node.params)
            source = nodes[_source(node.inputs["files"], nodes)]
            _capacity(selected, EmbedParams.model_validate(source.params), limits)
            selections.append(
                FrozenVectorSelection(
                    node_id=node.id,
                    embedding_node=_source(node.inputs["files"], nodes),
                    actual_asset_ids=identities,
                )
            )
    requests = sum(item.failure is None for node in frozen for item in node.inputs)
    cost = sum(
        item.token_bound * node.params.policy.nanos_per_token
        for node in frozen
        for item in node.inputs
    )
    return VectorPrepared(
        dag_hash=vector_hash(pipeline.model_dump(mode="json")),
        nodes=tuple(frozen),
        selections=tuple(selections),
        worst_requests=requests,
        worst_cost_nanos=cost,
    )


def _capacity(files: list[FileItem], embed: EmbedParams, params: DuplicateParams) -> None:
    eligible = sum(prepare_wire(file, embed).frozen.failure is None for file in files)
    if (
        len(files) > params.max_samples
        or eligible * (eligible - 1) // 2 > params.max_candidate_pairs
    ):
        msg = "vector_capacity_exceeded"
        raise VectorError(msg)
