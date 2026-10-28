# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze clean publication to a saved deterministic training governance dry run."""

from pydantic import Field

from datakeel.core.models import BoundaryModel


class CleanTrainingParams(BoundaryModel):
    """Bind approval to server-resolved source identities and a complete report digest."""

    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    version_id: str | None = None
    file_ids: tuple[str, ...] = ()
    report_digest: str = ""
