# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Declarative chart references into the authoritative query result rows."""

from typing import Literal

from datakeel.core.models import BoundaryModel

type ChartType = Literal[
    "scalar", "line", "bar", "horizontal_bar", "grouped_bar", "stacked_bar", "table"
]
type NumberFormat = Literal["number", "integer", "percent"]


class ChartSpec(BoundaryModel):
    """Describe presentation without copying, rounding, or replacing result data."""

    type: ChartType
    title: str
    description: str
    x: str | None = None
    y: tuple[str, ...] = ()
    series: str | None = None
    unit: str | None = None
    number_format: NumberFormat = "number"
    sort: Literal["source"] = "source"
    available_types: tuple[ChartType, ...] = ("table",)
    show_percent: bool = False
