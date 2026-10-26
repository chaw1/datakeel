# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Declared unit checks distinguish explicit suffix conflicts from value bounds."""

from collections.abc import Callable
from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.timeseries.models import UnitSummary
from datakeel.operators.timeseries.unit_check import OPERATOR


def test_unit_suffix_conflicts_and_physical_range_have_source_evidence(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Compatible suffix aliases pass; mismatches are reported without conversion guesses."""
    file = table_file(
        [
            (str(index), "a", value)
            for index, value in enumerate(["20 °C", "21 ℃", "22 C", "75 °F", "-40", "unknown", ""])
        ],
        ("timestamp", "device_id", "temperature"),
    )
    output = OPERATOR.run(
        [file],
        tmp_path / "out",
        {
            "declarations": [
                {"column": "temperature", "unit": "°C", "minimum": -20, "maximum": 100},
            ]
        },
    ).files[0]
    summary = UnitSummary.model_validate(output.metadata["timeseries"]["unit_check"])
    assert [(issue.rule, issue.rows) for issue in summary.issues] == [
        ("unit_mismatch", (5,)),
        ("unit_range", (6,)),
    ]
    assert summary.issues[1].threshold == -20


def test_volumetric_units_are_not_inferred_or_converted(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Physically convertible units still require an explicit caller-controlled conversion."""
    file = table_file(
        [("0", "a", "3 L/min"), ("1", "a", "0.18 m³/h")], ("timestamp", "device_id", "gas_flow")
    )
    output = OPERATOR.run(
        [file],
        tmp_path / "out",
        {
            "declarations": [
                {"column": "gas_flow", "unit": "L/min"},
            ]
        },
    ).files[0]
    assert [issue["rows"] for issue in output.metadata["timeseries"]["unit_check"]["issues"]] == [
        [3]
    ]


def test_plain_numeric_values_use_declared_unit_and_inclusive_bounds(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """The declaration gives plain numeric cells their unit, including exact endpoints."""
    file = table_file(
        [("0", "a", "0"), ("1", "a", "100"), ("2", "a", "101")],
        ("timestamp", "device_id", "temperature"),
    )
    output = OPERATOR.run(
        [file],
        tmp_path / "out",
        {
            "declarations": [
                {"column": "temperature", "unit": "C", "minimum": 0, "maximum": 100},
            ]
        },
    ).files[0]
    assert output.metadata["timeseries"]["unit_check"]["issues"][0]["rows"] == [4]
