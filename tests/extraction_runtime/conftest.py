# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Small independent contracts for deterministic extraction transport tests."""

import pytest

from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_models import TextBlock


@pytest.fixture
def schema() -> KGSchema:
    """Declare a compact vocabulary unrelated to production evaluation recordings."""
    return KGSchema.model_validate(
        {
            "id": "transport-fixture",
            "version": "1",
            "entity_types": [
                {"name": "Company", "description": "A company."},
                {"name": "Product", "description": "A product."},
            ],
            "relations": [
                {
                    "name": "develops",
                    "description": "A company develops a product.",
                    "domain": ["Company"],
                    "range": ["Product"],
                }
            ],
            "rules": ["Only extract facts explicitly established in the source."],
        }
    )


@pytest.fixture
def block() -> TextBlock:
    """Keep source offsets nonzero to exercise the typed domain boundary."""
    text = "Cedar develops Reed."
    return TextBlock(text=text, start=7, end=7 + len(text))
