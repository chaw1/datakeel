# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Transfer dimension slots across metrics only when registered semantics are unambiguous."""

from datakeel.core.ask_frame_models import AskQueryFrame
from datakeel.core.metric_models import (
    DimensionDefinition,
    DimensionSlice,
    MetricCard,
    SemanticLayer,
)


def inherit_frame(
    previous: AskQueryFrame, card: MetricCard, layer: SemanticLayer
) -> AskQueryFrame | None:
    """Preserve filters and groups, rejecting missing or multiply matched dimension contracts."""
    identities = {item.dimension_id for item in previous.slices} | set(previous.group_by)
    dimensions = {item.id: item for item in layer.dimensions}
    mapping: dict[str, str] = {}
    for identity in identities:
        if identity in card.definition.dimensions:
            mapping[identity] = identity
            continue
        source = dimensions.get(identity)
        candidates = [
            item
            for item in layer.dimensions
            if item.id in card.definition.dimensions
            and source is not None
            and _same_semantics(source, item)
        ]
        if len(candidates) != 1:
            return None
        mapping[identity] = candidates[0].id
    slices = tuple(
        DimensionSlice(dimension_id=mapping[item.dimension_id], value=item.value)
        for item in previous.slices
    )
    if any(
        str(item.value) not in dimensions[item.dimension_id].values
        for item in slices
        if dimensions[item.dimension_id].values
    ):
        return None
    return previous.model_copy(
        update={"slices": slices, "group_by": tuple(mapping[item] for item in previous.group_by)}
    )


def _same_semantics(source: DimensionDefinition, target: DimensionDefinition) -> bool:
    def names(item: DimensionDefinition) -> set[str]:
        return {
            label.casefold()
            for label in [item.name, item.english_name or "", *item.synonyms]
            if label
        }

    return bool(names(source) & names(target)) and set(source.values) == set(target.values)
