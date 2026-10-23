# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compliance API model boundary validation."""

import pytest
from pydantic import ValidationError

from datakeel.governance.models import ComplianceView


def test_compliance_unknown_fields_are_rejected() -> None:
    """Verify compliance unknown fields are rejected."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ComplianceView.model_validate({"total": 100, "dimensions": {}, "issues": [], "x": 1})
