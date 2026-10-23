# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Object query contracts reject ambiguous or invalid selectors."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import JsonValue

import pytest
from pydantic import ValidationError

from datakeel.ontology.models import ObjectSet, PropertyFilter


@pytest.mark.parametrize(
    "value",
    [
        {"quality_min": 80, "quality_max": 20},
        {"created_after": "2026-01-02T00:00:00Z", "created_before": "2026-01-01T00:00:00Z"},
        {"created_after": "2026-01-01T00:00:00"},
        {"object_type": "unknown"},
        {"schema_version": "999"},
        {"namespace": "different"},
        {"limit": 0},
        {"unexpected": True},
    ],
)
def test_object_set_when_invalid_or_ambiguous_rejects_query(value: JsonValue) -> None:
    """Verify object set when invalid or ambiguous rejects query."""
    with pytest.raises(ValidationError):
        ObjectSet.model_validate(value)


@pytest.mark.parametrize(
    "value",
    [
        {"field": "id", "operator": "in", "value": "wrong"},
        {"field": "quality", "operator": "lt", "value": True},
        {"field": "quality", "operator": "lt", "value": "60"},
    ],
)
def test_property_filter_when_operand_type_incompatible_rejects_query(value: JsonValue) -> None:
    """Verify property filter when operand type incompatible rejects query."""
    with pytest.raises(ValidationError):
        PropertyFilter.model_validate(value)
