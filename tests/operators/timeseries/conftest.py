# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Synthetic CSV fixtures for deterministic sensor-operator tests."""

import csv
from collections.abc import Callable
from pathlib import Path

import pytest

from datakeel.core.models import FileItem


@pytest.fixture
def table_file(tmp_path: Path) -> Callable[[list[tuple[str, ...]], tuple[str, ...]], FileItem]:
    """Build a CSV with only generated sensor data and known source row numbers."""

    def write(rows: list[tuple[str, ...]], columns: tuple[str, ...]) -> FileItem:
        path = tmp_path / "sensor.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(rows)
        return FileItem(path=str(path), filename=path.name, modality="table")

    return write
