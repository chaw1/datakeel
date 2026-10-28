# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check approved custom versions and parameters at durable submission boundaries."""

from sqlalchemy.orm import Session

from datakeel.core.custom_schema import validate_custom_values
from datakeel.core.models import JsonDocument
from datakeel.pipeline.models import Pipeline
from datakeel.storage.custom_store import approved_in_session


def validate_custom_pipeline(session: Session, pipeline: Pipeline | None) -> None:
    """Reject unpublished code and invalid parameters before persisting a task."""
    if pipeline is None:
        return
    for node in pipeline.nodes:
        if node.operator is None or not node.operator.startswith("custom."):
            continue
        version = approved_in_session(session, node.operator)
        validate_custom_values(version.parameter_schema, JsonDocument.model_validate(node.params))
