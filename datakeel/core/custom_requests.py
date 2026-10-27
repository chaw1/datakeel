# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public requests and runtime disclosures for custom operator execution."""

from typing import Literal

from pydantic import Field, JsonValue

from datakeel.core.models import BoundaryModel


class RunCustomOperatorRequest(BoundaryModel):
    """Select a dataset snapshot and parameters for one immutable custom operator."""

    dataset_id: str = Field(min_length=1)
    version_id: str | None = None
    params: dict[str, JsonValue] = Field(default_factory=dict)
    name: str | None = None


class CustomOperatorConfiguration(BoundaryModel):
    """Disclose whether the local service enables the unsafe development backend."""

    backend: Literal["container", "subprocess"]
    subprocess_enabled: bool
    container_image: str
