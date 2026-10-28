# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""All time-series parameters enforce strict, frozen, closed schemas."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from datakeel.core.errors import ValidationError
from datakeel.operators.timeseries.models import (
    AnomalyParams,
    ColumnRange,
    GapsParams,
    OrderParams,
    ResampleParams,
    TimestampParams,
    UnitParams,
)


@pytest.mark.parametrize(
    "model", [TimestampParams, OrderParams, GapsParams, ResampleParams, AnomalyParams, UnitParams]
)
def test_operator_parameters_reject_unknown_fields(model: type[TimestampParams]) -> None:
    """Each operator independently closes its public parameter boundary."""
    with pytest.raises(PydanticValidationError, match="Extra inputs"):
        model.model_validate({"undeclared": True})


def test_frequency_is_strict_and_positive() -> None:
    """String coercion and nonpositive frequencies fail before reading a table."""
    for value in ["1000", 0, -1]:
        with pytest.raises(PydanticValidationError):
            ResampleParams.model_validate({"interval_ms": value})


def test_range_bounds_cannot_be_inverted() -> None:
    """Engineering bounds must form an inclusive nonempty interval."""
    with pytest.raises((PydanticValidationError, ValidationError), match="minimum"):
        ColumnRange(column="temperature", minimum=100, maximum=0)
