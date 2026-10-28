# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compose a reusable sensor-inspection chain without implicit repair of values or units."""

from datakeel.operators.base import EmptyParams
from datakeel.operators.timeseries.models import (
    AnomalyParams,
    ColumnRange,
    GapsParams,
    TimeParams,
    UnitDeclaration,
    UnitParams,
)
from datakeel.pipeline.models import Node, Pipeline


def timeseries_pipeline(
    time_column: str = "timestamp",
    device_column: str | None = "device_id",
    interval_ms: int | None = None,
    values: tuple[str, ...] = (),
    ranges: tuple[ColumnRange, ...] = (),
    units: tuple[UnitDeclaration, ...] = (),
) -> Pipeline:
    """Profile sources, normalize and order timestamps, then retain all inspection evidence.

    Resampling is intentionally explicit: aggregating a signal before inspection can
    hide spikes. Original source coordinates remain available after normalization.
    """
    shared = TimeParams(time_column=time_column, device_column=device_column).model_dump()
    definitions = (
        ("profile", "table.profile", EmptyParams().model_dump()),
        ("timestamp", "timeseries.timestamp_normalize", shared),
        ("order", "timeseries.order_dedup", shared),
        (
            "gaps",
            "timeseries.gaps",
            GapsParams(**shared, expected_interval_ms=interval_ms).model_dump(),
        ),
        (
            "anomaly",
            "timeseries.anomaly",
            AnomalyParams(**shared, value_columns=list(values), ranges=list(ranges)).model_dump(),
        ),
        (
            "units",
            "timeseries.unit_check",
            UnitParams(**shared, declarations=list(units)).model_dump(),
        ),
    )
    nodes = [Node(id="route", kind="route", inputs={"files": "$input.files"})]
    source = "route.table"
    for identifier, operator, params in definitions:
        nodes.append(
            Node(id=identifier, operator=operator, inputs={"files": source}, params=params)
        )
        source = f"{identifier}.files"
    return Pipeline(nodes=nodes, outputs=[source], max_workers=1)
