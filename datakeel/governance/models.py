# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed immutable domain evaluation results."""

from datakeel.core.models import Record
from datakeel.quality.models import DimensionView, IssueView


class ComplianceView(Record):
    """Governance compliance assessment."""

    total: float
    dimensions: dict[str, DimensionView]
    issues: list[IssueView]
