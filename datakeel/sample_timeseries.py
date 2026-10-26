# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate a deterministic week of fictional smart-kitchen sensor observations."""

import csv
from datetime import UTC, datetime, timedelta, timezone
from math import cos, sin
from pathlib import Path

from datakeel.core.models import BoundaryModel

SAMPLE_INTERVAL_MS = 300_000
WEEK_SAMPLES = 7 * 24 * 12
TIMEZONE_RANGE = range(120, 180)
STUCK_RANGE = range(500, 548)
UNIT_RANGE = range(900, 912)
GAP_RANGES = {"kitchen-01": range(1000, 1012), "kitchen-02": range(1300, 1324)}
SAMPLES_PER_HOUR = 12
COLUMNS = (
    "timestamp",
    "device_id",
    "temperature",
    "fan_speed",
    "fire_level",
    "gas_flow",
    "switch_event",
    "contact_phone",
)


class SensorSamples(BoundaryModel):
    """Identify generated inputs and the deliberately faulty device/sample ranges."""

    paths: tuple[Path, ...]
    interval_ms: int = SAMPLE_INTERVAL_MS
    samples_per_device: int = WEEK_SAMPLES
    devices: tuple[str, ...] = ("kitchen-01", "kitchen-02", "kitchen-03")


def _row(device: str, index: int, *, faults: bool) -> tuple[str, ...]:
    moment = datetime(2026, 1, 5, tzinfo=UTC) + timedelta(minutes=5 * index)
    timestamp = moment.isoformat()
    if faults and device == "kitchen-01" and index in TIMEZONE_RANGE:
        timestamp = moment.astimezone(timezone(timedelta(hours=8))).isoformat()
    temperature = 65 + 4 * sin(index / 23) + cos(index / 7)
    if faults and device == "kitchen-02" and index in STUCK_RANGE:
        temperature = 63
    if faults and device == "kitchen-01" and index in {310, 810, 1510}:
        temperature = 220
    flow = f"{2 + 0.1 * sin(index / 17):.4f} L/min"
    if faults and device == "kitchen-03" and index in UNIT_RANGE:
        flow = f"{0.12 + 0.006 * sin(index / 17):.4f} m3/h"
    return (
        timestamp,
        device,
        f"{temperature:.5f}",
        f"{900 + 60 * cos(index / 29):.5f}",
        str(1 + index // 12 % 4),
        flow,
        "on" if index % 24 < SAMPLES_PER_HOUR else "off",
        "+1 202-555-0100",
    )


def generate_sensor_samples(directory: Path, *, faults: bool = True) -> SensorSamples:
    """Create three CSV files; a clean variant supplies an independent false-positive control."""
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for device in SensorSamples(paths=()).devices:
        indices = list(range(WEEK_SAMPLES))
        if faults and device in GAP_RANGES:
            indices = [index for index in indices if index not in GAP_RANGES[device]]
        if faults and device == "kitchen-01":
            indices[200:212] = reversed(indices[200:212])
        path = directory / f"{device}.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(COLUMNS)
            writer.writerows(_row(device, index, faults=faults) for index in indices)
        paths.append(path)
    return SensorSamples(paths=tuple(paths))
