# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only annotation report selection shared by tool transports."""

from pydantic import Field

from datakeel.core.models import BoundaryModel


class AnnotationQualityParams(BoundaryModel):
    """Read one dataset's annotation history, optionally pinned to an exact version."""

    dataset_id: str = Field(min_length=1)
    version_id: str | None = Field(default=None, min_length=1)
