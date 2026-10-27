# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed internal boundaries for deterministic semantic parsing."""

from datetime import date
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


class TimeAtom(BoundaryModel):
    """Locate one calendar period, possibly without a year, or one resolved relative span."""

    start: int
    end: int
    kind: str
    year: int | None = None
    month: int = 1
    day: int | None = None
    months: int = 0
    interval_start: date | None = None
    interval_end: date | None = None
    issue: str | None = None


class TimeParse(BoundaryModel):
    """Return a resolved date interval or explicit unsupported-time reasons."""

    time_range: TimeRange | None = None
    basis: Literal["period", "as_of"] | None = None
    matches: tuple[MatchEvidence, ...] = ()
    issues: tuple[str, ...] = ()


class DimensionParse(BoundaryModel):
    """Carry metric-scoped slices and optional groupings with their anchors."""

    slices: tuple[DimensionSlice, ...] = ()
    group_by: tuple[str, ...] = ()
    matches: tuple[MatchEvidence, ...] = ()
    issues: tuple[str, ...] = ()
    consumed: tuple[tuple[int, int], ...] = ()


class Leftovers(BoundaryModel):
    """Report question fragments that look temporal or conditional but were not understood."""

    times: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    calculations: tuple[str, ...] = ()
    rankings: tuple[str, ...] = ()


class QueryContext(BoundaryModel):
    """Freeze metadata and definitions for one consistent parse-to-explain pass."""

    snapshot: CatalogSnapshot
    layer: SemanticLayer
