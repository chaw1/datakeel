# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Optional bounded filtering over dataset manifests, preserving legacy full reads."""

from pydantic import Field

from datakeel.core.models import BoundaryModel


class FileQuery(BoundaryModel):
    """Select a bounded page after logical deletion and public field filtering."""

    offset: int = Field(default=0, ge=0)
    limit: int | None = Field(default=None, ge=1, le=1000)
    q: str = Field(default="", max_length=200)
    modality: str | None = Field(default=None, max_length=100)
