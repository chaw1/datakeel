# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only training queries shared by Agent and MCP transports."""

from pydantic import Field

from datakeel.core.models import BoundaryModel
from datakeel.core.training_models import SplitRequest


class TrainingDistributionParams(BoundaryModel):
    """Inspect a saved split or preview primary-label strata without saving any new split."""

    dataset_id: str = Field(min_length=1)
    version_id: str | None = Field(default=None, min_length=1)
    split_set_id: str | None = Field(default=None, min_length=1)
    request: SplitRequest = Field(default_factory=lambda: SplitRequest(name="preview"))


class TrainingLeakageParams(TrainingDistributionParams):
    """Check saved or external directory splits with direct pair evidence."""

    request: SplitRequest = Field(
        default_factory=lambda: SplitRequest(name="directory-preview", source="directory")
    )
