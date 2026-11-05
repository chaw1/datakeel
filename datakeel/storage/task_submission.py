# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Canonical direct queue validation, including refusal of external vector work."""

from typing import Any

from sqlalchemy.orm import Session

from datakeel.core.vector_models import VectorError
from datakeel.evidence.vector_plan import has_vectors
from datakeel.pipeline import Pipeline, validate_pipeline
from datakeel.pipeline.sharding import validate_shards
from datakeel.storage.custom_validation import validate_custom_pipeline


def canonical_pipeline(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Serialize an idempotent task pipeline consistently."""
    return Pipeline.model_validate(value).model_dump(mode="json") if value is not None else None


def submission_pipeline(
    value: Pipeline | dict[str, Any] | None, shards: int
) -> dict[str, Any] | None:
    """Validate shard constraints and refuse every direct external vector submission."""
    if value is None:
        return None
    validate_pipeline(value)
    definition = Pipeline.model_validate(value)
    validate_shards(definition, shards)
    if has_vectors(definition):
        msg = "vector_direct_queue_refused"
        raise VectorError(msg)
    return definition.model_dump(mode="json")


def validate_registered_pipeline(session: Session, value: dict[str, Any] | None) -> None:
    """Resolve custom registrations inside the task transaction."""
    validate_custom_pipeline(session, Pipeline.model_validate(value) if value else None)
