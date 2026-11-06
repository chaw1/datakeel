# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve every possible external branch against frozen original source bytes."""

from datakeel.core.models import FileItem
from datakeel.core.vector_models import (
    VECTOR_OPERATORS,
    EmbedParams,
    FrozenPayload,
    FrozenVectorNode,
    FrozenVectorSelection,
    VectorError,
    VectorPrepared,
    VectorReferenceSet,
    vector_hash,
)
from datakeel.evidence.vector_payload import prepare_wire
from datakeel.evidence.vector_plan_sets import freeze_selection
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
    if node.kind != "operator" or node.operator in VECTOR_OPERATORS:
        return _source(node.inputs["files"], nodes)
    msg = "duplicate_requires_vector_input"
    raise VectorError(msg)


def freeze_vectors(
    pipeline: Pipeline,
    files: list[FileItem],
    references: tuple[VectorReferenceSet, ...] = (),
    version_id: str = "",
) -> VectorPrepared:
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
            inputs = _embedding_inputs(node.id, nodes, selected, params, references)
            identities = tuple(sorted(set(identities) | {i.asset_id for i in inputs if i.subject}))
            frozen.append(
                FrozenVectorNode(
                    node_id=node.id, params=params, inputs=inputs, actual_asset_ids=identities
                )
            )
        else:
            source = nodes[_source(node.inputs["files"], nodes)]
            selections.append(
                freeze_selection(node, source, selected, actual, references, version_id)
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


def _embedding_inputs(
    node_id: str,
    nodes: dict[str, Node],
    selected: list[FileItem],
    params: EmbedParams,
    references: tuple[VectorReferenceSet, ...],
) -> tuple[FrozenPayload, ...]:
    inputs = {f.id: prepare_wire(f, params).frozen for f in selected}
    for group in references:
        if _source(nodes[group.node_id].inputs["files"], nodes) != node_id:
            continue
        for file, member in zip(group.files, group.members, strict=True):
            frozen = prepare_wire(file, params).frozen
            prior = inputs.get(file.id)
            if prior and prior.subject and prior.subject != member.subject:
                msg = "vector_reference_ambiguous_version"
                raise VectorError(msg)
            inputs[file.id] = frozen.model_copy(update={"subject": member.subject})
    return tuple(inputs[key] for key in sorted(inputs))
