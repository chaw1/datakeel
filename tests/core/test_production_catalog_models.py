# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Strict migration plans and catalog action schemas reject ambiguous write intent."""

import pytest
from pydantic import ValidationError

from datakeel.actions.production_catalog_parameters import CreateLabelSetParams
from datakeel.core.production_catalog_models import (
    LabelMigration,
    ProductionLabel,
    ProductionModel,
    ProductionTemplate,
)


@pytest.mark.parametrize(
    ("operation", "sources", "targets", "strategy"),
    [
        ("rename", ("a", "b"), ("c",), "map"),
        ("delete", ("a",), ("b",), "drop"),
        ("delete", ("a",), (), "map"),
        ("merge", ("a",), ("c",), "map"),
        ("split", ("a",), ("b", "c"), "map"),
        ("split", ("a",), ("b", "b"), "manual"),
        ("merge", ("a", "a"), ("b",), "map"),
        ("rename", ("a",), ("b",), "drop"),
    ],
)
def test_migration_rejects_invalid_cardinality_or_ambiguous_strategy(
    operation: str,
    sources: tuple[str, ...],
    targets: tuple[str, ...],
    strategy: str,
) -> None:
    """Deletion and splitting need explicit loss or manual-review choices."""
    with pytest.raises(ValidationError):
        LabelMigration.model_validate(
            {
                "operation": operation,
                "source_ids": sources,
                "target_ids": targets,
                "strategy": strategy,
            }
        )


@pytest.mark.parametrize(
    "values",
    [
        {"target": "template"},
        {"labels": ()},
        {"operation": "delete"},
        {"operation": "update", "labels": [{"id": "a", "name": "a"}]},
    ],
)
def test_catalog_action_requires_explicit_valid_target(values: dict[str, object]) -> None:
    """A draft edit cannot silently select an identity or version omitted by the caller."""
    with pytest.raises(ValidationError):
        CreateLabelSetParams.model_validate({"request_id": "request", **values})


def test_label_definitions_forbid_unregistered_fields() -> None:
    """Frozen boundaries reject hidden caller-controlled catalog state."""
    with pytest.raises(ValidationError):
        ProductionLabel.model_validate({"id": "a", "name": "a", "published": True})


@pytest.mark.parametrize(
    "rules",
    [
        {"unknown_rule": True},
        {"min_annotations": "1"},
        {"min_annotations": True},
        {"max_annotations": False},
        {"max_annotations": 0.5},
        {"min_annotations": -1},
        {"min_annotations": 2, "max_annotations": 1},
    ],
)
def test_templates_reject_unsupported_or_invalid_validation_rules(rules: dict[str, object]) -> None:
    """Invalid rules are rejected at configuration time instead of silently ignored on saves."""
    with pytest.raises(ValidationError):
        ProductionTemplate.model_validate(
            {"id": "template", "name": "Template", "validation_rules": rules}
        )


def test_model_cost_uses_exact_decimal_catalog_prices_at_budget_boundary() -> None:
    """Three ten-cent predictions fit exactly in a thirty-cent declared budget."""
    model = ProductionModel(id="fake", name="Fake", version="1", provider="fake", unit_price=0.1)
    assert model.estimate_cost(3) == 0.3
