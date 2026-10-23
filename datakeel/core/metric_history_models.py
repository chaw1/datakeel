# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public semantic audit and version history boundaries."""

from datetime import datetime

from datakeel.core.metric_models import MetricCard
from datakeel.core.models import BoundaryModel


class MetricAudit(BoundaryModel):
    """Attribute an authoritative semantic transition to its controlled plan."""

    plan_id: str
    actor: str
    metric_id: str
    from_version: int
    to_version: int
    event_id: str
    action_type: str
    created_at: datetime


class MetricHistory(BoundaryModel):
    """Return immutable definitions together with attributable changes."""

    metric_id: str
    versions: tuple[MetricCard, ...]
    audit: tuple[MetricAudit, ...]
