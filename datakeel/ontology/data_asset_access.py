# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve tool targets without trusting caller-supplied actor or entry fields."""

from datakeel.core.models import AssetRef, JsonDocument
from datakeel.ontology.tool_refs import argument_refs


def requested_refs(name: str, arguments: JsonDocument) -> tuple[AssetRef, ...]:
    """Include semantic pins that are not generic dataset/file argument references."""
    refs = argument_refs(name, arguments.root)
    metric_id = arguments.root.get("metric_id")
    if isinstance(metric_id, str):
        refs.append(AssetRef(asset_type="metric", asset_id=metric_id))
    subject_id = arguments.root.get("subject_id")
    if isinstance(subject_id, str):
        # Subject pins may refer to any catalog kind; the guard resolves their identity.
        refs.append(AssetRef(asset_type="resource", asset_id=subject_id))
    return tuple(refs)
