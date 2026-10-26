# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate immutability and strict profiling boundaries."""

import pytest
from pydantic import ValidationError as ModelValidationError

from datakeel.operators.table.io import TableData
from datakeel.operators.table.models import TableProfile
from datakeel.operators.table.params import ProfileParams


def test_table_data_is_frozen_and_forbids_unknown_fields() -> None:
    """Changing a table requires a deliberate new typed value."""
    data = TableData(columns=("id",), rows=(("1",),), row_numbers=(2,))
    with pytest.raises(ModelValidationError, match="frozen"):
        data.rows = ()
    with pytest.raises(ModelValidationError, match="extra_forbidden"):
        TableData.model_validate({"columns": (), "rows": (), "row_numbers": (), "hidden": True})


@pytest.mark.parametrize(
    ("rows", "row_numbers"),
    [((("1",),), ()), ((("1", "extra"),), (2,)), ((("1",),), (0,))],
)
def test_table_shape_validation_prevents_lost_row_coordinates(
    rows: tuple[tuple[str, ...], ...], row_numbers: tuple[int, ...]
) -> None:
    """No table is accepted when evidence coordinates cannot match its values."""
    with pytest.raises(ModelValidationError):
        TableData(columns=("id",), rows=rows, row_numbers=row_numbers)


@pytest.mark.parametrize(
    "params", [{"undeclared": True}, {"detect_pii": "yes"}, {"enum_max_values": 0}]
)
def test_profile_params_reject_undeclared_and_coerced_values(params: dict[str, object]) -> None:
    """Parameters are explicit, strict and bounded."""
    with pytest.raises(ModelValidationError):
        ProfileParams.model_validate(params)


def test_profile_model_roundtrip_preserves_exact_empty_shape() -> None:
    """Metadata serialization restores the same immutable typed contract."""
    profile = TableProfile(row_count=0, column_count=0, columns=())
    assert TableProfile.model_validate_json(profile.model_dump_json()) == profile


def test_null_markers_accept_json_arrays_without_coercing_item_types() -> None:
    """The published array schema is usable through operator JSON parameters."""
    assert ProfileParams.model_validate({"null_values": ["", "missing"]}).null_values == (
        "",
        "missing",
    )
    with pytest.raises(ModelValidationError):
        ProfileParams.model_validate({"null_values": [1]})
