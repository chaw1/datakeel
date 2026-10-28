# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose persisted annotation quality through a strictly read-only tool."""

from datakeel.core.models import AssetRef, JsonDocument
from datakeel.ontology.annotation_parameters import AnnotationQualityParams
from datakeel.ontology.models import FunctionResult
from datakeel.storage.annotation_store import get_annotation_quality
from datakeel.storage.database import Database


def invoke_annotation_quality(db: Database, arguments: JsonDocument) -> FunctionResult:
    """Read saved metrics, suspicions, inspections and rework without executing an action."""
    params = AnnotationQualityParams.model_validate(arguments.root)
    overview = get_annotation_quality(db, params.dataset_id, params.version_id)
    return FunctionResult(
        function="annotation_quality",
        asset_refs=[
            AssetRef(asset_type="dataset", asset_id=params.dataset_id, version=params.version_id)
        ],
        data=overview.model_dump(mode="json"),
    )
