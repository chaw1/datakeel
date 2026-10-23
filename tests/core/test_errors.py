# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expected failures retain domain identity and compatibility categories."""

import pytest

from datakeel.core.errors import (
    AuthorizationError,
    BudgetError,
    ConflictError,
    DatakeelError,
    ExecutionError,
    NotFoundError,
    ValidationError,
)


@pytest.mark.parametrize(
    "error_type",
    [
        AuthorizationError,
        BudgetError,
        ConflictError,
        ExecutionError,
        NotFoundError,
        ValidationError,
    ],
)
def test_declared_failure_when_raised_is_catchable_as_domain_error(
    error_type: type[DatakeelError],
) -> None:
    """Verify declared failure when raised is catchable as domain error."""
    msg = "declared failure"
    with pytest.raises(DatakeelError, match="declared failure"):
        raise error_type(msg)


def test_validation_failure_when_created_preserves_value_error_compatibility() -> None:
    """Verify validation failure when created preserves value error compatibility."""
    assert isinstance(ValidationError("invalid input"), ValueError)
