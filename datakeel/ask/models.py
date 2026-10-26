# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed internal boundaries for deterministic semantic parsing."""

from typing import Literal

from datakeel.core.ask_models import MatchEvidence
from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.metric_models import DimensionSlice, SemanticLayer, TimeRange
from datakeel.core.models import BoundaryModel


class MetricLexeme(BoundaryModel):
    """Identify one registered phrase and the semantic target it may match."""

    text: str
    source: str
    metric_id: str
    match_kind: Literal["exact", "synonym", "normalized", "prefix"]
    term_id: str | None = None


class TimeParse(BoundaryModel):
    """Return a resolved date interval or explicit unsupported-time reasons."""

    time_range: TimeRange | None = None
    matches: tuple[MatchEvidence, ...] = ()
    issues: tuple[str, ...] = ()


class DimensionParse(BoundaryModel):
    """Carry metric-scoped slices and optional groupings with their anchors."""

    slices: tuple[DimensionSlice, ...] = ()
    group_by: tuple[str, ...] = ()
    matches: tuple[MatchEvidence, ...] = ()
    issues: tuple[str, ...] = ()


class QueryContext(BoundaryModel):
    """Freeze metadata and definitions for one consistent parse-to-explain pass."""

    snapshot: CatalogSnapshot
    layer: SemanticLayer
